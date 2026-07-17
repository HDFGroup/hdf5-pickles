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
import os
import sys

import numpy as np

try:
    import h5py
except ImportError:  # pragma: no cover
    sys.exit("make_fixtures: h5py is required")


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
