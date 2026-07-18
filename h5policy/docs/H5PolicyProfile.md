# `H5PolicyProfile`: Current Semantics

This document describes the behavior of `H5PolicyProfile` and its nested
configuration groups as they are implemented today. It is a characterization
reference, not a proposal for future policy behavior. Where a field name
suggests broader behavior than the validators currently implement, the
narrower implemented behavior is documented.

The types and four built-in values are defined in
[`h5_profiles.pk`](../pickles/h5_profiles.pk). The effective option snapshot and
resolver are in [`h5_run_options.pk`](../pickles/h5_run_options.pk). The
command-line wrapper maps public profile names to the built-in values, and
[`h5_policy.pk`](../pickles/h5_policy.pk) selects and resolves them for a run.

Canonical literals shared by the declarative mappings and h5policy are defined
in [`h5_format_constants.pk`](../../pickles/h5_format_constants.pk). It is
loaded by `common.pk`, before both the mapping definitions and profile model.
It contains the fixed rank/layout ceilings and signatures consumed by both
layers. Executable constraints and structure-local constants remain beside
their structure definitions. None of these values are policy settings.

## Model structure

`H5PolicyProfile` contains four groups:

- `resources` (`H5ResourceLimits`) contains hard numeric resource, shape,
  depth, and walk-work ceilings;
- `heuristics` (`H5HeuristicPolicy`) contains the tiny-chunk and metadata-ratio
  thresholds;
- `features` (`H5FeaturePolicy`) contains the six `allow_*` switches; and
- `analysis_defaults` (`H5AnalysisDefaults`) contains three independent preset
  choices for run-analysis behavior.

`H5RunOptions` is deliberately outside `H5PolicyProfile`. At the beginning of
each invocation, `h5policy_resolve_run_options` combines the selected
`analysis_defaults` with CLI overrides and produces one effective value for
mapping strictness, continuation after corruption, and unreachable-metadata
sweeping. Walk deadlines and counters remain execution state rather than
profile or option fields.

This grouping is organizational. The field descriptions below generally use
the leaf field name; validator code accesses it through the group shown above.

## General behavior

`h5policy_profile_validation_error` validates a profile before file I/O. An
invalid selected profile emits `H5_INTERNAL_INVALID_PROFILE`, prints a normal
report, and returns without opening or validating the input file. Callers that
construct profiles directly can use `h5policy_profile_is_valid` first.

The validation text for invalid `analysis_defaults.nonstrict_mapping` and
`analysis_defaults.continue_after_corruption` values uses the leaf names
`default_nonstrict_mapping` and `default_continue_after_corruption`.

### Comparisons and saturation

Most numeric maxima are inclusive: a value equal to the limit is allowed, and
the finding is emitted when the value or accumulated sum would be greater than
the limit.

Counters using `h5policy_checked_add_u64` and derived sizes using
`h5policy_checked_mul_u64` saturate at the configured limit after emitting a
finding. Consequently, a reported metric can equal the limit rather than the
larger observed or derived value that caused the finding.

The sentinel conventions are not uniform:

- `0xffffffffffffffffUL` is used as the practical unlimited value for most
  counters and byte maxima.
- `0` disables `max_single_value_bytes` and the metadata-ratio percentage
  rules.
- `0` disables the tiny-chunk rule only when used for
  `min_logical_chunk_bytes`; `max_chunks_below_min_logical_bytes = 0` by itself
  does not disable that rule.
- `max_walk_seconds = 0` is invalid configuration.
- `max_walk_operations = 0` is invalid configuration.

### Findings and control flow

Emitting a finding updates the final decision but does not itself throw an
exception or stop the current validator. Some enforcement sites explicitly
return or decline to enqueue more work; others continue parsing the current
structure.

Without `--continue-after-rejection`, the main object-header breadth-first walk
stops before dequeuing its next object after any decision other than `accept` or
`accept_with_warnings`. Work already in progress inside the current object,
tree, index, pipeline, or continuation chain follows the control flow described
below. With continuation enabled, that main-walk early exit is disabled, but
explicit per-validator returns and the walk deadline still apply.

The JSON `analysis` object reports whether this walk started and completed, its
stop reason, the effective continuation setting, and finding truncation. This
makes a fail-fast rejection distinguishable from an exhaustive diagnostic pass.
`--continue-after-corruption` is retained as a deprecated CLI alias.

### Report schema and file geometry

Every machine-readable report carries integer `schema_version: 1`, including a
report synthesized by the shell wrapper after its hard wall timeout. The
version changes when an incompatible field shape, type, or meaning changes;
additive fields may retain the current version.

