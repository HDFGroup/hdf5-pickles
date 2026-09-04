# H5PL Policy-Profile API Extension

> **Status: design proposal.** The API in this document is not implemented by
> H5Lens or libhdf5. It is a draft for discussion with the HDF5 maintainers.

## Summary

Add a file-scoped policy-profile property to the H5PL public API. An
application selects one of the four profiles defined by h5policy, or supplies
a user-defined profile with the same nested structure, on a file access
property list (FAPL) before opening a file. The library snapshots that choice
into the shared file state and uses it whenever the file encounters a non-core
filter.

The first version should enforce only the profile rule that maps cleanly into
the native plugin boundary: whether a non-core filter may be activated. It
should not copy h5policy's resource budgets or metadata validator into H5PL,
and it must not imply that selecting a profile performs a preflight. In
particular, this API does not run h5policy.

The central design choice is scope. The existing H5PL loading mask and search
path are process-global. A policy decision about one file must instead survive
concurrent operations on files from different trust boundaries without a
global set/open/restore race.

## Design basis

This draft was checked on 2026-09-04 against a clean workstation-local HDF5
`develop` checkout at revision `44426bfc7d5f273d5c489ad515c2e7b3b36182c6`.
`H5public.h` identifies that source as HDF5 2.3.0. Paths are intentionally not
recorded.

That revision's public H5PL surface has two kinds of process-wide state:

- `H5PLset_loading_state()` and `H5PLget_loading_state()` control a bitmask for
  FILTER, VOL, and VFD plugins;
- `H5PLappend()`, `H5PLprepend()`, `H5PLreplace()`, `H5PLinsert()`,
  `H5PLremove()`, `H5PLget()`, and `H5PLsize()` manage a global search-path
  table.

`HDF5_PLUGIN_PRELOAD=::` disables plugin loading at package initialization and
cannot later be relaxed through `H5PLset_loading_state()`. Plugin discovery
checks a global cache before searching the path table, although the current
type mask is checked before consulting the plugin cache.

The source also contains optional build-time verification of appended digital
signatures before `dlopen`/`LoadLibrary`. The measured local 2.3.0 build has
that option disabled. Signature verification is useful defense in depth, but
it answers who signed a binary, not whether a file at a particular trust
boundary should be allowed to request that code.

## Semantic boundary

The h5policy profiles classify metadata. They do not activate filters, open
external resources, or load plugins. In current h5policy, filter identifiers 1
through 6 are core filters; every other identifier is a non-core filter for
profile purposes. `allow_dynamic_filters` determines whether the presence of
such a filter produces `H5_POLICY_DYNAMIC_FILTER`.

The proposed H5PL projection is therefore:

| Profile | `allow_dynamic_filters` | Proposed H5PL rule for non-core filters |
| --- | ---: | --- |
| `untrusted-strict` | `0` | `deny` |
| `forensic` | `0` | `deny` |
| `trusted-fast` | `1` | `allow` |
| `legacy` | `1` | `allow` |

Two pairs intentionally have the same H5PL behavior. Their differences remain
meaningful to h5policy: budgets, mapping strictness, continuation, unreachable
metadata sweeping, and the other feature switches are outside the plugin
loader's remit.

A user-defined profile is a complete value with the same `resources`,
`heuristics`, `features`, and `analysis_defaults` groups as `H5PolicyProfile`.
Its H5PL projection is determined directly by
`features.allow_dynamic_filters`: zero denies non-core filters and one allows
them subject to the other H5PL controls. The remaining fields are retained so
the same effective definition can be used by h5policy and audited through the
native file configuration; H5PL does not pretend to enforce them.

This projection applies to non-core filter use regardless of provenance. A
filter that was dynamically loaded earlier and is now cached, or one that was
programmatically registered with `H5Zregister()`, must not bypass a denying
file profile. Core filters remain available; their decoding risk is separately
reported by h5policy as `H5_ADVISORY_DECODE_FILTER` where applicable.

The profile does not select or authorize VOL and VFD plugins. Those are chosen
by the application, a property list, or process configuration rather than by a
filter identifier in the assessed file. Existing H5PL controls continue to
govern VOL and VFD plugins. A future application-policy API could control
those choices, but folding such a policy silently into the four h5policy names
would assign them semantics they do not currently have.

