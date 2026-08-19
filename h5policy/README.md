# h5policy

`h5policy` is a GNU poke policy workbench for HDF5 metadata preflight. It parses
HDF5 bytes independently of `libhdf5`, validates the metadata it can reach, applies
a security profile, and emits a stable JSON decision.

Files with an HDF5 user block are supported. The superblock is discovered at a
legal boundary and base-relative HDF5 addresses are translated to physical file
offsets before metadata is mapped. This includes the addresses a metadata cache
image records for the entries it shadows: they are base-relative like any other
file address, and the corpus covers a user block and a cache image together
(`valid/userblock_cache_image.h5`) because only their combination reaches that
translation.

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
./h5policy/tools/h5policy --profile untrusted-strict examples/file.h5
./h5policy/tools/h5policy --profile trusted-fast examples/file.h5
./h5policy/tools/h5policy --profile legacy examples/file.h5
./h5policy/tools/h5policy --profile forensic --continue-after-rejection examples/file.h5
./h5policy/tools/h5policy --profile trusted-fast --max-walk-seconds 60 examples/file.h5
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
the selected policy, or a legal representation the h5policy compatibility target
conservatively declines to pass to the selected `libhdf5`.

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
| `forensic`         | non-strict  | deep but bounded                     | no external traversal; reports anomalies |

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
  reported as a resource/denial-of-service hazard). The default profiles inspect
  only metadata reachable from the superblock, so they accept a file whose sole
  defect is an unreachable heap.

## Validation Coverage

Current coverage includes:

- HDF5 superblocks, EOF/base-address geometry, status flags, root and extension
  addresses, and v2/v3 superblock checksums.
