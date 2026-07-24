# h5policy

`h5policy` is a GNU poke policy workbench for HDF5 metadata preflight. It parses
HDF5 bytes independently of `libhdf5`, validates the metadata it can reach, applies
a security profile, and emits a stable JSON decision.

Files with an HDF5 user block are supported. The superblock is discovered at a
legal boundary and base-relative HDF5 addresses are translated to physical file
offsets before metadata is mapped.

The tool is intentionally a metadata-only boundary:

- no libhdf5 calls
- no plugin loading
- no decompression
- no external file opens
- no repair
- no writes
- no application deserialization

That boundary is the point. `h5policy` is meant to answer "what would this file
make an HDF5 stack do?" before application code, filters, VFDs, external links,
or payload decoders get a chance to run.

## Quick Start

Run from the repository root:

```sh
./h5policy/tools/h5policy --profile untrusted-strict file.h5
./h5policy/tools/h5policy --profile trusted-fast file.h5
./h5policy/tools/h5policy --profile legacy file.h5
./h5policy/tools/h5policy --profile forensic --continue-after-rejection file.h5
./h5policy/tools/h5policy --profile trusted-fast --max-walk-seconds 60 file.h5
```

Output is JSON (the machine-readable result); it is the only format, so no flag
is required.  `--json` is still accepted as a no-op for backward compatibility.

Useful mode flags:

- `--strict` / `--non-strict` force GNU poke strict or non-strict mapping.
- `--continue-after-rejection` keeps walking after policy, resource,
  unsupported, or corruption findings so diagnostics include every reachable
  issue.
- `--max-walk-seconds N` overrides the selected profile's internal wall-clock
  walk budget. The wrapper hard timeout is set to `N + 30` seconds.

## Decisions

Exit codes are part of the interface:

```text
0   accept
1   accept_with_warnings
2   reject_corrupt
3   reject_policy
4   reject_resource
5   unsupported_coverage_gap
70  internal_error
```

`unsupported_coverage_gap` is a bounded answer, not a silent accept. It means the
file reached a recognized HDF5 feature that is not yet decoded deeply enough for
the selected policy.

JSON output includes:

- `schema_version`: the integer report-contract version (currently `1`).
- `decision`: the final classification.
- `geometry`: physical file bytes, the superblock's declared EOA, the effective
  address ceiling used by validation, and bytes physically trailing the EOA.
  Values that cannot be established are JSON `null`.
- `analysis`: whether the reachable walk completed, why it stopped, whether
  continuation was enabled, and whether the finding list was truncated.
- `findings`: stable finding codes and locations. Comparison-based findings can
  also include typed `evidence` with a field name, actual and expected integer
  values, the required comparison, and byte-precise supporting locations.
- `features`: security-relevant constructs such as external links, external
  storage, VDS, dynamic filters, unknown messages, maximum rank, and maximum
  logical dataset bytes.
- `metrics`: traversal and accounting counters used by profile budgets.

Evidence comparisons currently use `equal` and `less_than_or_equal`; the
finding means the reported `actual` value did not satisfy that comparison
against `expected`. Each evidence location has a `role`, byte `offset`, and
byte `length`. `actual` and `expected` mean the bytes directly encode that
value; `actual_source` and `expected_source` identify fields contributing to a
derived value such as a product.

Trailing bytes are informational. They are outside the declared HDF5 address
space and do not produce a finding by themselves.

## In-process consumer API

Consumers that load `h5_policy.pk` should call `h5policy_analyze` and inspect
the result through the read-only `h5policy_result_*` functions defined in
`pickles/h5_consumer.pk`. The API exposes the decision, exit code, findings,
location validity, typed integer evidence and its supporting byte ranges,
truncation state, reachability queries, and explicit walk
start/completion/stop state as scalars and strings.
The parallel finding and traversal vectors remain implementation details. The
new `h5policy_result_continue_after_rejection` accessor has the deprecated
`h5policy_result_continue_after_corruption` spelling as an API alias.

## Profiles

Profiles differ in feature policy and resource budgets, not in whether corrupt
metadata is rejected. A truncated or checksum-bad file is corrupt under every
profile.

For an implementation-level reference covering every current profile field,
including its scope, sentinel behavior, finding class, and test coverage, see
[`H5PolicyProfile`: Current Semantics](docs/H5PolicyProfile.md).

| Profile            | Mapping     | Resource / analysis budgets          | Feature policy                         |
| ------------------ | ----------- | ------------------------------------ | -------------------------------------- |
| `legacy`           | strict      | unlimited data; bounded analysis     | all features allowed                   |
| `trusted-fast`     | strict      | generous; bounded analysis           | external refs / VDS / filters allowed  |
| `untrusted-strict` | strict      | tight                                | denied by default                      |
| `forensic`         | non-strict  | deep but bounded                     | never follows refs; reports anomalies  |

Examples:

- An external-link file is rejected by `untrusted-strict`, but accepted by
  `trusted-fast` and `legacy`.
- A very large logical dataset can be rejected by `untrusted-strict` resource
  budgets while remaining structurally valid.