The API also does not enforce external-link, external-storage, VDS, unknown-
message, legacy-message, resource-budget, or structural-validity rules. An
application still needs a complete h5policy result, or equivalent native
validation, before treating an untrusted file as approved.

## Proposed public interface

The new declarations belong in `H5PLpublic.h`:

```c
/** Policy profile applied to non-core filter activation for one file. */
typedef enum H5PL_policy_profile_t {
    H5PL_POLICY_PROFILE_ERROR            = -1,
    H5PL_POLICY_PROFILE_LEGACY           = 0,
    H5PL_POLICY_PROFILE_TRUSTED_FAST      = 1,
    H5PL_POLICY_PROFILE_UNTRUSTED_STRICT  = 2,
    H5PL_POLICY_PROFILE_FORENSIC          = 3,
    H5PL_POLICY_PROFILE_CUSTOM            = 4
} H5PL_policy_profile_t;

#define H5PL_POLICY_DEFINITION_VERSION 1

typedef struct H5PL_resource_limits_t {
    uint64_t max_accounted_metadata_bytes;
    uint64_t max_logical_dataset_bytes;
    uint64_t max_single_value_bytes;
    uint64_t max_object_count;
    uint64_t max_attribute_count;
    uint64_t max_object_header_chunks;
    uint64_t max_btree_depth;
    uint64_t max_link_traversal_depth;
    uint64_t max_datatype_recursion_depth;
    uint64_t max_filter_parameter_recursion_depth;
    uint64_t max_chunk_count;
    uint64_t max_filter_count;
    uint64_t max_rank;
    uint64_t max_walk_operations;
    uint64_t max_walk_seconds;
} H5PL_resource_limits_t;

typedef struct H5PL_heuristic_policy_t {
    uint64_t min_logical_chunk_bytes;
    uint64_t max_chunks_below_min_logical_bytes;
    uint64_t metadata_ratio_warn_percent;
    uint64_t metadata_ratio_warn_min_bytes;
    uint64_t metadata_ratio_reject_percent;
    uint64_t metadata_ratio_reject_min_bytes;
} H5PL_heuristic_policy_t;

typedef struct H5PL_feature_policy_t {
    uint8_t allow_external_links;
    uint8_t allow_external_storage;
    uint8_t allow_vds;
    uint8_t allow_dynamic_filters;
    uint8_t allow_unknown_messages;
    uint8_t allow_legacy_dangerous_messages;
} H5PL_feature_policy_t;

typedef struct H5PL_analysis_defaults_t {
    uint8_t nonstrict_mapping;
    uint8_t continue_after_corruption;
    uint8_t sweep_unreachable_metadata;
} H5PL_analysis_defaults_t;

typedef struct H5PL_policy_definition_t {
    unsigned int             version;
    size_t                   struct_size;
    H5PL_resource_limits_t   resources;
    H5PL_heuristic_policy_t  heuristics;
    H5PL_feature_policy_t    features;
    H5PL_analysis_defaults_t analysis_defaults;
} H5PL_policy_definition_t;

H5_DLL herr_t H5PLset_policy_profile(hid_t fapl_id,
                                     H5PL_policy_profile_t profile);

H5_DLL herr_t H5PLget_policy_profile(hid_t fapl_id,
                                     H5PL_policy_profile_t *profile);

H5_DLL ssize_t H5PLget_policy_profile_name(H5PL_policy_profile_t profile,
                                           char *name, size_t size);

H5_DLL herr_t H5PLget_policy_profile_by_name(const char *name,
                                             H5PL_policy_profile_t *profile);

H5_DLL herr_t H5PLget_policy_profile_definition(
    H5PL_policy_profile_t profile, H5PL_policy_definition_t *definition);

H5_DLL herr_t H5PLset_policy_definition(
    hid_t fapl_id, const H5PL_policy_definition_t *definition);

H5_DLL herr_t H5PLget_policy_definition(
    hid_t fapl_id, H5PL_policy_definition_t *definition);
```

`H5PLget_policy_profile_name()` returns the CLI spellings `legacy`,
`trusted-fast`, `untrusted-strict`, and `forensic`.
`H5PLget_policy_profile_by_name()` accepts those spellings and the exact JSON
report spellings `trusted_fast` and `untrusted_strict`; `legacy` and `forensic`
are identical in both forms. No other punctuation folding or case conversion
is performed. This prevents every application from growing its own spelling
table when it transfers a profile from an h5policy report or configuration
file.

