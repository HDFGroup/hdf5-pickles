# `H5PolicyLimits`: Current Semantics

This document describes the behavior of `H5PolicyLimits` as it is implemented
today. It is a characterization reference, not a proposal for a future profile
model. Where a field name suggests broader behavior than the validators
currently implement, the narrower implemented behavior is documented.

The type and four built-in values are defined in
[`h5_profiles.pk`](../pickles/h5_profiles.pk). The command-line wrapper maps the
public profile names to those values, and [`h5_policy.pk`](../pickles/h5_policy.pk)
selects one value for a run.

## General behavior

Although named `H5PolicyLimits`, the struct contains three kinds of setting:

- numeric resource, shape, depth, and time limits;
- feature-policy flags; and
- `forensic_mode`, which selects analysis behavior as well as a profile default.

There is currently no profile-validation step. Callers constructing another
`H5PolicyLimits` value are responsible for using meaningful percentages,
boolean values, sentinel values, and relationships between fields.

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
- `0` disables `max_single_allocation_bytes` and the metadata-ratio percentage
  rules.
- `0` disables the tiny-chunk rule only when used for
  `min_logical_chunk_bytes`; `min_logical_chunk_count = 0` by itself does not
  disable that rule.
- `max_walk_seconds = 0` does not disable the deadline.
- `max_filter_expansion_ratio` is not read, so its value has no effect.

### Findings and control flow

Emitting a finding updates the final decision but does not itself throw an
exception or stop the current validator. Some enforcement sites explicitly
return or decline to enqueue more work; others continue parsing the current
structure.

Without `--continue-after-corruption`, the main object-header breadth-first walk
stops before dequeuing its next object after any decision other than `accept` or
`accept_with_warnings`. Work already in progress inside the current object,
tree, index, pipeline, or continuation chain follows the control flow described
below. With continuation enabled, that main-walk early exit is disabled, but
explicit per-validator returns and the walk deadline still apply.

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
| `max_metadata_bytes` | 256 MiB | 1 GiB | 4 GiB | `UINT64_MAX` |
| `max_logical_dataset_bytes` | 64 GiB | `UINT64_MAX` | 16 TiB | `UINT64_MAX` |
| `max_single_allocation_bytes` | 1 GiB | disabled | disabled | disabled |
| `max_object_count` | 100,000 | 1,000,000 | 10,000,000 | `UINT64_MAX` |
| `max_attribute_count` | 100,000 | 1,000,000 | 10,000,000 | `UINT64_MAX` |
| `max_object_header_chunks` | 1,024 | 4,096 | 65,536 | `UINT64_MAX` |
| `max_btree_depth` | 64 | 128 | 128 | `UINT64_MAX` |
| `max_link_traversal_depth` | 64 | 128 | 128 | 128 |
| `max_datatype_recursion_depth` | 64 | 128 | 128 | 128 |
| `max_chunk_count` | 10,000,000 | `UINT64_MAX` | `UINT64_MAX` | `UINT64_MAX` |
| `min_logical_chunk_bytes` | 4 KiB | 0 | 0 | 0 |
| `min_logical_chunk_count` | 4,096 | 0 | 0 | 0 |
| `max_filter_count` | 32 | 64 | 64 | `UINT64_MAX` |
| `max_filter_expansion_ratio` | 100 | 0 | 0 | 0 |
| `max_rank` | 32 | 64 | 64 | `UINT64_MAX` |
| `metadata_ratio_warn_percent` | 50 | 0 | 75 | 0 |
| `metadata_ratio_warn_min_bytes` | 1 MiB | 0 | 16 MiB | 0 |
| `metadata_ratio_reject_percent` | 75 | 0 | 0 | 0 |
| `metadata_ratio_reject_min_bytes` | 16 MiB | 0 | 0 | 0 |
| `max_walk_seconds` | 10 | 30 | 20 | 60 |

## Counter and byte limits

### `max_metadata_bytes`

This limits `H5WalkContext.metadata_seen`, a file-wide accumulator shared by the
main reachable-metadata walk. Each explicit accounting call adds a declared or
calculated metadata-structure size. If the addition would exceed the limit,
the counter becomes the limit and h5policy emits:

```text
H5_RESOURCE_METADATA_BYTES (resource)
```

