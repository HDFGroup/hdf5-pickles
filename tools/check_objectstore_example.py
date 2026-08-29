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

"""Check the worked example in the object-store mapping document.

The document walks one HDF5 file end to end and quotes its spans, field
offsets, values, digests, and byte counts.  Those numbers follow the writer:
an h5py or libhdf5 change can move an object header and silently make every
one of them wrong, leaving a document that reads as measured and is not.

So this check does not trust the prose.  It reads each claim OUT of the
document and compares it against a freshly written fixture:

  * every `A..B` span in the manifest table, for ordering and overlap;
  * the values the table names at those spans -- the chunk-index address, the
    two global-heap ID components, the heap value, the collection size;
  * the raw layout bytes and the payload digests quoted in the record;
  * the byte counts in the accounting paragraph, recomputed from the spans.

A regex that fails to match is a failure, not a skip.  Deleting a claim from
the document must not be a way to make its check pass.

The regime itself -- fixed-array index, two of four chunks, a global-heap
backed attribute -- is asserted by the generator instead, so that a writer
change breaks this documentation check rather than corpus generation.
"""

import hashlib
import importlib.machinery
import importlib.util
import re
import struct
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "Mapping HDF5 Binary Primitives onto an Object Store.md"
GENCORPUS = ROOT / "tools" / "h5policy-gencorpus"
CORPUS_FIXTURE = (ROOT / "h5policy" / "tests" / "valid"
                  / "objectstore_mapping_example.h5")

failures = []


def check(label, condition, detail=""):
    if not condition:
        failures.append(f"{label}{': ' + detail if detail else ''}")


def claim(pattern, text, label):
    """Pull one claim out of the document.  A missing claim is a failure."""
    match = re.search(pattern, text, re.MULTILINE)
    if match is None:
        failures.append(f"the document no longer states {label} "
                        f"(pattern {pattern!r} did not match)")
        return None
    return match.group(1)


def load_writer():
    spec = importlib.util.spec_from_loader(
        "gencorpus",
        importlib.machinery.SourceFileLoader("gencorpus", str(GENCORPUS)))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.write_objectstore_mapping_example


