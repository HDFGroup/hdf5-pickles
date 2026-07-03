#!/usr/bin/env python3
"""Generate a minimal regression seed for CVE-2020-10812.

The vulnerability: a crafted file whose *superblock extension* carries a
metadata-cache-image message pointing at an out-of-file address.  libhdf5 reads
the superblock extension at open time and aborts with an address overflow;
h5policy must likewise reject it (it does, once it walks the superblock
extension -- which was a blind spot until that was fixed).

This builds the seed reproducibly: start from a valid h5py file (v2/v3
superblock + root group), append a version-1 object header holding one
metadata-cache-image message with a bogus address/size, then repoint the
superblock's extension address and EOF and recompute its checksum.  The v1
object header has no checksum of its own, so libhdf5's rejection is the address
overflow, exactly as in the original CVE reproducer.

Usage: make_cve_2020_10812.py [OUTPUT.h5]   (default: ./cve_2020_10812.h5)
"""
import os
import struct
import sys
import tempfile

import numpy as np

try:
    import h5py
except ImportError:  # pragma: no cover
    sys.exit("h5py is required to build the CVE seed")

HDF5_MAGIC = bytes([0x89, 0x48, 0x44, 0x46, 0x0D, 0x0A, 0x1A, 0x0A])
BAD_ADDR = 0x00010100      # 65792 -- past EOF
BAD_SIZE = 0x10000000      # 256 MiB -- past EOF
MDCI_MSG_TYPE = 0x0018     # metadata cache image


def _rot(x, k):
    return ((x << k) | (x >> (32 - k))) & 0xFFFFFFFF


def jenkins_lookup3(data, initval=0):
    """H5_checksum_lookup3 (Jenkins hashlittle) over `data`."""
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

    length = len(data)
    a = b = c = (0xDEADBEEF + length + initval) & 0xFFFFFFFF
    i = 0
    while length - i > 12:
        a = (a + int.from_bytes(data[i:i + 4], "little")) & 0xFFFFFFFF
        b = (b + int.from_bytes(data[i + 4:i + 8], "little")) & 0xFFFFFFFF
        c = (c + int.from_bytes(data[i + 8:i + 12], "little")) & 0xFFFFFFFF
        a, b, c = mix(a, b, c)
        i += 12
    tail = data[i:] + b"\x00" * (12 - (length - i))
    a = (a + int.from_bytes(tail[0:4], "little")) & 0xFFFFFFFF
    b = (b + int.from_bytes(tail[4:8], "little")) & 0xFFFFFFFF
    c = (c + int.from_bytes(tail[8:12], "little")) & 0xFFFFFFFF
    if length > 0:
        a, b, c = final(a, b, c)
    return c


def build(out_path):
    with tempfile.NamedTemporaryFile(suffix=".h5", delete=False) as tf:
        base = tf.name
    try:
        # track_times=False keeps the base byte-deterministic (no timestamps).
        with h5py.File(base, "w", libver="latest") as h:
            h.create_dataset("a", data=np.arange(4, dtype="i4"), track_times=False)
        raw = bytearray(open(base, "rb").read())
    finally:
        os.unlink(base)

    assert raw[:8] == HDF5_MAGIC, "base is not an HDF5 file"
    sbver = raw[8]
    assert sbver in (2, 3), f"need a v2/v3 superblock, got v{sbver}"
    soff = raw[9]
    ext_off = 12 + soff
    eof_off = 12 + 2 * soff
    chksum_off = 12 + 4 * soff

    # Self-check the checksum routine against the base file's real superblock.
    stored = struct.unpack_from("<I", raw, chksum_off)[0]
    assert jenkins_lookup3(bytes(raw[:chksum_off])) == stored, \
        "lookup3 self-check failed"

    # A version-1 object header holding one metadata-cache-image message.
    payload = struct.pack("<B", 0) + struct.pack("<Q", BAD_ADDR) + struct.pack("<Q", BAD_SIZE)
    msg_data = payload + b"\x00" * ((-len(payload)) % 8)          # pad to multiple of 8
    msg = struct.pack("<HHB", MDCI_MSG_TYPE, len(msg_data), 0) + b"\x00" * 3 + msg_data
    ohdr = struct.pack("<BBHII", 1, 0, 1, 1, len(msg)) + b"\x00" * 4 + msg

    raw += b"\x00" * ((-len(raw)) % 8)                            # 8-byte align
    ext_addr = len(raw)
    raw += ohdr

    struct.pack_into("<Q", raw, ext_off, ext_addr)               # superblock ext address
    struct.pack_into("<Q", raw, eof_off, len(raw))               # EOF address
    struct.pack_into("<I", raw, chksum_off, jenkins_lookup3(bytes(raw[:chksum_off])))

    with open(out_path, "wb") as f:
        f.write(bytes(raw))
    return out_path


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else \
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "cve_2020_10812.h5")
    build(out)
    print(f"wrote {out} ({os.path.getsize(out)} bytes)")