An accounting failure does not immediately stop the validator that made the
call.

The accumulator is not a count of all bytes read or mapped, and it is not a
complete unique-extent measure. Current accounting calls cover:

- the superblock mapping size;
- v1 and v2 root object-header extents;
- declared object-header continuation extents;
- old-style group v1 B-tree nodes and SNOD nodes;
- v1 chunk B-tree nodes; and
- v2 B-tree, fixed-array, and extensible-array chunk-index headers.

In particular, general byte mappings do not charge this counter automatically.
Dense fractal-heap/B-tree blocks, SOHM structures, VDS global-heap objects,
metadata-cache image bodies, and chunk-index data blocks are not uniformly
included. Reaching the same explicitly accounted structure through distinct
paths is not guaranteed to be globally deduplicated by the accounting helper.

Zero is an active zero-byte limit. The built-in unlimited preset uses
`UINT64_MAX`.

### `max_logical_dataset_bytes`

This is a per-dataset derived-size limit. Once both a dataspace and datatype are
known, h5policy calculates:

```text
dataset element count * datatype logical size
```

The logical size normally equals the datatype's stored element size. Revised
references with the recognized compact on-disk encoding use 64 bytes as their
logical size to match the libhdf5-facing metric.

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

### `max_single_allocation_bytes`

This field currently applies to three declared sizes:

- a datatype's stored element size;
- a defined fill value's byte count; and
- the raw attribute-value bytes remaining after the attribute header, name,
  datatype, and dataspace.

Each over-limit case emits:

```text
H5_RESOURCE_SINGLE_ALLOCATION_BYTES (resource)
```

The payload or datatype validator continues after emitting the finding. The
field does not currently constrain every mapping or every allocation a consumer
might perform; in particular, its name does not imply a general maximum mapping
size inside h5policy.

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

This limits the file-wide `H5WalkContext.chunk_index_count`. Depending on the
layout/index type, the counter is increased by:

- an estimated chunk count for an implicit v4 index;
- one for a defined single-chunk v4 layout;
- one for an unsupported but defined chunk-index reference;
- each leaf chunk reached in a v1 chunk B-tree;
- a v2 chunk B-tree header's total record count;
- a fixed-array header's element count; or
- an extensible-array header's element count.

Consequently, the JSON metric named `chunk_index_refs` is a mixed
chunk/index-accounting value, not strictly a number of index references.

An addition beyond the limit emits:

```text
H5_RESOURCE_CHUNK_COUNT (resource)
```

and saturates the counter. Header-counted index validators may continue
validating their root or inline records after the finding. The v1 chunk B-tree
walker has an additional early return: when a finite limit is configured and
the accumulated count is already equal to it, it stops before processing the
next entry. Because that return occurs before discovering another leaf, a v1
tree can stop at the exact limit without emitting an over-limit finding for
undiscovered remaining entries.

Zero is an active zero-chunk limit. `UINT64_MAX` also disables the v1 walker's
explicit equality early return and is used by the unlimited presets.

## Depth and shape limits

### `max_btree_depth`

This is checked on recursive paths for:

- v1 raw-data chunk B-trees;
- old-style group v1 B-trees;
- dense-link v2 B-trees; and
- dense-attribute v2 B-trees.

The check is `depth > max_btree_depth`, so depth equal to the limit is allowed.
Exceeding it emits:

```text
H5_CORRUPT_BTREE_DEPTH_EXCEEDED (corrupt)
```