def main():
    text = DOC.read_text(encoding="utf-8")

    if CORPUS_FIXTURE.exists():
        raw = CORPUS_FIXTURE.read_bytes()
        source = f"corpus fixture {CORPUS_FIXTURE.relative_to(ROOT)}"
        tmp = None
    else:
        try:
            writer = load_writer()
        except SystemExit as exc:            # gencorpus exits without h5py
            print(f"OBJECT-STORE EXAMPLE CHECK SKIPPED: {exc}")
            return 0
        except ImportError as exc:
            print(f"OBJECT-STORE EXAMPLE CHECK SKIPPED: {exc}")
            return 0
        tmp = tempfile.TemporaryDirectory()
        path = writer(str(Path(tmp.name) / "objectstore_mapping_example.h5"))
        raw = Path(path).read_bytes()
        source = "a freshly written fixture (corpus not generated)"

    # ---- spans named by the manifest table ---------------------------------
    section = text[text.index("### Import: the byte-ownership manifest"):
                   text.index("### Import: records and keys")]
    spans = [(int(a), int(b)) for a, b in
             re.findall(r"^\| `(\d+)\.\.(\d+)`", section, re.MULTILINE)]
    check("the manifest table lists spans", len(spans) >= 20,
          f"found {len(spans)}")
    for lo, hi in spans:
        check(f"span {lo}..{hi} is non-empty and inside the file",
              0 <= lo < hi <= len(raw))
    ordered = sorted(set(spans))
    for (alo, ahi), (blo, bhi) in zip(ordered, ordered[1:]):
        check(f"spans {alo}..{ahi} and {blo}..{bhi} do not overlap",
              ahi <= blo, "the manifest must give every byte one class")

    # ---- values the document names at those spans --------------------------
    eoa = int(claim(r"EOA `(\d+)`", text, "the EOA") or 0)
    check("EOA matches the superblock and the file length",
          struct.unpack("<Q", raw[28:36])[0] == eoa == len(raw),
          f"document {eoa}, superblock "
          f"{struct.unpack('<Q', raw[28:36])[0]}, file {len(raw)}")

    idx_lo, idx_hi = (int(x) for x in re.search(
        r"^\| `(\d+)\.\.(\d+)` \| — its chunk-index address", section,
        re.MULTILINE).groups())
    idx_value = int(claim(r"— its chunk-index address, value `(\d+)`",
                          section, "the chunk-index address value") or 0)
    check("the chunk-index address field holds the documented value",
          struct.unpack("<Q", raw[idx_lo:idx_hi])[0] == idx_value,
          f"document {idx_value}, file "
          f"{struct.unpack('<Q', raw[idx_lo:idx_hi])[0]}")
    check("that address points at the fixed-array header",
          raw[idx_value:idx_value + 4] == b"FAHD",
          f"bytes at {idx_value} are {raw[idx_value:idx_value + 4]!r}")

    gh_lo, gh_hi = (int(x) for x in re.search(
        r"^\| `(\d+)\.\.(\d+)` \| — global-heap collection address",
        section, re.MULTILINE).groups())
    gh_value = int(claim(r"— global-heap collection address, value `(\d+)`",
                         section, "the collection address") or 0)
    check("the collection-address component holds the documented value",
          struct.unpack("<Q", raw[gh_lo:gh_hi])[0] == gh_value)
    check("that address points at the collection",
          raw[gh_value:gh_value + 4] == b"GCOL")

    ix_lo, ix_hi = (int(x) for x in re.search(
        r"^\| `(\d+)\.\.(\d+)` \| — global-heap object index", section,
        re.MULTILINE).groups())
    ix_value = int(claim(r"— global-heap object index, value `(\d+)`",
                         section, "the object index") or 0)
    check("the object-index component holds the documented value",
          struct.unpack("<I", raw[ix_lo:ix_hi])[0] == ix_value)

    hv_lo, hv_hi = (int(x) for x in re.search(
        r"^\| `(\d+)\.\.(\d+)` \| — the heap object body", section,
        re.MULTILINE).groups())
    check("the heap object body is the documented string",
          raw[hv_lo:hv_hi] == b"some note", repr(raw[hv_lo:hv_hi]))

    size = int(claim(r"`GCOL`, (\d+) bytes allocated", section,
                     "the collection size") or 0)
    check("the collection declares the documented size",
          struct.unpack("<Q", raw[gh_value + 8:gh_value + 16])[0] == size)

    nil_lo, nil_hi = (int(x) for x in re.search(
        r"^\| `(\d+)\.\.(\d+)` \| NIL message", section,
        re.MULTILINE).groups())
    check("the NIL message is zero-filled reserved space",
          raw[nil_lo:nil_hi] == b"\0" * (nil_hi - nil_lo))
    gap_lo, gap_hi = (int(x) for x in re.search(
        r"^\| `(\d+)\.\.(\d+)` \| Allocation gap", section,
        re.MULTILINE).groups())
    check("the allocation gap is zero-filled",
          raw[gap_lo:gap_hi] == b"\0" * (gap_hi - gap_lo))
    gap_len = int(claim(r"the (\d+)-byte allocation gap", text,
                        "the allocation-gap length") or 0)
    check("the allocation gap is the documented length",
          gap_hi - gap_lo == gap_len, f"document {gap_len}, file "
          f"{gap_hi - gap_lo}")

    # ---- the record: raw bytes and payload digests -------------------------
    lay_lo = int(re.search(r"^\| `(\d+)\.\.\d+` \| Layout message body",
                           section, re.MULTILINE).group(1))
    lay_hex = claim(r"raw_bytes: ([0-9a-f]{20,})", text,
                    "the raw layout bytes")
    if lay_hex:
        check("the quoted layout bytes are the file's layout message",
              raw[lay_lo:lay_lo + len(lay_hex) // 2].hex() == lay_hex,
              f"file has {raw[lay_lo:lay_lo + len(lay_hex) // 2].hex()}")
        offset = int(claim(r"      - offset: (\d+)\n        width: 8\n"
                           r"        kind: chunk_index_root", text,
                           "the layout relocation offset") or -1)
        check("the relocation offset is the address field of those bytes",
              lay_lo + offset == idx_lo,
              f"body at {lay_lo} + {offset} != field at {idx_lo}")

    payloads = []
    for label in ("Chunk `\\(0,0\\)`", "Chunk `\\(2,0\\)`"):
        lo, hi = (int(x) for x in re.search(
            rf"^\| `(\d+)\.\.(\d+)` \| {label}", section,
            re.MULTILINE).groups())
        payloads.append(raw[lo:hi])
    payloads.append(raw[hv_lo:hv_hi])

    # The keys block addresses all three payloads; the record quotes only the
    # two chunks.  Both forms are checked, and they must agree with each other.
    key_digests = re.findall(r"\{c\}/h/sha256/([0-9a-f]{8,})\.\.\.", text)
    check("the keys block addresses all three payloads",
          len(key_digests) == 3, f"found {len(key_digests)}")
    record_digests = re.findall(r"payload: sha256:([0-9a-f]{8,})\.\.\.",
                                text)
    check("the record quotes both chunk payload digests",
          len(record_digests) == 2, f"found {len(record_digests)}")
    for digest, payload in zip(key_digests, payloads):
        actual = hashlib.sha256(payload).hexdigest()
        check(f"key digest {digest}... matches its payload",
              actual.startswith(digest), f"payload digest is {actual}")
    for quoted, keyed in zip(record_digests, key_digests):
        check(f"record digest {quoted}... agrees with the key",
              keyed.startswith(quoted) or quoted.startswith(keyed),
              f"the keys block says {keyed}")

    # ---- the accounting paragraph, recomputed from the spans ---------------
    meta = int(claim(r"bytes: (\d+) of metadata and heap value", text,
                     "the metadata byte count") or 0)
    payload_bytes = int(claim(r"heap value, (\d+) of chunk payload", text,
                              "the payload byte count") or 0)
    total = int(claim(r"preserved content is (\d+)\n?bytes", text,
                      "the preserved-content total") or 0)
    check("the preserved-content total is the sum of its parts",
          meta + payload_bytes == total,
          f"{meta} + {payload_bytes} != {total}")
    check("the chunk payload count matches the spans",
          sum(len(p) for p in payloads[:2]) == payload_bytes)
    pack_claim = claim(r"collection framing and its (\d+) bytes of", text,
                       "the collection packing count")
    if pack_claim:
        tail_lo, tail_hi = (int(x) for x in re.search(
            r"^\| `(\d+)\.\.(\d+)` \| Remainder of the collection", section,
            re.MULTILINE).groups())
        check("the collection packing count matches its span",
              tail_hi - tail_lo == int(pack_claim),
              f"document {pack_claim}, span {tail_hi - tail_lo}")
    attr_rest = claim(r"the (\d+) non-heap-ID bytes", text,
                      "the attribute non-relocation byte count")
    if attr_rest:
        a_lo, a_hi = (int(x) for x in re.search(
            r"^\| `(\d+)\.\.(\d+)` \| Attribute message body", section,
            re.MULTILINE).groups())
        check("the attribute's non-relocation byte count matches its spans",
              (a_hi - a_lo) == int(attr_rest),
              f"document {attr_rest}, span {a_hi - a_lo}")

    if tmp is not None:
        tmp.cleanup()

    if failures:
        print("OBJECT-STORE EXAMPLE CHECK FAILED "
              f"(against {source}):", file=sys.stderr)
        for line in failures:
            print(f"  {line}", file=sys.stderr)
        print("\n  The document quotes measured values.  If the writer moved "
              "them,\n  update the prose in\n"
              f"  {DOC.relative_to(ROOT)}\n  rather than relaxing this check.",
              file=sys.stderr)
        return 1
    print(f"OBJECT-STORE EXAMPLE CHECK OK: {len(spans)} manifest spans, "
          f"{len(key_digests)} digests, and the byte accounting agree with "
          f"{source}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