- Object headers, continuation chunks, object-header checksums, message prefix
  bounds and alignment, message flags, group link-storage consistency, and
  reachable-object traversal with visited sets. Unknown message IDs follow the
  read-only `libhdf5` flag semantics described under
  [Current coverage boundaries](#current-coverage-boundaries).
- Dataspace, datatype, layout, filter pipeline, fill value, link, attribute,
  both modification-time forms, B-tree K override, reference-count,
  free-space info, and metadata cache image message/container envelopes and
  replayed cached bodies. Checks include datatype class flags and nested size
  relationships, link names/types/flags, layout dimensionality and storage
  extents, fill flags, and the complete filter-descriptor envelope.
- Compact hard links, dense link storage, dense attribute storage, old-style
  group metadata, and every defined chunk-index representation. Dense storage
  covers both name indexes and recursive type-6/type-9 creation-order B-trees,
  including checksums, subtree totals, managed fractal-heap-ID resolution, and
  cross-index identity. Chunk coverage includes v1 and recursive raw-data v2
  B-trees, fixed arrays, complete extensible-array block graphs, and the
  index-less single-chunk and implicit forms.
- File-global Shared Object Header Message metadata: `SMTB` directories,
  `SMLI` record lists, recursive type-7 v2 B-trees, and managed, tiny, and
  unfiltered huge-message heap-ID resolution. Fractal-heap envelopes and
  complete huge-object index trees are validated before a body is dispatched.
  Every recursive SOHM node is independently bounded by range, checksum,
  visited-node, depth, operation/time, and accounted-metadata limits.
- File-global free-space managers named by the file-space-info message: each
  `FSHD` header and its `FSSE` serialized section list are range-checked,
  checksummed, and metadata-accounted, and every free section's extent and
  class type is validated. Fractal-heap managers named by `FRHP` headers are
  likewise walked as metadata; their sections are checked against the heap's
  logical managed-space extent rather than against file offsets.
- Virtual-dataset layout messages and their in-file `GCOL` mapping collections,
  including collection/object envelopes, alignment and progress, serialized
  selections, source names, and mapping counts. Source files named by a mapping
  are still never opened.
- Logical dataset byte accounting kept separate from raw storage accounting, so
  datatype semantics can be compared against `libhdf5` while layout checks still
  use on-disk storage size. Datatype validation accepts message versions 1–5,
  including bounded recursion through homogeneous rectangular Complex class
  (11) base types.

For the invariant-by-invariant inventory and its fixtures, use
[`registry/validation-coverage.yml`](../registry/validation-coverage.yml) and
the [finding registry](../registry/findings/README.md). This README summarizes
the user-visible boundary rather than duplicating that machine-checked catalog.

### Metadata cache-image hard boundary

A metadata cache image (`MDCI`) is a second serialization of live metadata.
Its entries can shadow the ordinary bytes at the same logical file addresses,
so parsing those backing bytes as if they were still live can manufacture false
corruption findings.

h5policy validates the cache-image message and bounded container information:
the image extent, block signature/version/flags, declared length, entry count,
entry envelopes, dependency counts and list sizes, body extents, trailing
layout, and the image checksum. It then replays all validated cached entry bodies
through the ordinary bounded metadata decoder at its logical `(address, length)`
range. This replaces the shadowed backing ranges through an in-memory read overlay over the original file: it never
writes the input, opens an external file, or materializes a whole-file copy.

Consequently, a structurally valid cache image can return exit `0` and
`accept`; `analysis.complete` and `analysis.walk_completed` are `true`. Cached
object headers, trees, heaps, and indexes receive the same semantic and
cross-reference checks as their ordinary on-disk counterparts. A corrupt MDCI
envelope, checksum, or replayed body produces `reject_corrupt`.
If an internal cache-client body cannot be reached by a type-aware decoder,
h5policy retains an explicit `unsupported_coverage_gap` rather than approving
the image.

`--continue-after-rejection` still controls only diagnostic traversal. It does
not weaken cache-image validation or alter an acceptance decision.

Checksum coverage includes the HDF5 Jenkins checksums used by:

- v2/v3 superblocks
- v2 object headers and continuation chunks
- chunk-index headers, v2 B-tree internal/leaf nodes, and extensible-array
  index/secondary/data blocks and initialized pages
- dense metadata fractal heaps: `FRHP`, `FHDB`, `FHIB`
- dense metadata v2 B-trees: `BTHD`, `BTLF`, `BTIN`
- SOHM master tables/lists (`SMTB`, `SMLI`), fractal-heap headers (`FRHP`),
  and type-7/huge-object v2 B-tree headers and internal/leaf nodes

### Current coverage boundaries

The old "blind spots" list mixed explicit refusals, compatibility guards, and
data that the metadata-only contract deliberately never reads. Those outcomes
are materially different.

The following boundaries are explicit refusals rather than silent acceptance.
They emit an unsupported finding or stop with `unsupported_coverage_gap` when
no higher-precedence corruption, policy, or resource finding determines the
final decision:

- **Wide superblock fields.** The complete policy walk supports 2-, 4-, and
  8-byte offset and length fields. Other format widths are refused during
  fixed-prefix preflight before they can size a later map. In particular,
  `sizeof_lengths = 16` is legal and h5policy can narrow representable values,
  but the selected `libhdf5` target's shared length decoder does not implement
  that width. Its refusal is a compatibility guard, not a corruption claim.
- **Driver-specific metadata.** Driver-info block/message envelopes, versions,
  sizes, extents, and placement are checked, but the VFD-specific body can name
  member files. h5policy does not interpret it or open those files.
- **Skippable unknown object-header messages.** The unconditional
  fail-if-unknown flag (`0x80`) makes an unknown ID corrupt for this read-only
  path. The read/write-only flag (`0x08`) does not. A prefix-valid unknown
  message is denied by profiles with `allow_unknown_messages = 0`; a profile
  that permits it still returns a coverage gap because the bounded raw body has
  no validator.
- **Filtered fractal-heap bodies.** h5policy validates the heap and filter
  envelopes for SOHM, dense links, and dense attributes, including checksums
  and the required direct-block checksum flag. It does not reverse the filter
  pipeline, so message/link/attribute bodies inside compressed blocks remain
  uninspected. A defect visible only after decompression therefore remains an
  explicit refusal.
- **Unresolved heap and shared-message forms.** Dense link/attribute indexes
  resolve managed fractal-heap IDs; huge and tiny dense IDs remain unsupported.
  SOHM resolves managed, tiny, and unfiltered huge IDs, but refuses a heap body
  whose legal form cannot be resolved. Nested shared-message indirection is
  also capped at 32 levels.
- **Unreached cache-image clients.** A valid metadata cache image normally
  replays and accepts. If any serialized entry body cannot be reached through a
  type-aware decoder, the whole analysis is refused rather than treating the
  overlay itself as validation.
- **Analysis exhaustion.** Reaching the deterministic operation ceiling, the
  internal walk deadline, or the wrapper hard timeout is an unsupported result:
  it says validation did not finish, not that the file is structurally corrupt.

Other data is intentionally outside the preflight graph and therefore does not
automatically produce a finding:

- **Dataset payload bytes.** h5policy validates layout and filter metadata but
  never reads or decompresses raw dataset data. This includes global-heap IDs
  embedded in variable-length and reference elements. The VDS mapping `GCOL`
  is different because its reference is metadata and is validated end to end;
  the forensic sweep separately recognizes the zero-progress `GCOL` shape
  wherever its signature occurs. Other malformed payload-reachable collections
  remain outside the preflight and can coexist with an accepted metadata
  decision.
- **External targets.** External links, external storage, and VDS source paths
  are classified from their metadata, then allowed or denied by the profile.
  h5policy never opens the named target, so an acceptance does not validate its
  existence, content, or behavior.

Consumers must therefore interpret `accept` as approval of the reachable
metadata under the selected profile, not as a promise that later payload reads
or external-resource activation will succeed safely.

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
  fixtures. Cache-image helper executables automatically match an
  AddressSanitizer-enabled `h5cc`; sanitizer runtime settings stay scoped to
  those helpers rather than the Python and GNU poke test harness.

See [`tests/README.md`](tests/README.md) for the corpus, differential harness,
and fuzzing workflow.