- `untrusted-strict` also rejects denial-of-service resource shapes such as
  many very small logical chunks, and high reachable-metadata-to-file-size
  ratios after an absolute metadata floor.
- `forensic` favors complete reporting over early exit, but still never follows
  external references or decodes payload data.  It additionally sweeps the raw
  bytes for structures that the reachability walk cannot see -- currently
  orphaned global heap collections (`GCOL`) whose object list does not advance,
  which would hang a consumer that loads them (`H5_RESOURCE_GLOBAL_HEAP_INFINITE_LOOP`,
  reported as a resource/denial-of-service hazard).  The default profiles follow
  references only, so they correctly accept a file whose sole defect is an
  unreachable heap.

## Validation Coverage

Current coverage includes:

- HDF5 superblocks, EOF/base-address geometry, and v2/v3 superblock checksums.
- Object headers, continuation chunks, object-header checksums, message prefix
  bounds, and reachable object traversal with visited sets.
- Dataspace, datatype, layout, filter pipeline, fill value, link, attribute,
  both modification-time forms, B-tree K override, reference-count,
  free-space info, and metadata cache image message/container envelopes.
  Cached metadata bodies remain outside decode coverage, as described in
  [Metadata cache-image hard boundary](#metadata-cache-image-hard-boundary).
  Driver-info envelopes are validated and then explicitly refused because
  their VFD bodies can name member files outside the single-file validation
  boundary.
- Compact hard links, dense link storage, dense attribute storage, old-style
  group metadata, and chunk-index metadata. Dense storage covers both the name
  indexes and recursive type-6/type-9 creation-order B-trees, including
  checksums, subtree totals, heap-ID resolution, and cross-index identity;
  chunk coverage includes recursive raw-data v2 B-trees and complete
  extensible-array block graphs.
- File-global Shared Object Header Message metadata: `SMTB` directories,
  `SMLI` record lists, recursive type-7 v2 B-trees, managed-message heap-ID
  resolution, fractal-heap envelopes, and complete huge-object index trees.
  Every recursive SOHM node is independently bounded by range, checksum,
  visited-node, depth, operation/time, and accounted-metadata limits.
- File-global free-space managers named by the file-space-info message: each
  `FSHD` header and its `FSSE` serialized section list are range-checked,
  checksummed, and metadata-accounted, and every free section's extent and
  class type is validated.  Fractal-heap (non-file) managers, reached from a
  heap header rather than the file-space-info message, remain a coverage gap.
- Logical dataset byte accounting kept separate from raw storage accounting, so
  datatype semantics can be compared against `libhdf5` while layout checks still
  use on-disk storage size.

### Metadata cache-image hard boundary

A metadata cache image (`MDCI`) is a second serialization of live metadata.
Its entries can shadow the ordinary bytes at the same logical file addresses,
so parsing those backing bytes as if they were still live can manufacture false
corruption findings.

h5policy validates the cache-image message and the bounded container information
needed to traverse it safely: the image extent, block signature/version/flags,
declared length, entry count, entry envelopes, dependency counts and list
sizes, body extents, and trailing layout. It records each validated
`(address, length)` shadow range. It does **not** decode the cached entry bodies
or validate their metadata semantics.

That missing body decoder is a hard coverage boundary shared by every profile,
not an `allow_*` feature policy:

- a structurally valid file containing a cache image returns exit `5` with
  decision `unsupported_coverage_gap` and finding
  `H5_UNSUPPORTED_PICKLE_COVERAGE_GAP`;
- `analysis.complete` and `analysis.walk_completed` are `false`;
- the default fail-fast profiles report `analysis.stop_reason: "rejection"`;
- with continuation enabled (including the `forensic` default), the walk skips
  shadowed addresses, continues checking reachable unshadowed metadata, and
  finishes with `analysis.stop_reason: "cache_image_coverage_gap"`; and
- `--continue-after-rejection` changes diagnostic traversal only. It never
  decodes the cached bodies and never converts this refusal into an acceptance.

Corruption found in the decoded message or container envelope can still produce
`reject_corrupt`, which outranks the unsupported finding. In either case,
consumers must not treat the file as preflight-approved while cached bodies
remain unvalidated.

Checksum coverage includes the HDF5 Jenkins checksums used by:

- v2/v3 superblocks
- v2 object headers and continuation chunks
- chunk-index headers, v2 B-tree internal/leaf nodes, and extensible-array
  index/secondary/data blocks and initialized pages
- dense metadata fractal heaps: `FRHP`, `FHDB`, `FHIB`
- dense metadata v2 B-trees: `BTHD`, `BTLF`, `BTIN`
- SOHM master tables/lists (`SMTB`, `SMLI`), fractal-heap headers (`FRHP`),
  and type-7/huge-object v2 B-tree headers and internal/leaf nodes

### Known blind spots

Some defects live strictly beyond a metadata-only boundary and are reported as
`unsupported_coverage_gap` rather than `reject_corrupt`, even when `libhdf5`
crashes on them:

- **Metadata cache-image bodies.** The message, container, entry envelopes, and
  shadow ranges are validated, but each cached entry body remains opaque. This
  is the [hard boundary described above](#metadata-cache-image-hard-boundary):
  continuation can preserve findings from unshadowed metadata but cannot make
  the analysis complete.

- **Encoded SOHM message bodies.** h5policy completely walks the type-7 shared
  index and the heap's huge-object index, validating record layouts, object
  extents, filter masks, checksums, and traversal budgets. Shared wrappers are
  currently resolved only when their eight-byte ID names an unfiltered managed
  heap object. A wrapper naming a huge, tiny, or filter-encoded heap object is
  refused as unsupported because validating its message payload would require
  an additional body decoder (and, for filtered objects, decompression).

- **Filtered dense link/attribute fractal heaps.** When a dense group's or
  object's fractal heap declares an I/O filter pipeline, the link/attribute
  records live inside a filter-compressed direct block. Resolving them means
  reversing the pipeline (decompressing untrusted bytes), which h5policy does
  not do. h5policy validates everything it can see in metadata — the pipeline
  descriptor, the header checksum, the direct-block checksum flag (see
  `H5_CORRUPT_FILTERED_HEAP_NO_DBLOCK_CHECKSUM`) — but a fault that only appears
  *after* decoding, such as a decoded direct block whose size does not match the
  heap's declared block size, is invisible to it. Such a file can crash some
  `libhdf5` versions during dense iteration (e.g. an invalid free in
  `H5G__link_release_table`) while h5policy can only answer "unsupported." The
  coverage gap is still a refusal, not an accept: a consumer honoring it will
  not process the file. The differential harness accepts that explicit refusal
  under invariant A' while retaining a classification warning when libhdf5
  rejects the same file as corrupt.

- **Vlen and reference data global heaps.** A dataset's variable-length or
  reference elements point into a global heap collection (`GCOL`) through heap
  IDs stored in the dataset's *raw data*, which h5policy never reads. It
  validates a `GCOL` only when the reference lives in metadata (the VDS layout
  message; see `h5_vds.pk`) or when the collection is *orphaned* and caught by
  the forensic sweep (`H5_RESOURCE_GLOBAL_HEAP_INFINITE_LOOP`). A malformed but
  data-reachable collection is otherwise invisible, so unlike the filtered-heap
  gap above this one surfaces as an *accept*, not a coverage-gap refusal. That
  is still sound under invariant A': the differential oracle (`introspect` in
  `h5policy-diff`) also reads only metadata and reports such a file as opened, so
  a consumer that goes on to read the data gets libhdf5's own error or
  denial-of-service behavior, which a metadata-only preflight does not model.

## Embedding h5policy

`h5policy_run` is the command-line entry point: it opens the file named by
`h5policy_file_name`, analyzes it, and prints the JSON report plus the exit-code
marker the shell wrapper reads.

In-process consumers use the seam underneath it:

```text
fun h5policy_analyze = (int ios, H5PolicyProfile profile) H5WalkContext
```

`h5policy_analyze` takes an IOS the caller already opened and prints nothing.
The decision, exit code, and findings are left in the `h5policy_*` globals
(`h5policy_decision`, `h5policy_exit_code`, and the parallel
`h5policy_finding_severities` / `_codes` / `_classes` / `_offsets` / `_objects` /
`_messages` arrays); the returned `H5WalkContext` carries the walk metrics.
Findings and traversal state are reset on entry, so each call reports exactly
what that analysis found.

This exists because GNU poke refuses a second IOS on an already-open file, so a
consumer holding the file open — `h5explain`, for instance — cannot call
`h5policy_run`. Two constraints come with it:

- Pass offsets and scalars, not mapped values. `load` re-executes a pickle, so
  a session that loads both `h5explain` and `h5policy` holds two bindings of the
  shared format types and globals (see the note in
  [`../pickles/stab.pk`](../pickles/stab.pk)). Values mapped by one side are not
  interchangeable with the other's types.
- The caller owns the IOS and closes it. `h5policy_analyze` never opens or
  closes one.

`tests/unit_seam.pk` pins these properties.

## Companion Tools

See the [h5policy tool guide](docs/README.md) for command usage, fuzzing
workflows, and a detailed explanation of the differential cross-invariants.

- [`tools/h5policy`](tools/h5policy): the policy oracle.
- [`tools/h5policy-diff`](tools/h5policy-diff): compares h5policy decisions and
  extracted features with `libhdf5` via `h5py` and optional HDF5 command-line
  tools.
- [`tools/h5policy-fuzz`](tools/h5policy-fuzz): structure-aware fuzzer for
  h5policy, using `libhdf5` via `h5py` as the oracle.
- [`tools/h5policy-crashfuzz`](tools/h5policy-crashfuzz): mutates files against
  installed HDF5 tools and triages crashers with h5policy.
- [`tools/h5policy-fuzzlib`](tools/h5policy-fuzzlib): shared fuzzing engine
  (mutation strategies, seed loading, guided corpus) imported by both fuzzers.
- [`tools/h5policy-gencorpus`](tools/h5policy-gencorpus): regenerates the valid,
  malformed, policy, resource, coverage, integration, and CVE regression
  fixtures.

See [`tests/README.md`](tests/README.md) for the corpus, differential harness,
and fuzzing workflow.