`H5PLget_policy_profile_name()` follows the established `H5PLget()` buffer
contract: it returns the required string length excluding the terminating NUL;
with a non-NULL buffer it writes a NUL-terminated, possibly truncated value.
Invalid enum or string values fail rather than selecting a fallback.
`H5PL_POLICY_PROFILE_CUSTOM` has the diagnostic spelling `custom`, but the
by-name function rejects it because a name alone contains no definition.
`H5PLset_policy_profile()` likewise rejects `CUSTOM`; only
`H5PLset_policy_definition()` can supply the required value.

Although the functions have the H5PL prefix, the property lives on a FAPL.
That keeps plugin policy in the plugin module while giving it the same copying
and lifetime behavior as other file-open choices. The setter accepts a real
file-access property-list identifier, not `H5P_DEFAULT`. A newly created FAPL
contains `H5PL_POLICY_PROFILE_LEGACY`, preserving current application behavior.
The getter may accept `H5P_DEFAULT` and report that resolved default.

### User-defined profile definitions

`H5PLget_policy_profile_definition()` returns a copy of any predefined profile.
It rejects `CUSTOM`, which has no single predefined value. The caller can
change any fields in a returned copy and pass the result to
`H5PLset_policy_definition()`. This clone-and-adjust operation is the intended
way to create a deployment or run-specific blend: inheritance is resolved by
the application, and the FAPL stores one complete effective value rather than
a base profile plus a sparse override set.

For example, a deployment can begin with `trusted-fast`, retain its resource
budgets, but deny non-core filters and external references:

```c
H5PL_policy_definition_t policy = {
    .version     = H5PL_POLICY_DEFINITION_VERSION,
    .struct_size = sizeof(H5PL_policy_definition_t)
};

if (H5PLget_policy_profile_definition(
        H5PL_POLICY_PROFILE_TRUSTED_FAST, &policy) < 0)
    fail_closed();

policy.features.allow_dynamic_filters = false;
policy.features.allow_external_links  = false;
policy.features.allow_external_storage = false;
policy.resources.max_walk_seconds     = 10;

if (H5PLset_policy_definition(fapl, &policy) < 0)
    fail_closed();
```

The definition is an anonymous value object, not an entry in a mutable global
profile registry. After the custom setter succeeds,
`H5PLget_policy_profile()` returns `H5PL_POLICY_PROFILE_CUSTOM` and
`H5PLget_policy_definition()` returns the effective fields. An application may
keep its own deployment label, but authorization never depends on that label.

Both definition getters require the caller to initialize `version` and
`struct_size`. Version 1 requires the exact size shown above. A later source
release can add a new versioned definition without guessing how much storage
an older binary supplied. The setter copies the complete value; it never keeps
caller-owned pointers.

The setter applies the same configuration validation as
`h5policy_profile_validation_error()`: Boolean fields must be zero or one,
walk budgets must be nonzero and representable, rank and ratio limits must be
valid, disabled compound rules must use consistent sentinels, and the reject
metadata-ratio rule cannot be weaker than the warning rule. Invalid custom
profiles fail before file I/O. The detailed field and sentinel contract remains
the [`H5PolicyProfile` semantics](../h5policy/docs/H5PolicyProfile.md), avoiding
a second prose definition that can drift.

## Lifetime and propagation

`H5Pcopy()` copies the selected profile identity and complete effective
definition. `H5Fopen()` and `H5Fcreate()` snapshot them into the shared file
state; changing or closing the source FAPL afterward has no effect. All object
identifiers opened from that file inherit the same snapshot, including
asynchronous work that outlives the initiating call.

The profile is runtime state, not HDF5 file-format metadata. It is never
written into a file. `H5Fget_access_plist()` returns a FAPL containing the
resolved identity and definition so an application can audit the live file
configuration, including every field of a custom blend.

External-link traversal opens another file and is outside this first H5PL
extension. Its FAPL and profile must be chosen through the existing external-
link access-property machinery. This is not a concern for the denying profiles
when used after h5policy, because those profiles reject external-link metadata,
but native behavior still needs an explicit test and documentation.

