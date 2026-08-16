# h5patch

`h5patch` is an experimental repair planner for HDF5 metadata damaged by
interrupted writes, application crashes, or similar failures.  It is designed to
work with the GNU poke based metadata validators in this repository: `h5patch`
proposes byte-level repairs, applies only approved plans, and verifies the
result with `h5policy`.

The tool is conservative.  Its goal is metadata coherence, not pretending that
missing raw data was recovered.

Like `h5policy`, `h5patch` uses a small shell driver.  The repair catalog,
metadata inspection, checksum calculation, and byte writes live in GNU poke
pickles.

## Workflow

Create a what-if patch plan:

```sh
./h5patch/tools/h5patch plan damaged.h5 -o repair.plan.json
```

Review it as Markdown:

```sh
./h5patch/tools/h5patch explain repair.plan.json
```

Apply to a repaired copy and write an audit log:

```sh
./h5patch/tools/h5patch apply damaged.h5 repair.plan.json \
  --output repaired.h5 \
  --log repair.log.jsonl
```

Verify any file with `h5policy`:

```sh
./h5patch/tools/h5patch verify repaired.h5
```

## Plan Format

The authoritative plan format is canonical JSON emitted by the poke repair
planner.  JSON keeps byte offsets, before/after values, and preconditions
unambiguous; human-readable summaries can be rendered from it.

Each action contains:

- `kind`: repair operation category, such as `replace_bytes`,
  `set_uint_le`, or `recompute_checksum`.
- `target`: HDF5 structure, object path if known, and structure offset.
- `preconditions`: byte checks that must match before the action can run.
- `writes`: exact byte ranges with `old_hex` and `new_hex`.
- `reason`: why the repair is proposed.
- `confidence`: `high`, `medium`, or `speculative`.

`h5patch apply` regenerates the plan for the current input and fails closed if
the approved JSON does not match exactly.  The poke applier then performs the
same catalog repairs against the output copy and `h5policy` verifies the result.

## Repair Catalog

This is the authoritative and exhaustive list of implemented repair classes.
The catalog intentionally favors byte-level changes backed by complete
`h5policy` reachability and exact on-disk evidence:

- restore the HDF5 file signature when the surrounding superblock fields are
  plausible.  Plausibility requires more than version and address widths: the
  candidate body must also record its own location as its base address and name
  a root object header inside the file.  This is what keeps the byte-0 fallback
  off a user block, whose application bytes are not a superblock even when they
  happen to look like one;
- normalize a mismatched v2/v3 superblock base address to the discovered
  superblock offset and reseal the superblock;
- clear stale v2/v3 superblock file-consistency flags;
- recompute v2/v3 superblock Jenkins checksums;
- recompute reachable v2 object-header Jenkins checksums reported by
  `h5policy`;
- rewrite a mismatched stored element size in a reachable v4 chunk-layout
  message from its unique inline datatype message, atomically with any needed
  v2 object-header checksum update;
- rewrite scale-offset and atomic N-bit filter parameters when `h5policy`
  provides an unambiguous typed expected value, atomically with any needed v2
  object-header checksum update;
- rewrite free-space header serialized-section totals from a structurally
  confirmed section-list recount for client 1, when there are no ghost
  sections, then reseal the header;
- rewrite flagged v1 object-header message counts to the counted message total;
- rewrite symbol-table node (`SNOD`) symbol counts to the contiguous valid entry
  count;
- rewrite depth-0 v2 B-tree header total-record counts to the root-record
  count, resealing the B-tree header checksum when needed;
- recompute trailing Jenkins checksums for reached metadata structures when
  `h5policy` identifies both the exact checksum field and its complete source
  byte range.  This includes deeper free-space, v2 B-tree, extensible-array,
  and shared-message structures.

Semantic object-header repairs are grouped with their checksum update in one
plan, so applying a plan does not intentionally create a checksum-valid but
semantically invalid intermediate file.  Evidence-dependent repairs fail
closed when analysis or reachability is incomplete, evidence is ambiguous, or
the affected structure has unrelated corruption.

Future repair classes can add B-tree rebuilds, orphan pruning, continuation
chunk repair, end-of-address expansion, and chunk-index reconstruction behind
the same plan/apply/log interface.

## User blocks

Files with an HDF5 user block are supported.  The superblock is located the way
`h5policy` and libhdf5 locate it -- byte 0, then 512, 1024, 2048, and so on --
and the plan reports the discovered `superblock_offset`.

Every address stored in HDF5 metadata is relative to the superblock's base
address, so a repair that follows one (a symbol-table entry's object header, a
v2 B-tree's root node, a free-space section list) must translate before reading
bytes.  An untranslated read lands a base short of its target on a user-block
file, the structure check fails, and the repair is quietly not offered rather
than misapplied.  `h5patch/tests/test_h5patch.py` pins this: the SNOD and
depth-0 v2 B-tree count repairs each run twice, once with a user block and once
without.