The `geometry` object makes the address boundary used during validation
explicit:

- `physical_bytes` is the byte length of the available file image;
- `declared_eoa` is the superblock's declared end-of-address value once that
  field has been decoded;
- `effective_ceiling` is `min(physical_bytes, declared_eoa)` when EOA is known,
  otherwise the physical size used before a superblock is available; and
- `trailing_bytes` is `max(physical_bytes - declared_eoa, 0)` when both inputs
  are known.

An unavailable value is JSON `null`, rather than zero. A bad signature therefore
has known physical bytes and an effective physical ceiling, but `null` EOA and
trailing-byte values. A profile rejected before file I/O has four `null` values.
A hard-timeout report retains the physical size when the wrapper can obtain it,
but reports the three in-pickle bounds as `null` because the killed process
cannot return its decoded state.

Physical bytes after the declared EOA are outside HDF5's address space. They are
reported for provenance and triage but do not cause a finding by themselves.

Comparison-based findings carry an `evidence.locations` array. Every entry has
a semantic `role`, absolute byte `offset`, and byte `length`. Roles `actual` and
`expected` mean the range directly encodes the corresponding integer. Roles
`actual_source` and `expected_source` identify encoded inputs to a derived value;
for example, a chunk-size overflow cites every dimension field multiplied into
the reported product. Constants and other values with no encoded byte range do
not receive a fabricated location. These locations are additive report fields
under schema version 1.

When several findings occur, decision precedence is:

```text
internal > corrupt > policy > resource > unsupported > warning > accept
```

Thus, for example, a dataspace that exceeds both the fixed rank ceiling and the
profile rank limit finishes as `reject_corrupt`, even though it also has a
resource finding.

## Built-in numeric presets

`UINT64_MAX` below means the literal `0xffffffffffffffffUL`. `disabled` means
that the enforcement site explicitly treats zero as off.

| Field | `untrusted-strict` | `forensic` | `trusted-fast` | `legacy` |
| --- | ---: | ---: | ---: | ---: |
| `max_accounted_metadata_bytes` | 256 MiB | 1 GiB | 4 GiB | `UINT64_MAX` |
| `max_logical_dataset_bytes` | 64 GiB | `UINT64_MAX` | 16 TiB | `UINT64_MAX` |
| `max_single_value_bytes` | 1 GiB | disabled | disabled | disabled |
| `max_object_count` | 100,000 | 1,000,000 | 10,000,000 | `UINT64_MAX` |
| `max_attribute_count` | 100,000 | 1,000,000 | 10,000,000 | `UINT64_MAX` |
| `max_object_header_chunks` | 1,024 | 4,096 | 65,536 | `UINT64_MAX` |
| `max_btree_depth` | 64 | 128 | 128 | `UINT64_MAX` |
| `max_link_traversal_depth` | 64 | 128 | 128 | 128 |
| `max_datatype_recursion_depth` | 64 | 128 | 128 | 128 |
| `max_filter_parameter_recursion_depth` | 64 | 128 | 128 | 128 |
| `max_chunk_count` | 10,000,000 | `UINT64_MAX` | `UINT64_MAX` | `UINT64_MAX` |
| `min_logical_chunk_bytes` | 4 KiB | 0 | 0 | 0 |
| `max_chunks_below_min_logical_bytes` | 4,096 | 0 | 0 | 0 |
| `max_filter_count` | 32 | 64 | 64 | `UINT64_MAX` |
| `max_rank` | 32 | 32 | 32 | 32 |
| `metadata_ratio_warn_percent` | 50 | 0 | 75 | 0 |
| `metadata_ratio_warn_min_bytes` | 1 MiB | 0 | 16 MiB | 0 |
| `metadata_ratio_reject_percent` | 75 | 0 | 0 | 0 |
| `metadata_ratio_reject_min_bytes` | 16 MiB | 0 | 0 | 0 |
| `max_walk_operations` | 10,000,000 | 50,000,000 | 50,000,000 | 100,000,000 |
| `max_walk_seconds` | 10 | 30 | 20 | 60 |

## Counter and byte limits

### `max_accounted_metadata_bytes`

This limits `H5WalkContext.metadata_seen`, a file-wide accumulator shared by the
main reachable-metadata walk. Each explicit accounting call adds a declared or
calculated metadata-structure size. If the addition would exceed the limit,
the counter becomes the limit and h5policy emits:

