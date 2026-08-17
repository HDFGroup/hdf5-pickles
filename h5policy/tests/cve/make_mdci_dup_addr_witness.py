#!/usr/bin/env python3
"""Build a MINIMAL, CLEAN duplicate-address MDCI witness.

Goal: isolate the metadata-cache-image *entry-address uniqueness* invariant from
the trailing-byte / oversized-length artifact that the original
poc_heap_corruption.h5 uses.  This file has:

  * a correctly sized cache-image block (image_data_len == real length),
  * a valid lookup3 (Jenkins hashlittle) trailing checksum,
  * two well-formed entries whose addresses are IDENTICAL (0x30).

Everything h5policy currently checks (envelope, version, flags/dependency
consistency, per-entry overrun, exact single trailing checksum) PASSES.  The
only defect is the duplicate entry address -- the invariant libhdf5 enforces in
H5C__check_for_duplicates (H5Cimage.c:2418) and h5policy does not yet model.

Template: h5policy/tests/cve/make_cve_2020_10812.py (same v1-OH + MDCI-message
grafting, same lookup3).

PROMOTED 2026-08-15 from an h5cve working bundle, which is gitignored working
scratch.  This file was the only copy of the witness named in
registry/cases/mdci-reconstruct-cleanup-unsafe.yml under
`reproducers.regression_witness`, so the record depended on an untracked file.
It is invoked from h5policy-gencorpus (_make_mdci_dup_addr_witness) and its
output is a committed cve/ seed, checked byte-for-byte by run.sh's
tracked-fixture reproducibility step.

WHAT IT WITNESSES: this file was a PROVEN h5policy false accept -- oracle exit 0,
zero findings, while libhdf5 rejected it -- until 7f928c9 added the
mdci.entry_addr_unique check.  At HEAD it rejects, so it now guards that fix
rather than demonstrating the gap.  That is why it belongs in the corpus: a
regression would silently restore a soundness hole, and nothing else would
notice.
"""
import os, struct, sys, tempfile
import numpy as np, h5py

HDF5_MAGIC = bytes([0x89, 0x48, 0x44, 0x46, 0x0D, 0x0A, 0x1A, 0x0A])
MDCI_MSG_TYPE = 0x0018


def _rot(x, k):
    return ((x << k) | (x >> (32 - k))) & 0xFFFFFFFF


def jenkins_lookup3(data, initval=0):
    def mix(a, b, c):
        a = (a - c) & 0xFFFFFFFF; a ^= _rot(c, 4);  c = (c + b) & 0xFFFFFFFF
        b = (b - a) & 0xFFFFFFFF; b ^= _rot(a, 6);  a = (a + c) & 0xFFFFFFFF
        c = (c - b) & 0xFFFFFFFF; c ^= _rot(b, 8);  b = (b + a) & 0xFFFFFFFF
        a = (a - c) & 0xFFFFFFFF; a ^= _rot(c, 16); c = (c + b) & 0xFFFFFFFF
        b = (b - a) & 0xFFFFFFFF; b ^= _rot(a, 19); a = (a + c) & 0xFFFFFFFF
        c = (c - b) & 0xFFFFFFFF; c ^= _rot(b, 4);  b = (b + a) & 0xFFFFFFFF
        return a & 0xFFFFFFFF, b & 0xFFFFFFFF, c & 0xFFFFFFFF

    def final(a, b, c):
        c ^= b; c = (c - _rot(b, 14)) & 0xFFFFFFFF
        a ^= c; a = (a - _rot(c, 11)) & 0xFFFFFFFF
        b ^= a; b = (b - _rot(a, 25)) & 0xFFFFFFFF
        c ^= b; c = (c - _rot(b, 16)) & 0xFFFFFFFF
        a ^= c; a = (a - _rot(c, 4)) & 0xFFFFFFFF
        b ^= a; b = (b - _rot(a, 14)) & 0xFFFFFFFF
        c ^= b; c = (c - _rot(b, 24)) & 0xFFFFFFFF
        return a & 0xFFFFFFFF, b & 0xFFFFFFFF, c & 0xFFFFFFFF

    length = len(data); a = b = c = (0xDEADBEEF + length + initval) & 0xFFFFFFFF
    i = 0
    while length - i > 12:
        a = (a + int.from_bytes(data[i:i+4], "little")) & 0xFFFFFFFF
        b = (b + int.from_bytes(data[i+4:i+8], "little")) & 0xFFFFFFFF
        c = (c + int.from_bytes(data[i+8:i+12], "little")) & 0xFFFFFFFF
        a, b, c = mix(a, b, c); i += 12
    tail = data[i:] + b"\x00" * (12 - (length - i))
    a = (a + int.from_bytes(tail[0:4], "little")) & 0xFFFFFFFF
    b = (b + int.from_bytes(tail[4:8], "little")) & 0xFFFFFFFF
    c = (c + int.from_bytes(tail[8:12], "little")) & 0xFFFFFFFF
    if length > 0:
        a, b, c = final(a, b, c)
    return c


def encode_entry(type_id, flags, addr, image):
    out = bytes([type_id, flags, 1, 0])                     # type,flags,ring,age
    out += struct.pack("<HHH", 0, 0, 0)                     # child,dirty,parent counts
    out += struct.pack("<i", -1)                            # lru_rank
    out += struct.pack("<QQ", addr, len(image))             # addr, body length
    return out + image                                      # no parents


