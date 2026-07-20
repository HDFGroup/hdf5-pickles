# A CVE strategy for the HDF5 library

Are we winning the war against CVEs? The HDF5 library has a long history of CVE fixes, but the fixes are often isolated and ad hoc. This document proposes a more systematic approach to CVE mitigation.

The most practical strategy is a capability-separated pipeline, introduced behind existing decode choke points and adopted one complete record type at a time:

```text
bounded read
  → RawSlice + cursor
  → RawRecord + inert ChildRefs
  → semantic/policy validation
  → opaque ValidatedRecord
  → native materialization and activation
```

This implements the contract in the [bounded raw decode design note](https://github.com/HDFGroup/hdf5-pickles/blob/main/docs/What%20is%20bounded%20raw%20decode.md) without requiring a big-bang rewrite.

## Target architecture

1. Bounded byte substrate

Create an internal raw-decoding package with:

- A half-open cursor `{base, size, position, absolute_offset}`. Bounds checks use `n <= size - position`, avoiding the pervasive `p + size - 1` idiom and its zero-length underflow hazards.
- Checked add, multiply, align, address-range, string, and allocation helpers.
- `RawSlice {owner, offset, length}` objects tied to immutable, owned input.
- A decode context carrying per-record and cumulative limits: bytes read, allocations, nodes, depth, child references, loop steps, strings, members, findings, and so on.
- A bounded arena for raw IR that is charged before every allocation.
- Stable findings containing category, code, severity, absolute offset, and field path.

Raw decoders should accept bytes, explicit extent, a validated file-geometry snapshot, and the decode context. They should not receive `H5F_t *`, callback tables, or anything else capable of I/O or activation.

2. Inert references and bounded traversal

A raw decoder may identify a continuation, heap, shared message, B-tree, external link, or chunk index, but returns it only as a typed `ChildRef`. A separate coordinator owns metadata reads and maintains:

- A work queue rather than uncontrolled recursion.
- File-range checks before reads.
- Visited keys such as `(record-kind, address)`.
- Depth, hop, node, byte, allocation, and step budgets.
- Per-structure cycle rules: a link-graph cycle may be valid, while a B-tree or cache-dependency cycle may be corrupt.

The raw layer therefore cannot follow external paths, load filters, decompress data, or mutate the metadata cache.

3. Semantic validation with type-state enforcement

Separate three kinds of rules:

- Hard safety invariants: bounds, checked arithmetic, forward progress, and allocation limits. These can never be relaxed.
- Format semantics: versions, flags, cardinalities, datatype relationships, duplicate messages, layout/dataspace compatibility, and so forth.
- Policy/resource rules: external traversal, dynamic plugins, decompression, and configurable quotas.

Successful validation should produce an opaque internal `Validated<T>` wrapper, not a Boolean. Materializers accept that wrapper, making accidental raw-to-native construction difficult.

For a dataset, validation should also have an aggregate gate covering datatype × dataspace × layout × pipeline × fill/EFL/VDS before the dataset object initializes layout or index operations.

4. Activation after validation

Plugin lookup, external-file opening, decompression, user callbacks, cache insertion, and public identifier registration happen only after validation.

Compressed metadata needs a separate bounded transform stage: authorize the transform, enforce output and expansion-ratio limits, produce another explicit slice, and raw-decode that slice. Decompression does not belong inside a raw decoder.

## Why this fits the present code

There is already a strong migration seam: `H5O_mesg_t` keeps `raw/raw_size` separately from `native`, while `H5O_LOAD_NATIVE` centralizes lazy native construction in [H5Opkg.h](https://github.com/HDFGroup/hdf5/blob/4d666721f42f8f739152021a23775a16d676c8b1/src/H5Opkg.h#L163) and [H5Opkg.h](https://github.com/HDFGroup/hdf5/blob/4d666721f42f8f739152021a23775a16d676c8b1/src/H5Opkg.h#L236).

Initially, add a companion raw-operations table keyed by message ID:

```text
raw_decode → validate → materialize
```

This avoids changing every positional `H5O_msg_class_t` initializer immediately. Once a message class is migrated, `H5O_LOAD_NATIVE` uses the new path. If raw decode or validation fails, it must never retry through the legacy decoder.

The current raw/native split is only a bridge. Object-header deserialization still allocates and mutates `H5O_t` while scanning messages in [H5Ocache.c](https://github.com/HDFGroup/hdf5/blob/4d666721f42f8f739152021a23775a16d676c8b1/src/H5Ocache.c#L1170). The final form should therefore introduce an `H5O_raw_ohdr_t`, validate its complete envelope and continuation graph, and only then promote it to `H5O_t`.

Other useful choke points are:

- Central pre-read and pre-allocation guards in [H5Centry.c](https://github.com/HDFGroup/hdf5/blob/4d666721f42f8f739152021a23775a16d676c8b1/src/H5Centry.c#L1010).
- Continuation traversal budgets in [H5Oint.c](https://github.com/HDFGroup/hdf5/blob/4d666721f42f8f739152021a23775a16d676c8b1/src/H5Oint.c#L1015).
- Recursive datatype parsing in [H5Odtype.c](https://github.com/HDFGroup/hdf5/blob/4d666721f42f8f739152021a23775a16d676c8b1/src/H5Odtype.c#L109).
- Shared messages, which currently perform secondary reads during decode, in [H5Oshared.c](https://github.com/HDFGroup/hdf5/blob/4d666721f42f8f739152021a23775a16d676c8b1/src/H5Oshared.c#L289).
- Cache images, which should be decoded and validated completely before transactional insertion, in [H5Cimage.c](https://github.com/HDFGroup/hdf5/blob/4d666721f42f8f739152021a23775a16d676c8b1/src/H5Cimage.c#L2435).

## Incremental roadmap

| Phase | Scope | Deliverable |
|---|---|---|
| 0. Foundation | Cursor, checked arithmetic, slices, budgets, findings, arena, direct-byte test harness | No public behavior change; reusable infrastructure for CVE fixes |
| 1. Vertical pilot | One complete explicit-size record, preferably datatype through `H5Tdecode2()` or whichever record is affected by the next CVE | Proves raw → validate → materialize and exact truncation testing |
| 2. Object-header envelope | Prefix, message envelopes, checksums, continuation `{address,size}` references | Validate the whole envelope before `H5O_t` mutation; bounded queue and visited set |
| 3. Core messages | Datatype, dataspace/selection, attribute, layout, pipeline, fill | Per-message certificates plus object-level dataset validation |
| 4. Side-effectful and graph structures | Shared messages, heaps, SOHM, free-space managers, B-trees, chunk indexes, external links, EFL and VDS | All secondary access expressed as inert references; no raw-stage activation |
| 5. Transactional/bootstrap work | Cache images and superblock/file bootstrap | Decode-all/validate-all/promote; enables an honest file-level bounded guarantee |
| 6. Public adoption | Profiles, forensic file-image API, size-aware replacement APIs | Opt-in soak, then default once coverage and compatibility criteria are met |

`H5Tdecode2()` is a particularly useful pilot because it already has an explicit extent. Its wrapper-length handling in [H5T.c](https://github.com/HDFGroup/hdf5/blob/4d666721f42f8f739152021a23775a16d676c8b1/src/H5T.c#L3938) should receive an exhaustive truncation sweep. Size-less entry points such as [H5Sdecode](https://github.com/HDFGroup/hdf5/blob/4d666721f42f8f739152021a23775a16d676c8b1/src/H5S.c#L1531), `H5Pdecode`, and deprecated `H5Tdecode1` cannot provide this guarantee; eventually they need size-aware successors or explicit legacy status.

## Making each CVE a migration unit

For stable release branches, retain the smallest safe, backportable fix. On `develop`, use the same issue to migrate the smallest complete containing record:

1. Turn the PoC into a direct byte-array fixture.
2. Put extent and representation checks in raw decode.
3. Put cross-field or cross-record rules in semantic validation.
4. Require the validated token at the native constructor.
5. Assert the expected finding code and offset, plus zero native construction or external side effects.
6. Add the input to the per-decoder fuzz corpus and the full-file regression suite.

Maintain a coverage manifest by format record and version. In compatibility mode, explicitly unmigrated classes may temporarily use legacy decoding. A mode advertised as bounded must reject an unsupported required record rather than silently falling back. Unknown optional messages may remain bounded opaque records where forward compatibility allows it.

## Profiles and compatibility

Use one versioned decode profile instead of adding a flag for every check:

- `compat`: hard safety invariants plus historical semantic allowances and measured, generous limits.
- `strict`: specification conformance without repair-on-decode behavior.
- `forensic`: strict budgets, capped findings, no native materialization, plugin loading, external traversal, or user callbacks.

Existing `HDF5_STRICT_FORMAT_CHECKS` and `H5Pset_relax_file_integrity_checks` demonstrate the compatibility need, but they should not be allowed to weaken structural safety. Any historical “repair and mark dirty” behavior should become a post-validation normalization plan applied by the materializer.

Validation should remain lazy and per reachable record; a normal `H5Fopen()` should not require scanning the whole file.

## Acceptance tests

Every migrated decoder should have:

- Truncation at every byte position and `N-1/N/N+1` limit tests.
- Overflow, zero-length, trailing-data, deep nesting, non-progress, duplicate-reference, and cycle cases.
- Allocation and traversal budget exhaustion tests.
- Exact finding code, byte offset, and field-path assertions.
- Test hooks proving no materializer, cache mutation, plugin load, decompression, external open, or callback occurred on fatal validation.
- Differential tests showing valid inputs produce equivalent native state and canonical re-encoding.
- A dedicated in-memory fuzz target under fixed hardened limits, complementing the current full-pipeline [OSS-Fuzz HDF5 targets](https://github.com/google/oss-fuzz/tree/master/projects/hdf5) and existing [CVE workflow](https://github.com/HDFGroup/hdf5/blob/4d666721f42f8f739152021a23775a16d676c8b1/.github/workflows/cve.yml#L35).

The first three practical PRs would therefore be: the bounded substrate, one CVE-sized explicit-buffer pilot, and raw object-header envelopes plus bounded continuations. From that point onward, each CVE fix reduces the remaining legacy surface instead of adding another isolated guard.