```text
H5_RESOURCE_ACCOUNTED_METADATA_BYTES (resource)
```

An accounting failure does not globally abort unrelated validation. Recursive
modern chunk-index walkers do stop following additional child edges once the
ceiling has been crossed, so an attacker cannot use an already-refused charge
to drive an unbounded graph walk.

The accumulator is not a count of all bytes read or mapped, and it is not a
complete unique-extent measure. Current accounting calls cover:

- the superblock mapping size;
- v1 and v2 root object-header extents;
- declared object-header continuation extents;
- old-style group v1 B-tree nodes and SNOD nodes;
- v1 chunk B-tree nodes;
- raw-data v2 B-tree headers and each fixed-size internal or leaf node;
- SOHM master tables, full configured record-list allocations, fractal-heap
  headers, and each type-7 or huge-object v2 B-tree header/internal/leaf
  allocation (list/node checksums still cover only their exact used prefixes);
- free-space manager `FSHD` headers and their full `FSSE` section-list
  allocations (the section-list checksum still covers only its used prefix);
- fixed-array chunk-index headers; and
- extensible-array headers, index blocks, secondary blocks, and complete data
  block allocations (including their page-checksum storage).

In particular, general byte mappings do not charge this counter automatically.
Dense fractal-heap/B-tree blocks, SOHM heap data blocks and encoded message
bodies, VDS global-heap objects, metadata-cache image bodies, and fixed-array
chunk-index data blocks are not uniformly included. Reaching the same
explicitly accounted structure through distinct paths is not guaranteed to be
globally deduplicated by the accounting helper.

Zero is an active zero-byte limit. The built-in unlimited preset uses
`UINT64_MAX`.

### `max_logical_dataset_bytes`

This is a per-dataset derived-size limit. Once both a dataspace and datatype are
known, h5policy calculates:

```text
dataset element count * datatype logical size
```

The logical size normally equals the datatype's stored element size. References
with the recognized compact on-disk encoding use 64 bytes as their logical size
to match the libhdf5-facing metric.

If the multiplication exceeds the profile limit, h5policy emits:

```text
H5_RESOURCE_LOGICAL_DATASET_BYTES (resource)
```

and stores the configured limit as the dataset's logical byte value. Dataset
facts are reset for each object header, so this is not an aggregate logical-byte
limit across all datasets. `max_logical_dataset_bytes_seen` retains the largest
stored value across the run and can therefore be saturated at the profile limit.

If the dataspace element count has already overflowed, or if a dataset with a
layout has a stored-size product that overflows, h5policy records
`UINT64_MAX` and returns through the corresponding corruption path before this
profile multiplication is evaluated.

Zero is an active zero-byte limit. Unlimited presets use `UINT64_MAX`.

### `max_single_value_bytes`

This field currently applies to three declared sizes:

- a datatype's stored element size;
- a defined fill value's byte count; and
- the raw attribute-value bytes remaining after the attribute header, name,
  datatype, and dataspace.

Each over-limit case emits:

```text
H5_RESOURCE_SINGLE_VALUE_BYTES (resource)
```

The payload or datatype validator continues after emitting the finding. The
field does not constrain raw dataset extents, general mapping sizes, or every
allocation a consumer might perform; it is specifically a ceiling on one
declared value handled at these three sites.

Zero explicitly disables all three checks.

### `max_object_count`

This limits the file-wide `H5WalkContext.object_count`. The counter increments
once when the main breadth-first walk begins validating a queued object header,
including a queued superblock-extension object header. Queue and visited-set
deduplication normally prevent repeated hard links from incrementing it again.

Direct object-header lookups performed only to resolve a shared message do not
use this counter.

An over-limit increment emits:

```text
H5_RESOURCE_OBJECT_COUNT (resource)
```

and saturates the counter. It does not abort the current object-header parser.
The main walk may stop before its next queued object according to the general
continuation rules above.

Zero is an active zero-object limit. Unlimited uses `UINT64_MAX`.

### `max_attribute_count`

This limits the file-wide `H5WalkContext.attribute_count`. It increments once
for each attribute payload that reaches the attribute validator, including
attributes reached through compact object-header messages and dense attribute
storage.

An over-limit increment emits:

```text
H5_RESOURCE_ATTRIBUTE_COUNT (resource)
```

and saturates the counter. Attribute validation continues after the increment.

Zero is an active zero-attribute limit. Unlimited uses `UINT64_MAX`.

### `max_object_header_chunks`