def build_block(dup_addr, body):
    """Two type-5 (object-header) entries at the SAME address, each carrying a
    valid object-header body so the image is coherent under h5policy's MDCI
    cached-body replay. The only defect is the repeated address."""
    e0 = encode_entry(5, 0x00, dup_addr, body)
    e1 = encode_entry(5, 0x00, dup_addr, body)             # SAME address -> the defect
    entries = e0 + e1
    image_size = 10 + 8 + len(entries) + 4                 # sig+ver+flags(6) + data_len(8) + nentries(4)... +checksum(4)
    header = b"MDCI" + bytes([0, 0]) + struct.pack("<Q", image_size) + struct.pack("<I", 2)
    block_wo_cksum = header + entries
    assert len(block_wo_cksum) == image_size - 4, (len(block_wo_cksum), image_size)
    cksum = jenkins_lookup3(block_wo_cksum)
    return block_wo_cksum + struct.pack("<I", cksum), image_size


def pin_v2_ohdr_times(raw, offset):
    """Zero the root v2 object-header timestamps and reseal its checksum.

    ``track_times=False`` pins the dataset header below, but h5py still writes
    wall-clock timestamps into the root-group header.  This builder copies that
    header into both MDCI entries, so leave no timestamp-dependent bytes for the
    generated witness to inherit.
    """
    if raw[offset:offset + 4] != b"OHDR" or raw[offset + 4] != 2:
        raise RuntimeError("expected a v2 root object header")
    flags = raw[offset + 5]
    if not flags & (1 << 5):
        return
    cursor = offset + 6 + 16 + (4 if flags & (1 << 4) else 0)
    size_width = 1 << (flags & 3)
    chksum_off = cursor + size_width + int.from_bytes(
        raw[cursor:cursor + size_width], "little")
    if chksum_off + 4 > len(raw):
        raise RuntimeError("root object-header checksum is outside the file")
    if struct.unpack_from("<I", raw, chksum_off)[0] != jenkins_lookup3(
            bytes(raw[offset:chksum_off])):
        raise RuntimeError("root object-header checksum mismatch")
    raw[offset + 6:offset + 22] = b"\x00" * 16
    struct.pack_into("<I", raw, chksum_off,
                     jenkins_lookup3(bytes(raw[offset:chksum_off])))


def build(out_path):
    with tempfile.NamedTemporaryFile(suffix=".h5", delete=False) as tf:
        base = tf.name
    try:
        with h5py.File(base, "w", libver="latest") as h:
            h.create_dataset("a", data=np.arange(4, dtype="i4"), track_times=False)
        raw = bytearray(open(base, "rb").read())
    finally:
        os.unlink(base)

    assert raw[:8] == HDF5_MAGIC
    sbver = raw[8]; assert sbver in (2, 3), f"need v2/v3 superblock, got v{sbver}"
    soff = raw[9]
    ext_off, eof_off, chksum_off = 12 + soff, 12 + 2 * soff, 12 + 4 * soff
    assert jenkins_lookup3(bytes(raw[:chksum_off])) == struct.unpack_from("<I", raw, chksum_off)[0], \
        "lookup3 self-check failed"

    # Duplicate the ROOT object header: both entries sit at the root-OH address
    # and carry the real OH bytes, so replay stays coherent and only the address
    # uniqueness is violated.
    root_oh = struct.unpack_from("<Q", raw, 12 + 3 * soff)[0]
    pin_v2_ohdr_times(raw, root_oh)
    oh_body = bytes(raw[root_oh:])                          # full OH (decode uses its own internal lengths)

    # Place the MDCI block first so its address is known when we write the message.
    raw += b"\x00" * ((-len(raw)) % 8)
    image_addr = len(raw)
    block, image_size = build_block(root_oh, oh_body)
    raw += block

    # v1 object header holding one MDCI message: version:u8, image addr:u64, size:u64.
    raw += b"\x00" * ((-len(raw)) % 8)
    payload = struct.pack("<B", 0) + struct.pack("<Q", image_addr) + struct.pack("<Q", image_size)
    msg_data = payload + b"\x00" * ((-len(payload)) % 8)
    msg = struct.pack("<HHB", MDCI_MSG_TYPE, len(msg_data), 0) + b"\x00" * 3 + msg_data
    ohdr = struct.pack("<BBHII", 1, 0, 1, 1, len(msg)) + b"\x00" * 4 + msg
    raw += b"\x00" * ((-len(raw)) % 8)
    ext_addr = len(raw)
    raw += ohdr

    struct.pack_into("<Q", raw, ext_off, ext_addr)
    struct.pack_into("<Q", raw, eof_off, len(raw))
    struct.pack_into("<I", raw, chksum_off, jenkins_lookup3(bytes(raw[:chksum_off])))

    with open(out_path, "wb") as f:
        f.write(bytes(raw))
    return out_path, image_addr, image_size


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "dup_addr_witness.h5"
    p, a, s = build(out)
    print(f"wrote {p} ({os.path.getsize(p)} bytes); MDCI block @ {a} size {s}, two entries both @ 0x30")