## Enforcement contract

For a file whose predefined projection says `deny`, or whose custom definition
sets `features.allow_dynamic_filters` to false, libhdf5 must reject use of a
filter ID outside the core 1-through-6 set:

1. Check the profile when a dataset creation or open path accepts its filter
   pipeline. Rejecting at discovery gives a deterministic error before raw
   data I/O where the metadata is already available.
2. Check again immediately before a filter callback is invoked. This closes
   paths that use delayed metadata decoding or an already registered filter.
3. When lookup would be necessary, check before consulting the plugin cache
   and before searching any plugin path. A denial must cause no filesystem
   search, signature operation, dynamic-library open, or plugin entry-point
   call.
4. Treat a policy denial as a hard error even when the filter carries
   `H5Z_FLAG_OPTIONAL`. Optional execution semantics must not weaken an
   explicit trust-boundary policy.

The error stack should identify the selected profile and numeric filter ID and
should distinguish a policy denial from an unavailable filter. The existing
`H5E_PLUGIN` major class can contain the first implementation; a new public
error class is not required by this proposal.

For an `allow` profile, this API contributes no additional filter restriction.
The existing loading mask, path configuration, filter availability, and any
signature-verification build policy still apply.

In version 1, the other 29 custom fields are carried configuration. They are
available to the preflight handoff and future native validation components,
but they do not alter libhdf5 behavior merely because H5PL stores them. Public
documentation and getters must preserve that distinction.

## Composition with existing controls

The effective decision is an intersection, never a precedence rule that can
weaken an older restriction:

```text
effective permission
    = selected file profile
    AND H5PL loading-state bit
    AND HDF5_PLUGIN_PRELOAD hard disable
    AND build/runtime signature requirement, when enabled
```

Consequently, `trusted-fast` and `legacy` cannot re-enable filter loading after
`H5PLset_loading_state()` clears `H5PL_FILTER_PLUGIN`, and no profile can
override `HDF5_PLUGIN_PRELOAD=::`. Search-path APIs remain global discovery
configuration and are not consulted for a denying file.

A signature requirement remains orthogonal. This proposal does not make
`trusted-fast` mean "signed" and does not make a signature sufficient for
authorization. Applications using that profile are expected to apply the
separate controls appropriate to their deployment, matching h5policy's current
description of allowed filters as "separately controlled."

## Application handoff

A consumer can keep the assessed and native phases aligned without asking
libhdf5 to parse h5policy JSON:

```c
H5PL_policy_profile_t profile;
hid_t                 fapl;
hid_t                 file;

/* The application has already required a complete, acceptable h5policy
 * report and extracted its exact JSON profile string (for example,
 * "untrusted_strict"). */
if (H5PLget_policy_profile_by_name(report_profile, &profile) < 0)
    fail_closed();

fapl = H5Pcreate(H5P_FILE_ACCESS);
if (fapl < 0 || H5PLset_policy_profile(fapl, profile) < 0)
    fail_closed();

file = H5Fopen(path, H5F_ACC_RDONLY, fapl);
```

Passing only the profile string is not proof that preflight succeeded. The
application must separately require supported JSON, the expected schema and
path encoding, a complete analysis, and an acceptable decision before this
handoff.

For a custom profile, the application must pass the same complete effective
definition to both phases. A profile label such as `deployment-strict` is not
enough. A production interchange format should serialize all 30 leaf fields in
canonical group and field order and include a digest in the h5policy report;
that cross-tool serialization is a companion change, not part of the C ABI in
this draft.

## Compatibility

The enum, structures, and functions are additive ABI. Existing applications
retain the legacy behavior because the default FAPL uses `legacy`; the current
global loading-state and path APIs remain source- and behavior-compatible.
Language bindings can expose the predefined enum and complete custom value
without reproducing preset values or validation logic.

The profile names are stable API tokens, while their broader h5policy presets
may evolve. H5PL promises only the projection in this document. If a future
h5policy version changes the meaning of `allow_dynamic_filters`, the checked
documentation contract in this repository must fail until the projection is
reviewed.

## Required implementation work

This proposal is intentionally more than four aliases for the existing global
mask:

1. Add the enum, versioned nested structures, preset/string conversion,
   validation, FAPL properties, and public API functions.