Despite the metric and field names, this counts continuation messages, not all
object-header chunks. The file-wide `object_header_chunk_count` increments for
every continuation message encountered, before its size, target, cycle, and
checksum validation. Root chunks are not counted, and the counter is not reset
between objects.

An over-limit increment emits:

```text
H5_RESOURCE_OBJECT_HEADER_CHUNKS (resource)
```

and saturates the counter. Exceeding the field does not by itself prevent a
valid, unvisited continuation target from being followed recursively. Other
continuation checks or the general walk deadline may still stop that recursion.

Zero is an active zero-continuation limit. Unlimited uses `UINT64_MAX`.

### `max_chunk_count`

This limits the file-wide `H5WalkContext.accounted_chunk_count`. Depending on
the layout/index type, the counter is increased by:

- an estimated chunk count for an implicit v4 index;
- one for a defined single-chunk v4 layout;
- one for an unsupported but defined chunk-index reference;
- each leaf chunk reached in a v1 chunk B-tree;
- a v2 chunk B-tree header's total record count;
- a fixed-array header's element count; or
- an extensible-array header's realized-element count.

Consequently, the JSON metric named `chunk_index_refs` is a mixed
chunk/index-accounting value, not strictly a number of index references.

An addition beyond the limit emits:

```text
H5_RESOURCE_CHUNK_COUNT (resource)
```

and saturates the counter. An internal overflow flag preserves the distinction
between exact equality and proven overflow after saturation, and suppresses
duplicate chunk-count findings. Header-counted index validators may validate
their root or inline records after the finding, but recursive modern
chunk-index walkers do not follow further child edges after proven overflow.

For a validated v1 chunk-B-tree leaf, the declared leaf entry count is claimed
atomically. If it crosses the remaining allowance, only entries within that
allowance have their raw chunk addresses inspected. Internal nodes continue
descending when the accumulated count merely equals the ceiling: the walk
stops only when a later nonempty leaf proves overflow. That limited look-ahead
remains bounded by `max_btree_depth`, the visited-node set,
`max_walk_operations`, and `max_walk_seconds`.

Zero is an active zero-chunk limit. `UINT64_MAX` is effectively unlimited and
is used by the unlimited presets.

## Depth and shape limits

### `max_btree_depth`

This is checked on recursive paths for:

- v1 raw-data chunk B-trees;
- v2 raw-data chunk B-trees;
- old-style group v1 B-trees;
- dense-link v2 B-trees; and
- dense-attribute v2 B-trees;
- SOHM type-7 shared-message v2 B-trees; and
- SOHM fractal-heap huge-object v2 B-trees.

The check is `depth > max_btree_depth`, so depth equal to the limit is allowed.
Exceeding it emits:

```text
H5_RESOURCE_BTREE_DEPTH (resource)
```

and returns from that tree branch. A tree can be valid HDF5 while exceeding the
selected profile's analysis budget, so this finding does not claim corruption.
The field does not constrain every structure that merely contains a field
named “depth”; it applies at the recursive B-tree walkers listed above.

Zero allows a depth-zero leaf/root and rejects a recursive depth of one.
`UINT64_MAX` is effectively unlimited.

### `max_link_traversal_depth`

This limits hard-link traversal depth in the main object-header graph. The root
object and superblock extension are queued at depth zero. A hard-linked child is
queued at its parent's depth plus one. Soft links, external links, and
user-defined links are not resolved and therefore do not extend this depth.

The limit is checked both before enqueueing a child and again when dequeuing an
object. The comparison is `depth > max_link_traversal_depth`. Exceeding it emits:

```text
H5_RESOURCE_LINK_TRAVERSAL_DEPTH (resource)
```

The enqueue check declines to queue that target; the dequeue check skips the
object. A deeper valid link graph is therefore rejected as a resource-policy
choice rather than corruption. Zero permits only depth-zero objects.
`UINT64_MAX` would be effectively unlimited, although no built-in profile uses
it.

### `max_datatype_recursion_depth`

This bounds recursive datatype parsing. Datatype messages have both a bounded
iterative preflight for long single-child chains and the full recursive
validator; both use this field.

The check is `depth > max_datatype_recursion_depth`. A datatype over the limit
emits:

```text
H5_RESOURCE_DATATYPE_RECURSION_DEPTH (resource)
```

and stops validating that datatype. The configured ceiling is validator
self-protection, so exceeding it does not by itself establish malformed HDF5.

Zero permits only the depth-zero outer datatype. No built-in profile uses an
unlimited value.

### `max_filter_parameter_recursion_depth`