and returns from that tree branch. The field does not constrain every structure
that contains an on-disk B-tree depth. For example, the partial v2 chunk-index
B-tree validator validates a header and root but does not recursively descend
arbitrary internal nodes through this field.

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
H5_CORRUPT_LINK_TRAVERSAL_DEPTH_EXCEEDED (corrupt)
```

The enqueue check declines to queue that target; the dequeue check skips the
object. Zero permits only depth-zero objects. `UINT64_MAX` would be effectively
unlimited, although no built-in profile uses it.

### `max_datatype_recursion_depth`

This bounds recursive datatype parsing and also the recursive walk of n-bit
filter datatype parameters. Datatype messages have both a bounded iterative
preflight for long single-child chains and the full recursive validator; both
use the same profile field.

The check is `depth > max_datatype_recursion_depth`. A datatype over the limit
emits:

```text
H5_CORRUPT_DATATYPE_RECURSION_LIMIT (corrupt)
```

and stops validating that datatype. An n-bit parameter tree over the limit
instead emits:

```text
H5_CORRUPT_NBIT_PARAMS_RECURSION (corrupt)
```

and returns its poison/failure value to the pipeline validator.

Zero permits only the depth-zero outer datatype or parameter node. No built-in
profile uses an unlimited value.

### `max_rank`

This is checked independently for every decoded dataspace. h5policy first
updates `max_rank_seen`, then applies two checks:

1. rank greater than the fixed `H5POLICY_H5S_MAX_RANK` value of 32 emits
   `H5_CORRUPT_DATASPACE_RANK_TOO_LARGE`;
2. rank greater than `profile.max_rank` emits
   `H5_RESOURCE_DATASPACE_RANK`.

The profile finding is a resource finding and does not stop dimension parsing.
Because the fixed check is also applied, built-in profile values of 32 or more
do not cause a resource-only rejection for ranks above the fixed ceiling.

Zero permits rank-zero scalar/null dataspaces but treats every positive rank as
over the resource limit. `UINT64_MAX` disables only the profile-level check in
practice; the fixed rank check still applies.

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

### `max_filter_expansion_ratio`

No validator reads this field. It has no trigger, finding, metric, or control
flow effect in the current implementation. In particular, filtered chunk
metadata is not compared with this value.

## Compound resource rules

### Tiny logical chunks

`min_logical_chunk_bytes` and `min_logical_chunk_count` form one per-dataset
rule. It is evaluated only after h5policy knows a chunked layout, dataspace,
datatype, non-overflowed dataset element count, nonzero chunk element count, and
nonzero datatype logical size.

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
estimated chunks > min_logical_chunk_count
```

The finding is:

```text
H5_RESOURCE_CHUNK_TOO_SMALL (resource)
```

It does not stop dataset validation. Equality at either byte or count threshold
does not trigger the rule. Setting `min_logical_chunk_bytes` to zero disables
the complete rule. Setting only `min_logical_chunk_count` to zero means any
positive estimated count can satisfy the count side of the rule.

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
A zero percentage disables its rule regardless of the corresponding minimum.
A zero minimum does not disable a nonzero-percentage rule. A zero denominator
causes the percentage helper to return false.