2. Copy the resolved identity and complete definition into shared file state
   during open/create.
3. Carry file context to filter-pipeline validation and invocation sites.
4. Identify the library's core filter implementations independently of mutable
   registration state.
5. Gate non-core pipelines before discovery and again before callback use.
6. Preserve the existing process-global mask as an upper bound.
7. Document the C API and add language-binding constants where supported.

The plugin cache does not need to be partitioned merely to prevent new loads,
but cached plugin provenance must remain identifiable so a denying file cannot
execute cached external code through the filter registry.

## Verification plan

The upstream test matrix should cover:

- enum/string and predefined-definition round trips, invalid values,
  `H5Pcopy()`, `H5P_DEFAULT`, and `H5Fget_access_plist()`;
- all 30 fields of each predefined definition against the h5policy source;
- clone-and-adjust blends, complete custom round trips, unsupported definition
  versions and sizes, invalid Boolean/sentinel/range combinations, and proof
  that retrieving or changing a copy does not mutate a predefined value;
- all four profiles against core and non-core pipeline metadata;
- custom profiles with `allow_dynamic_filters` both false and true;
- dynamically discovered, already cached, and programmatically registered
  non-core filters;
- dataset create, open, read, and write paths, including optional filters;
- proof that a denial performs no path scan, signature check, library load, or
  plugin callback;
- intersection with every `H5PLset_loading_state()` filter-bit state and with
  `HDF5_PLUGIN_PRELOAD=::`;
- builds with signature verification on and off;
- concurrently active files with opposite predefined and custom policies in a
  thread-safe build;
- confirmation that VOL and VFD behavior is unchanged; and
- exact error-stack classification for policy denial versus missing plugin.

An integration test should run h5policy on one non-core-filter fixture under
all four profiles, transfer the reported profile name through the conversion
API, and confirm that the native H5PL/H5Z outcome follows the table above.

## Alternatives considered

**A new process-global profile setter.** This matches the current H5PL state
model but cannot safely serve two files with different trust boundaries. A
set/open/restore sequence also leaves delayed dataset reads and other threads
outside the intended scope.

**Four aliases for loading-state masks.** The h5policy profiles do not define
VOL or VFD policy, and the current loading mask cannot stop an already
registered non-core filter callback. Aliases would overstate enforcement.

**A mutable process-global registry of named custom profiles.** Global names
create replacement and lifetime races, and a name is not an authorization
property. Complete definitions copied into FAPLs give each file stable value
semantics; deployment configuration can still map its own names to those
values.

**Sparse overrides stored beside a base profile.** That representation makes
the meaning of an open file depend on later changes to a predefined template
and complicates audit output. The API can offer clone-and-adjust ergonomics
while storing only the resolved 30-field definition.

**Import the complete h5policy report into libhdf5.** That would couple H5PL to
a separate report schema, duplicate validation-boundary decisions, and invite
applications to confuse profile selection with proof of a successful
assessment. The application is the right place to verify the report and pass
the small native setting onward.

**Make `trusted-fast` require a signature.** h5policy currently says allowed
filters require separate control; it does not specify a signer, keystore, or
signature policy. Signature requirements should remain explicit and
independently configurable.

## Open questions

- Should a denying profile reject non-core filter metadata at `H5Dopen()`, or
  only when an operation would activate the filter? Early rejection is easier
  to audit; delayed rejection preserves more metadata-only inspection use
  cases.
- Should the default be named `legacy`, as proposed for exact compatibility,
  or should a fifth `H5PL_POLICY_PROFILE_DEFAULT` value resolve to a configured
  library default while the getter reports both requested and effective values?
- Does HDF5 want the four profile identifiers and complete custom structure in
  H5PL, or should a new cross-module policy interface own the value while H5PL
  consumes only `allow_dynamic_filters`? H5PL is the immediate enforcement
  boundary, but 29 fields belong to validation and analysis rather than plugin
  loading.
- Should the first release standardize the custom-profile serialization and
  digest used by h5policy reports, or ship only the in-process C value and add
  cross-process interchange after the native semantics settle?
- Should a later version add explicit policy for VOL/VFD activation sources,
  trusted search roots, or signer identities? Those controls need their own
  threat model and must not be inferred from today's h5policy profiles.