This independently bounds the recursive walk of n-bit filter datatype
parameters. A parameter tree over the limit emits:

```text
H5_RESOURCE_FILTER_PARAMETER_RECURSION_DEPTH (resource)
```

and returns its poison/failure value to the pipeline validator. As with datatype
depth, this is a resource-policy ceiling rather than a format-validity claim.

Zero permits only the depth-zero outer parameter node. No built-in profile uses
an unlimited value.

### `max_rank`

This is checked independently for every decoded dataspace. h5policy first
updates `max_rank_seen`, then applies two checks:

1. rank greater than the fixed `H5S_MAX_RANK` value of 32 from
   `h5_format_constants.pk` emits
   `H5_CORRUPT_DATASPACE_RANK_TOO_LARGE`;
2. rank greater than `profile.resources.max_rank` emits
   `H5_RESOURCE_DATASPACE_RANK`.

The profile finding is a resource finding and does not stop dimension parsing.
All built-ins use 32. Profile validation rejects a value above the fixed
ceiling, since it cannot make a rank accepted that the format/library check
rejects. A custom lower value remains useful as a stricter resource policy.

Zero permits rank-zero scalar/null dataspaces but treats every positive rank as
over the resource limit.

### `max_filter_count`

This is applied independently to each v1 or v2 filter-pipeline message. If the
pipeline's one-byte filter count is greater than the profile value, h5policy
emits:

```text
H5_RESOURCE_FILTER_COUNT (resource)
```

The validator deliberately continues through the declared descriptors so that
descriptor bounds, filter policy, and filter-specific parameters can still be
checked. This field is the only filter-count ceiling applied by the current
pipeline validator.

Zero rejects every nonempty pipeline as a resource shape. `UINT64_MAX` is
effectively unlimited.

## Compound resource rules

### Tiny logical chunks

`min_logical_chunk_bytes` and `max_chunks_below_min_logical_bytes` form one
per-dataset rule. It is evaluated only after h5policy knows a chunked layout,
dataspace, datatype, non-overflowed dataset element count, nonzero chunk element
count, and nonzero datatype logical size.

h5policy derives:

```text
logical chunk bytes = chunk element count * datatype logical size
estimated chunks    = ceil(dataset element count / chunk element count)
```

The finding is emitted only when all of the following are true:

```text
min_logical_chunk_bytes != 0
logical chunk bytes < min_logical_chunk_bytes
dataset element count != 0
estimated chunks > max_chunks_below_min_logical_bytes
```

The finding is:

```text
H5_RESOURCE_CHUNK_TOO_SMALL (resource)
```

It does not stop dataset validation. Equality at either byte or count threshold
does not trigger the rule. Setting `min_logical_chunk_bytes` to zero disables
the complete rule, and a valid profile must then set the companion count
threshold to zero as well. Setting only
`max_chunks_below_min_logical_bytes` to zero while keeping the byte threshold
enabled means any positive estimated count can satisfy the count side.

### Reachable-metadata ratios

The four metadata-ratio fields form a post-walk file-level rule. The numerator
is the possibly saturated `metadata_seen` accumulator described above. The
denominator is `h5policy_ceiling(ios)`, the smaller applicable bound from the
physical file size and declared HDF5 EOF.

The reject rule is evaluated first:

```text
metadata_ratio_reject_percent != 0
metadata_seen > metadata_ratio_reject_min_bytes
metadata_seen > floor(file_size * reject_percent / 100)
```

If true, it emits:

```text
H5_RESOURCE_METADATA_RATIO (resource)
```

Only when the reject rule is false is the warning rule evaluated:

```text
metadata_ratio_warn_percent != 0
metadata_seen > metadata_ratio_warn_min_bytes
metadata_seen > floor(file_size * warn_percent / 100)
```

If true, it emits:

```text
H5_ADVISORY_METADATA_RATIO (warning)
```

Both the absolute floor and percentage comparisons are strict `>` comparisons.
A zero percentage disables its rule and requires the corresponding minimum to
also be zero. A zero minimum does not disable a nonzero-percentage rule. A zero
denominator causes the percentage helper to return false.

Percentages must be at most 100. When both rules are enabled, the reject rule
must be at least as strict in both percentage and byte floor and strictly
stronger in at least one. Profile validation rejects redundant or weaker reject
rules.

The post-walk check runs after the top-level try/catch, so it can add a ratio
finding even when another finding or caught exception has already determined
the final decision.

### `max_walk_operations`

