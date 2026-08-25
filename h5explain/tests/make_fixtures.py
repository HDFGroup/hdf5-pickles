#!/usr/bin/env python3
# Copyright (C) 2026 The HDF Group.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Generate the h5explain navigation fixtures.

Writes small, deterministic HDF5 files into ``tests/fixtures``, each chosen to
put a different primitive under the explorer's cursor: old-style symbol tables,
new-style compact links, dense link storage, and the chunk indexes.

The generated ``*.h5`` files are build artifacts (git-ignored); the tracked
specification lives in ``test_h5explain.py``.

Requires: h5py.  Usage: make_fixtures.py [TARGET_DIR]
"""
import ctypes
import ctypes.util
import os
import sys

import numpy as np

try:
    import h5py
except ImportError:  # pragma: no cover
    sys.exit("make_fixtures: h5py is required")

from h5py import h5f, h5p


def _find_libhdf5():
    """Locate the libhdf5 shared library that h5py itself is linked against.

    h5py's public API has no binding for H5Pset_shared_mesg_index() (used to
    build the SOHM fixture below), so that one property is set through a raw
    ctypes call instead.  There is no portable way to ask h5py for the path
    of the library it loaded, so this tries the same places h5py itself
    would find it.
    """
    found = ctypes.util.find_library("hdf5")
    if found:
        return found

    # glob("**") skips dot-directories, but vendored wheel libs commonly live
    # under one (h5py/.dylibs/, h5py/.libs/) -- walk instead so those aren't
    # silently missed.
    h5py_dir = os.path.dirname(os.path.abspath(h5py.__file__))
    search_roots = [h5py_dir, os.path.join(os.path.dirname(h5py_dir), "h5py.libs")]
    for root in search_roots:
        for dirpath, _dirnames, filenames in os.walk(root):
            for name in filenames:
                if name.startswith("libhdf5") and (".so" in name or name.endswith(".dylib")):
                    return os.path.join(dirpath, name)

    for name in ("libhdf5.so", "libhdf5.dylib"):
        try:
            ctypes.CDLL(name)
            return name
        except OSError:
            continue
    return None


def _make_shared_mesg_fcpl(userblock_size, mesg_type_flags):
    """A file-creation property list with a userblock and one SOHM index.

    mesg_type_flags is an H5O_SHMESG_*_FLAG bitmask (bit position == the
    on-disk object-header message type ID being shared -- see sohm.pk's
    "Message type flags" table), not exposed by h5py's own h5p bindings.
    """
    libhdf5_path = _find_libhdf5()
    if libhdf5_path is None:
        sys.exit("make_fixtures: could not locate the libhdf5 shared library "
                 "h5py is linked against (needed for the SOHM fixture)")
    lib = ctypes.CDLL(libhdf5_path)
    lib.H5Pset_userblock.argtypes = [ctypes.c_int64, ctypes.c_uint64]
    lib.H5Pset_shared_mesg_nindexes.argtypes = [ctypes.c_int64, ctypes.c_uint]
    lib.H5Pset_shared_mesg_index.argtypes = [
        ctypes.c_int64, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint]

    fcpl = h5p.create(h5p.FILE_CREATE)
    if (lib.H5Pset_userblock(fcpl.id, userblock_size) < 0
            or lib.H5Pset_shared_mesg_nindexes(fcpl.id, 1) < 0
            or lib.H5Pset_shared_mesg_index(fcpl.id, 0, mesg_type_flags, 0) < 0):
        sys.exit("make_fixtures: H5Pset_shared_mesg_* failed")
    return fcpl


def make_earliest(path):
    """v0 superblock, v1 object headers (no signature), symbol-table links.

    Exercises the h5explain_detect_kind heuristic: v1 headers carry no OHDR
    signature, so the explorer has to guess from version/message-count.
    """
    with h5py.File(path, "w", libver="earliest") as f:
        g = f.create_group("group_a")
        g.create_dataset("values", data=np.arange(8, dtype="<i4"))
        f.create_dataset("top", data=np.arange(4, dtype="<f8"))
        # A v1-era chunked dataset indexes its chunks with a v1 B-tree, which
        # is the only index whose decode needs set_bt1_ndims(D+1).
        f.create_dataset("chunked", data=np.arange(64, dtype="<i4"),
                         maxshape=(None,), chunks=(8,))


def make_latest(path):
    """v2+ superblock, OHDR-signature headers, compact link messages."""
    with h5py.File(path, "w", libver="latest") as f:
        g = f.create_group("group_a")
        g.create_dataset("values", data=np.arange(8, dtype="<i4"))
        f.create_dataset("top", data=np.arange(4, dtype="<f8"))
        f["top"].attrs["units"] = "m"


def make_userblock(path, libver):
    """A shifted superblock whose metadata addresses are base-relative."""
    with h5py.File(path, "w", libver=libver, userblock_size=512) as f:
        g = f.create_group("group_a")
        g.create_dataset("values", data=np.arange(8, dtype="<i4"))


def make_userblock_sohm(path):
    """A shifted superblock with a real Shared Object Header Message table.

    Requires a v2+ superblock (SOHM needs a superblock extension), so this
    always uses "latest" -- there is no v1/earliest-header equivalent.

    Two datasets share an identical dataspace and datatype; libhdf5 leaves
    the first dataset's copies in place (H5SM_IN_OH) and only physically
    moves the second dataset's copies into the SOHM heap, marking them
    OH_MSG_FLAG_SHARED.  Only "values2" exercises the base-relative
    SOHM-heap-address translation this fixture exists to cover (issue #77).
    """
    H5O_SHMESG_SDSPACE_FLAG = 0x0002
    H5O_SHMESG_DTYPE_FLAG   = 0x0008
    fcpl = _make_shared_mesg_fcpl(512, H5O_SHMESG_SDSPACE_FLAG | H5O_SHMESG_DTYPE_FLAG)
    fapl = h5p.create(h5p.FILE_ACCESS)
    fapl.set_libver_bounds(h5f.LIBVER_LATEST, h5f.LIBVER_LATEST)
    fid = h5f.create(path.encode(), h5f.ACC_TRUNC, fcpl=fcpl, fapl=fapl)
    with h5py.File(fid) as f:
        g = f.create_group("group_a")
        g.create_dataset("values", data=np.arange(8, dtype="<i4"))
        g.create_dataset("values2", data=np.arange(8, dtype="<i4"))


def make_dense(path):
    """Dense link storage: fractal heap plus a v2 B-tree name index."""
    with h5py.File(path, "w", libver="latest") as f:
        dense = f.create_group("dense")
        # The default compact-to-dense threshold is 8 links; 24 puts the group
        # well past the conversion so the links live in the fractal heap.
        for i in range(24):
            dense.create_group("child_%02d" % i)


def make_chunked(path):
    """Chunk indexes: fixed array, extensible array, and v1 B-tree."""
    # Every dataset is written, not just created: an unwritten chunked dataset
    # leaves idx_addr undefined and there is no index for h5explain to reach.
    with h5py.File(path, "w", libver="latest") as f:
        # Fixed dims + chunks => fixed array index.
        f.create_dataset("fixed", data=np.arange(64, dtype="<i4"), chunks=(8,))
        # One unlimited dim => extensible array index.
        f.create_dataset("extensible", data=np.arange(64, dtype="<i4"),
                         maxshape=(None,), chunks=(8,))
        # Two unlimited dims => v1 B-tree index.
        f.create_dataset("btree", data=np.arange(256, dtype="<i4").reshape(16, 16),
                         maxshape=(None, None), chunks=(4, 4))


def make_filtered(path):
    """A v2 pipeline whose built-in filters carry client data but no names."""
    with h5py.File(path, "w", libver="latest") as f:
        data = np.arange(1280, dtype="<f8").reshape(1, 1280)
        f.create_dataset("filtered", data=data, chunks=(1, 1280),
                         shuffle=True, compression="gzip", compression_opts=1)


def make_bad_signature(path):
    """A file whose superblock signature is broken.

    The explorer has to open this: a superblock that does not decode is exactly
    the case worth exploring, and h5policy reports it at offset 0 -- the same
    offset it uses as its "no location" placeholder.
    """
    make_latest(path)
    with open(path, "rb") as fh:
        raw = bytearray(fh.read())
    raw[0] ^= 0xFF
    with open(path, "wb") as fh:
        fh.write(raw)


FIXTURES = {
    "earliest.h5": make_earliest,
    "latest.h5": make_latest,
    "userblock_latest.h5": lambda path: make_userblock(path, "latest"),
    "userblock_earliest.h5": lambda path: make_userblock(path, "earliest"),
    "userblock_sohm.h5": make_userblock_sohm,
    "dense.h5": make_dense,
    "chunked.h5": make_chunked,
    "filtered.h5": make_filtered,
    "bad_signature.h5": make_bad_signature,
}


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "fixtures")
    os.makedirs(target, exist_ok=True)
    for name, builder in FIXTURES.items():
        path = os.path.join(target, name)
        builder(path)
        print("make_fixtures: wrote %s" % path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