The post-walk check runs after the top-level try/catch, so it can add a ratio
finding even when another finding or caught exception has already determined
the final decision.

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
H5_UNSUPPORTED_WALK_BUDGET (unsupported)
```

and normal validation does not resume. `max_walk_seconds = 0` sets the deadline
to the current integer second; it does not disable deadline checking. Internal
callers such as h5patch disable the in-pickle deadline by directly assigning
`h5policy_walk_deadline = 0`, outside `H5PolicyLimits`.

The shell wrapper has a second, independent hard timeout: 20 seconds for the
default/untrusted profile, 35 for trusted-fast, 50 for forensic, and 90 for
legacy. If that timeout kills poke, the wrapper produces
`H5_UNSUPPORTED_WALK_TIMEOUT`. Those wrapper values are not derived from
`max_walk_seconds`.

## Built-in feature and mode presets

All fields are `uint<8>`. Enforcement sites treat zero as false and nonzero as
true; there is no validation restricting a custom value to exactly zero or one.

| Field | `untrusted-strict` | `forensic` | `trusted-fast` | `legacy` |
| --- | ---: | ---: | ---: | ---: |
| `allow_external_links` | 0 | 0 | 1 | 1 |
| `allow_external_storage` | 0 | 0 | 1 | 1 |
| `allow_vds` | 0 | 0 | 1 | 1 |
| `allow_dynamic_filters` | 0 | 0 | 1 | 1 |
| `allow_unknown_messages` | 0 | 1 | 1 | 1 |
| `allow_legacy_dangerous_messages` | 0 | 0 | 0 | 1 |
| `forensic_mode` | 0 | 1 | 0 | 0 |

### `allow_external_links`

An external link is always counted in the report's `features.external_links`
metric and its in-file message envelope is validated. h5policy never opens or
follows the target file.

When this field is zero, encountering an external link emits:

```text
H5_POLICY_EXTERNAL_LINK (policy)
```

When it is nonzero, no policy finding is emitted. The current external-link
validator does not emit the absolute/relative/parent-path advisories used for
external storage and VDS sources.

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

### `forensic_mode`

This field currently has three effects:

1. In the absence of a CLI mapping override, nonzero selects non-strict Poke
   mappings (`@!`) and zero selects strict mappings (`@`).
2. In the absence of `--continue-after-corruption`, nonzero enables continued
   walking after a rejection and zero uses early exit between queued objects.
3. After the reachable walk, nonzero enables the raw-file GCOL signature sweep
   used to find orphaned global-heap zero-advance loops.

`--strict` or `--non-strict` can override the first default, and
`--continue-after-corruption` can enable the second behavior for another
profile. Those overrides do not disable or enable the GCOL sweep; the sweep is
still controlled directly by `forensic_mode`.

## Current test coverage

[`unit_limits.pk`](../tests/unit_limits.pk) copies the strict profile, reduces
one or two fields at a time, and drives synthetic in-memory metadata through the
ordinary enforcement helpers. It characterizes current behavior without
requiring production-scale files. The generated corpus remains the end-to-end
and libhdf5-facing layer.

| Field or rule | Current direct coverage |
| --- | --- |
| `max_metadata_bytes`, `max_object_count` | Equality, over-limit finding class, and saturating accumulation are covered directly through their accounting helpers. |
| `max_attribute_count` | A valid synthetic attribute is parsed at and above a reduced cumulative limit. |
| `max_object_header_chunks` | A synthetic continuation message covers equality, over-limit saturation, and the fact that its later structural finding is independent. |
| `max_chunk_count` | Defined chunk-index references cover equality and over-limit saturation; full index-format stopping behavior remains integration coverage. |
| `max_single_allocation_bytes` | A fill value covers equality, over-limit resource classification, and zero-as-disabled. The datatype-size and attribute-value enforcement sites are not separately crossed. |
| `max_logical_dataset_bytes` | Synthetic dataset facts cover equality and saturation. `resource/huge_logical_dataset.h5` requires the resource finding, and the same file is accepted under legacy. |
| Tiny logical chunks | Synthetic facts cover equality at both sub-thresholds, rejection when both strict comparisons pass, and zero-byte disabling. `resource/tiny_chunks.h5` supplies end-to-end coverage. |
| `max_btree_depth` | A recursive chunk-tree entry above a zero limit characterizes the corrupt finding and early branch return. |
| `max_link_traversal_depth` | Synthetic queue operations cover equality, the corrupt over-limit finding, and declining to enqueue the child. |
| `max_datatype_recursion_depth` | `unit_datatype.pk` covers deep VLen and compound nesting; the CVE fixture also requires the recursion finding under legacy. |
| `max_rank` | A valid rank-two dataspace covers equality and resource-only rejection below the fixed rank ceiling. |
| `max_filter_count` | A valid two-filter pipeline covers equality, resource classification, and continued descriptor parsing. |
| Metadata-ratio rules | Synthetic counters cover the strict absolute/percentage boundaries, warning behavior, reject behavior, and reject-over-warning precedence. |
| `allow_external_links`, `allow_external_storage`, `allow_vds`, `allow_dynamic_filters` | Each zero/nonzero policy branch and feature counter is covered synthetically. External-link and EFL corpus cases also compare restrictive and permissive profiles; VDS has a permissive source-path corpus case. |
| `allow_unknown_messages` | Synthetic message policy covers denied-as-policy and allowed-as-unsupported behavior. |
| `allow_legacy_dangerous_messages` | Synthetic message policy covers both zero and nonzero behavior. |
| `forensic_mode` | Unit checks cover default mapping/continuation behavior and CLI mapping overrides. Forensic corpus cases exercise non-strict diagnostics, and the orphaned-GCOL fixture exercises the forensic-only sweep. |
| `max_walk_seconds` | The four current preset values are snapshotted; deadline expiry is not induced because it is clock-dependent. |
| `max_filter_expansion_ratio` | The four current preset values are snapshotted, but no enforcement exists to exercise. |

The authoritative corpus decisions and required findings are in
[`tests/expected`](../tests/expected). The two synthetic layers are
[`unit_limits.pk`](../tests/unit_limits.pk) and
[`unit_datatype.pk`](../tests/unit_datatype.pk).