Every `h5policy_walk_tick` call charges an abstract cost for work such as
bounded reads, checked arithmetic, recursive steps, and linear visited-set
searches. The configured maximum is inclusive. A charge that would exceed it
saturates `walk_operations` at the limit and raises a distinguished exception;
the top-level handler emits:

```text
H5_UNSUPPORTED_WALK_OPERATION_BUDGET (unsupported)
```

This deterministic budget makes the same validation workload stop at the same
charged cost regardless of machine speed. Zero is invalid profile
configuration. `UINT64_MAX` is practically unlimited, although no built-in
profile uses it.

### `max_walk_seconds`

Before opening and validating the file, h5policy records an integer-second
deadline equal to the current time plus this field. `h5policy_walk_tick`
accumulates abstract operation costs and samples the clock at the first tick and
then after approximately each additional 200,000 charged operations.

The deadline is exceeded when the sampled integer time is strictly greater than
the deadline. A long operation that does not call `h5policy_walk_tick` is not
interrupted by the in-pickle deadline until a later tick.

Exceeding the deadline raises a distinguished internal exception. The top-level
handler converts it to:

```text
H5_UNSUPPORTED_WALK_TIME_BUDGET (unsupported)
```

and normal validation does not resume. `max_walk_seconds` must be between 1 and
2,147,483,647, keeping signed deadline arithmetic bounded; profile validation
rejects other values before file I/O. Internal callers such as h5patch disable
the in-pickle deadline by directly assigning
`h5policy_walk_deadline = 0`, outside `H5PolicyProfile`.

The shell wrapper has a second, independent hard timeout: 20 seconds for the
default/untrusted profile, 35 for trusted-fast, 50 for forensic, and 90 for
legacy. If that timeout kills poke, the wrapper produces
`H5_UNSUPPORTED_WALK_TIMEOUT`. Those wrapper values are not derived from
`max_walk_seconds`.

## Built-in feature and analysis-default presets

All fields are `uint<8>` and valid profiles restrict them to exactly zero or
one. Enforcement sites therefore receive canonical boolean values.

| Field | `untrusted-strict` | `forensic` | `trusted-fast` | `legacy` |
| --- | ---: | ---: | ---: | ---: |
| `allow_external_links` | 0 | 0 | 1 | 1 |
| `allow_external_storage` | 0 | 0 | 1 | 1 |
| `allow_vds` | 0 | 0 | 1 | 1 |
| `allow_dynamic_filters` | 0 | 0 | 1 | 1 |
| `allow_unknown_messages` | 0 | 1 | 1 | 1 |
| `allow_legacy_dangerous_messages` | 0 | 0 | 0 | 1 |
| `nonstrict_mapping` | 0 | 1 | 0 | 0 |
| `continue_after_corruption` | 0 | 1 | 0 | 0 |
| `sweep_unreachable_metadata` | 0 | 1 | 0 | 0 |

### `allow_external_links`

An external link is always counted in the report's `features.external_links`
metric and its in-file message envelope is validated. h5policy never opens or
follows the target file.

When this field is zero, encountering an external link emits:

```text
H5_POLICY_EXTERNAL_LINK (policy)
```

When it is nonzero, no policy finding is emitted, but the external-link validator
classifies the terminated target file name and can emit one of the relative,
absolute, or parent-path advisories used for external storage and VDS sources:

```text
H5_ADVISORY_EXTERNAL_LINK_RELATIVE_PATH (warning)
H5_ADVISORY_EXTERNAL_LINK_ABSOLUTE_PATH (warning)
H5_ADVISORY_EXTERNAL_LINK_PARENT_PATH   (warning)
```

The classification is syntactic and best-effort: h5policy inspects only the
stored bytes, never resolving the path or opening the target, so it cannot know
the consumer's base directory or whether a plain name is itself a symlink. These
advisories are suppressed when the feature is denied, although the message
envelope (bounds and NUL termination of both the target file name and object
path) is validated under every profile.

### `allow_external_storage`

Every external-file-list message is counted in
`features.external_storage` and its in-file header, slots, heap references,
names, and segment arithmetic are validated. h5policy never opens an external
file.

When this field is zero, the message-policy step emits:

```text
H5_POLICY_EXTERNAL_STORAGE (policy)
```

When it is nonzero, the EFL validator additionally classifies each terminated
filename and can emit one of the relative, absolute, or parent-path advisories.
It can also warn about an unlimited external segment. These advisories are
suppressed when the feature is denied, although structural validation still
runs.

### `allow_vds`

A virtual-dataset layout is always counted in `features.vds`, and h5policy
validates the in-file VDS mapping block without opening a source file.

When this field is zero, encountering the layout emits:

```text
H5_POLICY_VDS (policy)
```

When it is nonzero, source filenames are classified and can produce relative,
absolute, or parent-path advisories. Path advisories are suppressed when VDS is
denied, although mapping validation still runs.

### `allow_dynamic_filters`

The current core-filter set is filter IDs 1 through 6. Every other filter ID is
recorded in the report's distinct `features.dynamic_filters` array.

When this field is zero, each encountered non-core filter can emit:

```text
H5_POLICY_DYNAMIC_FILTER (policy)
```

When it is nonzero, no dynamic-filter policy or advisory finding is emitted.
h5policy never loads or runs the filter. Built-in filters that decode or expand
data are handled separately: deflate, szip, n-bit, and scale-offset produce
`H5_ADVISORY_DECODE_FILTER` regardless of this flag.

### `allow_unknown_messages`

An object-header message ID outside the recognized range is always counted in
`features.unknown_messages`.

When this field is zero, h5policy emits:

```text
H5_POLICY_UNKNOWN_MESSAGE (policy)
```

When it is nonzero, h5policy instead emits:

```text
H5_UNSUPPORTED_PICKLE_COVERAGE_GAP (unsupported)
```

Thus, nonzero does not make an unknown message an unconditional accept; it
changes the classification from denied-by-policy to not-covered-by-validator.

### `allow_legacy_dangerous_messages`

This field controls object-header message type `0x09`, called the
"bogus-valid" message by the validator. When zero, the message emits:

```text
H5_POLICY_LEGACY_DANGEROUS_MESSAGE (policy)
```

When nonzero, that policy finding is suppressed. There is no corresponding
feature counter in the JSON report.

### Analysis controls

`analysis_defaults.nonstrict_mapping` selects the mapping default when neither
`--strict` nor `--non-strict` is supplied. Nonzero selects non-strict Poke
mappings (`@!`); zero selects strict mappings (`@`).

`analysis_defaults.continue_after_corruption` independently selects whether the
main walk continues between queued objects after a rejection when
`--continue-after-rejection` is absent. The field keeps its original name for
profile and pickle API compatibility; the CLI and JSON use the more accurate
"after rejection" terminology. The CLI flag can enable continuation for any
profile.

`analysis_defaults.sweep_unreachable_metadata` independently enables the
raw-file GCOL signature sweep after the reachable walk. The sweep finds
orphaned global-heap zero-advance loops and is not affected by either CLI
override.

The resolver copies or overrides these values into the same-named fields of
`H5RunOptions`. Validators consult that effective run value rather than the
preset defaults directly. The forensic preset enables all three fields.

## Current test coverage

[`unit_limits.pk`](../tests/unit_limits.pk) clones the strict profile, reduces
one or two fields at a time, and drives synthetic in-memory metadata through the
ordinary enforcement helpers. It also snapshots all 30 fields of each of the
four built-in profiles. It characterizes exact helper boundaries without
requiring production-scale files.

The generated corpus is the end-to-end and libhdf5-facing layer. Its shipped-
preset cases lock down public behavior. Its reduced-boundary cases clone a
named preset, apply strictly typed and allowlisted test-only overrides, and call
the ordinary `h5policy_run` entry point. Thus compact files can exercise the
complete parser and walk without exposing configurable limits in the public
CLI.

| Field or rule | Current direct coverage |
| --- | --- |
| Built-in profile values | Every field in all four presets is compared with its documented value. The production clone helper reconstructs every nested group; unit mutation checks verify that clones cannot alias a shipped preset. |
| `max_accounted_metadata_bytes`, `max_object_count` | Equality, over-limit finding class, and saturating accumulation are covered directly through their accounting helpers. Reduced full-file cases saturate `metadata_bytes_seen` at the exact ceiling, including deep raw-data, SOHM type-7, and SOHM huge-object v2 B-tree cases that permit their roots but refuse and stop at a child-node charge. |
| `max_attribute_count` | A valid synthetic attribute is parsed at and above a reduced cumulative limit. |
| `max_object_header_chunks` | A synthetic continuation message covers equality, over-limit saturation, and the fact that its later structural finding is independent. A valid continuation-heavy object header crosses a reduced full-walk ceiling and saturates the reported counter without becoming corrupt. |
| `max_chunk_count` | Defined chunk-index references cover equality, over-limit saturation, and the internal exact-versus-exceeded state. A valid four-chunk fixed-array dataset rejects as resource policy under a reduced ceiling. Separate legacy v1 cases cover exact equality and overflow within one leaf, plus a 130-chunk multi-level tree whose parent must continue at equality into a later child to prove overflow. In every rejecting case, `chunk_index_refs` saturates exactly at the selected limit. |
| `max_single_value_bytes` | Fill values cover equality, over-limit resource classification, and zero-as-disabled; separate valid datatype and attribute blobs cross the other two enforcement sites. A compact valid file isolates the attribute-value enforcement site during a full walk. |
| `max_logical_dataset_bytes` | Synthetic dataset facts cover equality and saturation. `resource/huge_logical_dataset.h5` requires the resource finding, and the same file is accepted under legacy. |
| Tiny logical chunks | Synthetic facts cover equality at both sub-thresholds, rejection when both strict comparisons pass, zero-byte disabling, and validation of the disabled pair. `resource/tiny_chunks.h5` supplies end-to-end coverage. |
| `max_btree_depth` | A recursive chunk-tree entry above a zero limit characterizes the resource finding and early branch return. Valid multi-level dense-link, raw-data chunk, SOHM type-7, and SOHM huge-object v2 B-trees also reject as resource policy under reduced full-walk ceilings. |
| `max_link_traversal_depth` | Synthetic queue operations cover equality, the resource over-limit finding, and declining to enqueue the child. A real depth-66 hierarchy rejects under the built-in strict profile and accepts under the built-in forensic profile. |
| `max_datatype_recursion_depth` | `unit_datatype.pk` covers deep VLen and compound nesting as resource rejection; the CVE fixture requires the same finding under legacy. A valid compound-with-array datatype crosses a reduced full-walk depth ceiling as a resource rejection. |
| `max_filter_parameter_recursion_depth` | A direct recursive call above a zero limit covers the resource finding and poison return; malformed n-bit parameter bounds and classes retain their synthetic coverage. A valid n-bit-filtered dataset reaches the same resource path end to end under a reduced ceiling. |
| `max_rank` | A valid rank-two dataspace covers equality and resource rejection below the fixed rank ceiling; profile validation rejects ceilings above 32. A full-file rank-one case confirms enforcement of the configured profile limit. |
| `max_filter_count` | A valid two-filter pipeline covers equality, resource classification, and continued descriptor parsing synthetically. The same shape is exercised end to end by a valid shuffle+gzip dataset: lowering only the filter ceiling retains both the decode advisory and all four chunk records. |
| Metadata-ratio rules | Synthetic counters cover the strict absolute/percentage boundaries, warning behavior, reject behavior, and reject-over-warning precedence. Profile checks cover percentage bounds, disabled-rule floors, and warning/reject ordering. Full-walk cases separately require the warning and rejection decisions and verify rejection suppresses the advisory. |
| `allow_external_links`, `allow_external_storage`, `allow_vds`, `allow_dynamic_filters` | Each zero/nonzero policy branch and feature counter is covered synthetically. External-link and EFL corpus cases also compare restrictive and permissive profiles; VDS has a permissive source-path corpus case. |
| `allow_unknown_messages` | Synthetic message policy covers denied-as-policy and allowed-as-unsupported behavior. |
| `allow_legacy_dangerous_messages` | Synthetic message policy covers both zero and nonzero behavior. |
| Analysis controls | Unit checks cover independent mapping and continuation defaults plus CLI overrides. Integration cases isolate non-strict mapping from the other forensic controls and show that disabling the sweep suppresses an otherwise reachable orphaned-GCOL diagnostic. |
| `max_walk_operations` | Unit checks cover the inclusive boundary, saturated metric, distinguished exception, zero rejection, and all four preset values. A dense-link full walk reaches the deterministic operation exception with the metric exactly saturated at the reduced ceiling and no time-budget finding. |
| `max_walk_seconds` | The four current preset values are snapshotted, all built-ins are validated, and zero/overflowing values are rejected directly. An already-expired synthetic deadline covers the distinguished time-budget exception. An invalid-profile integration case uses a deliberately missing input to prove validation happens before file I/O. |

The authoritative corpus decisions, required findings, forbidden findings, and
selected metric/feature assertions are in
[`tests/expected`](../tests/expected). The two focused synthetic suites are
[`unit_limits.pk`](../tests/unit_limits.pk) and
[`unit_datatype.pk`](../tests/unit_datatype.pk); the two integration tiers are
documented in [`tests/README.md`](../tests/README.md).
