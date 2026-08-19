# A CVE strategy for the HDF5 library

Are we winning the war against CVEs? The HDF5 library has a long history of CVE fixes, but the fixes are often isolated and ad hoc. This document proposes a more systematic approach to CVE mitigation.

## Summary

HDF5 should separate four activities that are currently often interleaved:

1. Reading and locally decoding bytes.
2. Discovering references to other file regions or files.
3. Validating record, object, and reference-graph semantics.
4. Constructing and activating native HDF5 objects.

The principal security benefit does not come from adopting a particular byte-stream abstraction. Straightforward rewrites using explicit buffer sizes, bounds checks, checked arithmetic, bounded allocation, and progress checks should address many local decoder vulnerabilities.

The more important architectural change is that successfully parsing fields must not authorize the library to follow references, update global state, count objects, load plugins, open files, or construct native objects. Those actions require semantic validation in the appropriate structural context.

The desired pipeline is:

```text
bounded fetch
    ↓
local raw decode
    ↓
local semantic validation and reference discovery
    ↓
bounded reference resolution
    ↓
object and graph semantic validation
    ↓
validated object description
    ↓
native materialization and activation
```

**Validation remains lazy:** opening one object validates the closure needed for that object, not the entire file.

## Motivation

Many decoder vulnerabilities are ordinary implementation errors:

- Reading a field without checking that enough input remains.
- Computing an inclusive last-byte pointer as `buffer + length - 1` when `length` may be zero, thereby forming an out-of-bounds pointer.
- Overflowing a size calculation.
- Allocating from an unchecked encoded count.
- Failing to prove that a loop consumes input.

These should be fixed through a relatively small rewrite that establishes safe decoding conventions. A cursor or slice type may help enforce those conventions, but is not itself the architectural objective.

The harder vulnerabilities occur when individually well-formed values create an invalid larger structure. Examples include:

- An object-header continuation referencing part of itself or overlapping another chunk.
- A continuation graph causing messages to be counted more than once.
- A shared message recursively resolving through itself.
- A compound datatype member extending beyond its enclosing datatype.
- A chunk index or heap containing structurally inconsistent references.
- An external link causing an unexpected file or path to be opened.
- A valid filter identifier causing dynamic plugin loading during validation.
- A cache image publishing entries before the complete dependency graph has been checked.

Local bounds checking cannot detect these conditions. They require semantic validation over a record, an aggregate object, or a graph of referenced records.

## Goals

The design should provide the following properties:

- Every decoder receives an explicit byte extent.
- Every byte access, size calculation, and allocation is checked.
- Raw decoding produces inert data and references, not native HDF5 objects.
- References are validated before being followed.
- Traversal is bounded by depth, node, byte, allocation, hop, and operation limits.
- Cross-record and graph invariants are checked before native construction.
- Parsing and validation cannot load plugins, decompress data, open external files, invoke user callbacks, or mutate live cache state.
- Validation failures have stable classifications and useful byte locations.
- Format compatibility can be preserved without weakening memory-safety invariants.
- Record families can be migrated incrementally.

## Non-goals

This proposal does not require:

- A particular cursor, span, or slice implementation.
- Rewriting every decoder before any benefit is obtained.
- Validating an entire file before opening one object.
- Treating all cycles or repeated references as corruption.
- Rejecting unknown optional messages solely because they are unknown.
- Immediately changing default compatibility behavior.

## Terminology

**Raw record:** An inert representation of encoded fields. It may contain offsets, lengths, integers, bounded strings, and child references, but no initialized `H5O_t`, `H5T_t`, `H5S_t`, cache entry, plugin, or external-file handle.

**Child reference:** A typed description of another region or resource, such as `{kind, address, extent}`. It does not follow or load the target.

**Validation closure:** The set of raw records that must be inspected to establish the semantics needed for a requested operation. It is generally smaller than the entire file.

**Validated record:** An opaque internal value proving that the required local and contextual validation has succeeded.

**Materialization:** Construction of native HDF5 structures from validated descriptions.

**Activation:** Operations with side effects, including cache publication, public ID registration, index initialization, plugin loading, decompression, user callbacks, and external-file access.

## 1. Safe local decoding

Existing decoders should be rewritten around a small set of rules:

- An explicit input pointer and size are mandatory.
- The decoder checks availability before each read.
- Addition, multiplication, alignment, and address calculations are checked.
- Attacker-controlled counts are validated and charged against a budget before allocation.
- Every variable-length loop demonstrates forward progress.
- Searches for string terminators or delimiters examine only the validated byte extent assigned to the string and never continue into an adjacent field or beyond the enclosing record.
- The decoder distinguishes required complete consumption from permitted trailing or opaque data.
- Failures identify the field and absolute input offset where possible.

These rules may be implemented with a cursor, pointer plus remaining length, or another convention. A common helper library would improve consistency and reviewability, but the security contract matters more than the representation.

A bounded mode must never substitute `SIZE_MAX` for a missing input extent. Bounded decoding requires the caller to provide or establish the actual number of readable input bytes. An unknown extent must not be represented as `SIZE_MAX`, because doing so disables the bounds checks.

The important distinction is that `SIZE_MAX` may sensibly represent an unlimited policy budget in some contexts, but it must not represent an unknown physical input extent.

 Existing size-less APIs therefore cannot provide the bounded guarantee and will eventually need size-aware alternatives or explicit legacy status.

## 2. Raw records must be inert

A raw decoder may allocate a bounded raw representation, preferably from an allocation-accounted arena. It must not:

- Construct format-derived native HDF5 objects.
- Perform another metadata read.
- Follow a continuation or shared-message reference.
- Traverse an external link or VDS source.
- Load or query a dynamically loaded plugin.
- Decompress a payload.
- Insert or update metadata-cache entries.
- Invoke application callbacks.
- Repair encoded data or mark an object dirty.

This should be enforced by API design: raw decoders receive bytes, a validated geometry snapshot, immutable limits, and diagnostic state—not an `H5F_t *` or other live capability.

## 3. Semantic validation occurs at three scopes

### Record-local validation

This validates relationships contained in one record:

- Legal version and flag combinations.
- Count and encoded-length consistency.
- Valid enum values and reserved bits.
- Checked dimensions and element counts.
- Datatype member extents.
- Required terminators and padding.
- Legal child-record kinds.

For example, a compound datatype validator computes each member end using checked arithmetic and verifies that it fits within the enclosing datatype before an `H5T_t` is constructed.

### Aggregate-object validation

This validates relationships among messages that describe one logical object:

- Required and duplicate message rules.
- Datatype, dataspace, and layout compatibility.
- Filter-pipeline applicability.
- Fill-value size relative to datatype.
- Compact payload size.
- Chunk dimensionality relative to dataspace rank.
- Consistency among VDS, EFL, layout, and storage messages.

The aggregate validator operates on raw or locally validated message descriptions. Dataset layout/index initialization must wait until it succeeds.

### Reference-graph validation

This validates structures assembled through addresses or paths:

- Continuation chunks.
- Shared messages and shared-object-header messages.
- Heaps and free-space structures.
- B-trees and chunk indexes.
- Cache-image dependency graphs.
- External links, EFL entries, and VDS mappings.

Reference-graph validation is the central focus of this proposal.

## 4. Reference discovery and traversal

Raw decoders return typed child references to a traversal coordinator. *The coordinator is the only component allowed to perform secondary reads.*

It maintains:

- A work queue.
- Discovered, pending, decoded, and validated node states.
- Exact or interval-based tracking of referenced file regions.
- Cumulative byte, node, allocation, depth, hop, and step limits.
- Per-reference-type overlap and cycle rules.
- A bounded collection of findings.

Before following a reference, the coordinator checks:

- Address and extent arithmetic.
- File bounds and applicable allocation bounds.
- Minimum and maximum legal extent.
- Whether the target overlaps its source message or source chunk.
- Whether it overlaps another region where overlap is forbidden.
- Whether it is already pending or validated.
- Whether following it would exceed a traversal budget.
- Whether the edge type is permitted by the active policy.

Cycles must be interpreted according to the structure. Group-link cycles may be legitimate and merely stop traversal. Cycles in object-header continuations, B-tree ancestry, or cache dependencies may be corrupt. A universal “all repeated addresses are invalid” rule would be incorrect.

## 5. Object-header continuations

Object-header continuations should be an early migration target because they illustrate the difference between local and semantic safety.

Raw decoding of a continuation produces something like:

```text
ContinuationRef {
    target_address,
    target_size,
    source_message_range,
    source_chunk_range
}
```

Local validation checks that the fields are completely encoded and that address/size arithmetic is representable.

The object-header graph validator then establishes that:

- The target is within the permitted file region.
- The target does not point into the continuation message itself.
- The target does not improperly overlap the current or another object-header chunk.
- The reference does not create a forbidden pending-node cycle.
- Each accepted chunk contributes to the logical object header only once.
- Traversal makes progress and stays within its budgets.
- Every chunk envelope and checksum is valid.

Message counts should be computed from the final set of validated, unique chunks. They should not be incrementally trusted while attacker-controlled continuations are still being followed.

Only after the complete required continuation closure has passed validation should an `H5O_t` be constructed or published.

## 6. Materialization and activation

Validation returns an opaque internal certificate:

```text
Raw<T> → validate → Validated<T> → materialize → Native<T>
```

The materializer should not accept an unvalidated raw record. For aggregate objects, an aggregate certificate proves that relevant cross-message rules have also succeeded.

Historical compatibility repairs should be represented as an explicit normalization plan produced by validation. *The parser must not silently modify values.* The materializer may apply authorized normalizations under the compatibility profile.

Construction should be transactional where partial publication is dangerous. Cache images, for example, should follow:

```text
decode all inert entries
    → validate all entry ranges and sizes
    → validate unique addresses and dependency graph
    → construct temporary native entries
    → publish the set transactionally
```

A failure before publication discards the temporary state without changing the live cache.

## 7. Format constructs requiring controlled activation

External links and VDS mappings are decoded as bounded strings and inert references. Validation may determine that they are syntactically and semantically valid without opening their targets. External access occurs only during an explicitly authorized activation step.

Filter pipelines are similarly enumerated without loading plugins. Validation may report whether an identifier names a built-in or already registered filter, but dynamic loading occurs later under policy control.

Compressed metadata should use a separate bounded transformation stage with limits on output size and expansion ratio. The decompressed result becomes a new explicit input region for another raw decoder.

## 8. Findings and profiles

Findings should distinguish:

- `CORRUPT_*`: invalid encoding or semantics.
- `RESOURCE_*`: a configured byte, node, depth, allocation, or operation limit was reached.
- `POLICY_*`: an otherwise meaningful operation is prohibited, such as external traversal.
- `UNSUPPORTED_*`: a record is well bounded but lacks a migrated validator or supported version.

Each finding should include a stable code, severity, absolute file offset, record kind, and field or graph path. Finding storage itself must be capped.

Suggested profiles are:

- **Compatibility:** hard safety invariants, historical semantic allowances, and generous measured limits.
- **Trusted-fast:** optimized bounded validation for provenance-trusted inputs.
- **Strict:** specification-oriented semantic validation without implicit repair.
- **Forensic:** strict limits, bounded finding collection, and no materialization or activation.

Hard memory, arithmetic, range, and progress invariants are mandatory under every profile. Hence, these are named presets over separate dimensions—resource budgets, feature policy, compatibility policy, and analysis depth—rather than four fundamentally different safety levels.

Unknown optional messages may be retained as bounded opaque records if the format and requested operation permit that. If their interpretation is required, the result is unsupported rather than silently passed to an unsafe legacy decoder.

## 9. Integration with the current implementation

The existing object-header machinery already provides an incremental seam: `H5O_mesg_t` retains raw bytes separately from its native representation, and `H5O_LOAD_NATIVE` centralizes lazy native decoding in [H5Opkg.h](https://github.com/HDFGroup/hdf5/blob/4d666721f42f8f739152021a23775a16d676c8b1/src/H5Opkg.h#L163).

A companion raw-operations table can initially be keyed by object-header message ID:

```text
raw_decode
validate_local
materialize
```

This avoids changing every existing message-class initializer at once. For migrated classes, `H5O_LOAD_NATIVE` uses the new path. A failed raw decode or validation must never fall through to the legacy decoder.

This is transitional. The final object-header path needs a raw object-header representation because the current cache deserializer begins constructing and mutating `H5O_t` during envelope processing in [H5Ocache.c](https://github.com/HDFGroup/hdf5/blob/4d666721f42f8f739152021a23775a16d676c8b1/src/H5Ocache.c#L1170).

Other important integration points include:

- Central metadata-read and allocation checks in [H5Centry.c](https://github.com/HDFGroup/hdf5/blob/4d666721f42f8f739152021a23775a16d676c8b1/src/H5Centry.c#L1010).
- Continuation coordination in [H5Oint.c](https://github.com/HDFGroup/hdf5/blob/4d666721f42f8f739152021a23775a16d676c8b1/src/H5Oint.c#L1015).
- Recursive datatype decoding in [H5Odtype.c](https://github.com/HDFGroup/hdf5/blob/4d666721f42f8f739152021a23775a16d676c8b1/src/H5Odtype.c#L109).
- Shared-message resolution in [H5Oshared.c](https://github.com/HDFGroup/hdf5/blob/4d666721f42f8f739152021a23775a16d676c8b1/src/H5Oshared.c#L289).
- Transactional cache-image reconstruction in [H5Cimage.c](https://github.com/HDFGroup/hdf5/blob/4d666721f42f8f739152021a23775a16d676c8b1/src/H5Cimage.c#L2435).

A complete file-level bounded guarantee also requires a bounded superblock/bootstrap path. Until then, claims should be scoped to migrated record families rather than the entire open operation.

## 10. Incremental implementation

### Phase 1: Local decoding conventions

Introduce checked arithmetic, allocation accounting, explicit-size requirements, findings, and direct byte-array tests. Whether this uses a cursor is an implementation choice.

Apply the conventions immediately to new code and ordinary bounds-related CVE fixes.

### Phase 2: First semantic vertical slice

Migrate one complete record through raw decode, validation, and materialization. An explicit-buffer datatype entry point is a useful pilot, though the next suitable CVE may provide a better target.

The pilot must include a genuine semantic invariant, not merely truncated-input handling.

See Appendix A for a detailed description of the pilot’s scope, interfaces, and test requirements.

### Phase 3: Object-header continuations

Introduce inert continuation references, interval tracking, pending-node detection, traversal budgets, validated unique message counting, and delayed `H5O_t` construction.

### Phase 4: Core object semantics

Migrate datatype, dataspace, selection, attribute, layout, pipeline, and fill messages. Add aggregate dataset validation before layout and index initialization.

### Phase 5: Reference-bearing structures

Migrate shared messages, heaps, SOHM, free-space managers, B-trees, chunk indexes, external links, EFL, and VDS. All secondary access goes through the coordinator.

### Phase 6: Cache and bootstrap

Implement decode-all/validate-all/promote for cache images and migrate the superblock bootstrap sufficiently to support an end-to-end bounded mode.

### Phase 7: Adoption

Add public profiles or a forensic file-image inspection API after internal semantics stabilize. Make the bounded path the default only after compatibility, performance, and coverage criteria are met.

## 11. Embedding the design in the CVE process

This section is an HDF5-specific engineering addendum to the normal vulnerability-management and disclosure process. It applies when a security report involves attacker-controlled encoded data, metadata traversal, native construction, or activation. CVEs outside that area continue to use the normal process.

The design should be embedded in every stage of a decoding-related CVE, rather than treated as a separate hardening project. However, an urgent fix must not be delayed until a large architectural migration is complete.

### 11.1 Two outcomes and two completion states

Every applicable CVE should produce two explicitly linked outcomes:

1. **Containment:** the smallest safe fix for supported release branches.
2. **Systemic closure:** enforcement of the missing invariant at the correct semantic boundary on the development branch.

These outcomes may be separate changes. The containment change lands on the development branch first and is then backported according to the supported-release policy. If the systemic change is too large or risky for the embargoed fix, it becomes a linked private follow-up with an owner and milestone. Its tracking can be made public at disclosure.

The process should distinguish two completion states:

- **Release fixed:** the known exploit path is blocked on supported branches and the end-to-end PoC no longer succeeds.
- **Systemically closed:** the invariant is enforced at the correct semantic boundary, adjacent variants have been audited, and the direct tests, fuzz corpus, and coverage manifest have been updated.

A release may be fixed before the issue is systemically closed, but the architectural disposition must not be lost when the CVE is published or the release is shipped.

### 11.2 Triage by missing invariant

Triage should classify *the first incorrect security decision*, not merely the eventual crash site or CWE. One issue may have more than one classification.

| Classification | Typical missing invariant |
|---|---|
| Local decode safety | Explicit extent, checked arithmetic, bounded allocation, or forward progress |
| Record-local semantics | Relationships among fields in one record, such as a compound member exceeding its enclosing datatype |
| Aggregate-object semantics | Relationships among messages describing one object, such as datatype, dataspace, and layout compatibility |
| Reference-graph semantics | Target range, overlap, aliasing, uniqueness, cycle, traversal, or counting rules |
| Premature activation | Native construction, cache publication, plugin loading, decompression, callbacks, or external access before validation |

The triage record should identify:

- The affected record family, versions, and public or internal entry points.
- The violated invariant.
- The validation closure required to establish that invariant.
- Native state or activation reachable before the failure was detected.
- Whether the same pattern is present in sibling versions, record types, or resolvers.

For example, a later allocation failure caused by a continuation pointing into its own object header is primarily a reference-graph defect, not an allocation defect.

### 11.3 Select the smallest complete semantic boundary

The development fix should migrate the **smallest complete semantic boundary** containing the violated invariant. That boundary is not necessarily one encoded record:

- A truncated scalar may require only its record decoder.
- A compound member extending beyond its parent requires the complete datatype record.
- Incompatible layout and dataspace messages require the aggregate dataset description.
- A continuation self-reference requires the object-header continuation closure.
- A cache-image dependency cycle requires the complete dependency graph represented by the image.

This keeps migration incremental without forcing graph or aggregate vulnerabilities into an artificially local fix.

### 11.4 Preserve two forms of the reproducer

Every applicable CVE should retain:

1. The original full-file or public-API PoC, demonstrating that the complete exploit path is closed.
2. The smallest practical direct raw-record, aggregate-object, or reference-graph fixture, demonstrating that the invariant itself is enforced.

The direct test should assert, where the necessary infrastructure exists:

- The stable finding or error classification and relevant byte offset or structural path.
- Failure before native construction or cache publication.
- No plugin load, decompression, external open, or user callback.
- No fallback to a legacy decoder after raw decode or validation fails.

During an embargo these artifacts remain in the private advisory or security fork. After disclosure, minimized cases and semantic variants should be promoted to the appropriate public regression and fuzz corpora.

### 11.5 Plan containment and systemic remediation together

The private advisory or security ticket should track both changes, even when they are implemented separately:

```text
Affected record and versions:
Affected entry points:
Root-cause classification:
Violated invariant:
Required validation closure:
Activation reached before validation:
Supported-release containment:
Development semantic boundary:
Expected finding or error:
Direct regression fixture:
Integration PoC:
Fuzz seed and sibling audit:
Coverage-manifest change:
Compatibility and backport risks:
```

The systemic implementation places checks according to their scope:

- Extent, representation, arithmetic, allocation, and progress checks belong in raw decode.
- Cross-field rules belong in record-local validation.
- Cross-message rules belong in aggregate-object validation.
- Overlap, aliasing, cycle, uniqueness, counting, and traversal rules belong in the graph coordinator or graph validator.
- Native construction and activation require the corresponding validation certificate.

Once a class has migrated, validation failure must never fall through to its legacy decoder. Hard memory-safety and progress checks apply under every compatibility profile.

#### Private repository-advisory handoff

The case bundle should also contain a private repository-advisory draft. It is
prepared after triage and verification, and it is not a substitute for the case
record or an authorization to create or publish anything remotely.

The draft must supply the repository form's current fields:

- a title and the choice to supply an existing CVE identifier or request one
  later;
- a description covering summary, impact, patches, workarounds, and references;
- one affected-product entry per disjoint vulnerable version range, with the
  ecosystem, package name, affected versions, patched versions, and vulnerable
  functions;
- severity and CVSS vector, weaknesses, and optional credits.

Use one lower/upper-bound range per affected-product entry, for example
`>= lower, < upper`. Multiple disjoint ranges require separate entries. Before
an authorized maintainer creates the private draft, compare the local handoff
against the authenticated [HDF5 draft advisory form](https://github.com/HDFGroup/hdf5/security/advisories/new); the form, not this document, remains authoritative. Creation,
inviting collaborators, identifier requests, and publication are separate
authorization boundaries.

The [`h5cve`](TOOLS.md#h5cve-case-orchestrator) initializer creates
`cases/<id>/github-advisory.md` with these headings. The form instructions and
version-range guidance are maintained by [GitHub's repository-advisory
documentation](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/fix-reported-vulnerabilities/create-repository-advisory).

### 11.6 Require invariant-focused review

A decoding-related security change should receive both format and security review. Reviewers should verify:

- That the stated invariant matches the format and compatibility requirements.
- That it is enforced at the correct semantic boundary and before native construction or activation.
- That all relevant entry points and encoded versions reach the check.
- That error cleanup cannot publish partial native or cache state.
- That the patch covers adjacent variants rather than only the exact crashing value.
- That release-branch differences do not invalidate the backport.

For reference-bearing structures, the review should explicitly consider self-reference, partial overlap, duplicate targets, references to pending nodes, valid sharing, structure-specific cycles, non-progress, and resource exhaustion.

### 11.7 Make both test layers release gates

The existing full-file [CVE regression workflow](https://github.com/HDFGroup/hdf5/blob/4d666721f42f8f739152021a23775a16d676c8b1/.github/workflows/cve.yml#L35) should remain the end-to-end exploit-path test. It should be complemented by in-tree tests with exact semantic oracles.

For the containment fix, the release gate is the original PoC plus the applicable sanitizer and compatibility tests. For systemic closure, the gate additionally includes the direct fixture, semantic boundary variants, proof of no premature activation, valid-input differential tests, and a seed for the appropriate bounded raw-decoder fuzzer. Section 12 gives the general verification requirements.

### 11.8 Record post-CVE learning

After disclosure and merge:

- Update a machine-readable manifest by record family, format version, and validation scope.
- Add the minimized input and generated semantic neighbors to the appropriate fuzz corpus.
- Audit sibling decoders and reference resolvers for the same missing invariant.
- Record whether the issue occurred in a migrated or legacy path.
- Track time to containment separately from time to systemic closure.

A mode advertised as bounded must reject unsupported required records instead of falling back. The manifest therefore describes the scope of the guarantee as well as migration progress.

The governing process principle is:

> An urgent CVE patch may contain the known exploit without migrating the affected decoder. Nevertheless, every decoding CVE must record whether the violated invariant is already enforced, is migrated by the same change, or requires a linked systemic follow-up.

A CVE containment patch might add a narrow check to legacy code:

```c
if (member_offset + member_size > compound_size)
    return FAIL;
```

That may safely block the known PoC and be appropriate for supported release branches. But it does not necessarily:

- Decode the datatype into an inert raw representation.
- Put the invariant in a reusable record-local validator.
- Cover every datatype version and entry point.
- Prevent native construction before validation.
- Prevent fallback to another legacy decoder.
- Audit related compound, array, or nested-type cases.
- Add direct semantic tests and bounded-decoder fuzz coverage.

It is therefore a valid CVE fix, but not automatically an architectural migration.

“Explicit architectural disposition” means the CVE record must state what will happen to the missing invariant in the bounded-decoding design. The disposition should be one of:

1. **Migrated by this change:** the CVE fix also enforces the invariant at the correct semantic boundary and meets the systemic-closure criteria.
2. **Already architecturally covered:** the invariant exists in the bounded path, but the CVE exposed an alternate or legacy route; close that route and add coverage.
3. **Contained now, migration scheduled:** the release patch blocks the exploit, while a linked development-branch task migrates the complete semantic boundary, with an owner and milestone.
4. **Not applicable:** the issue is not a decoding-architecture problem, with a recorded explanation.

For example:

```text
CVE symptom:
    native datatype construction writes beyond an allocation

Containment:
    reject the offending member dimensions before the write

Architectural disposition:
    record-local datatype invariant is missing
    required closure is the complete compound datatype
    migrate through RawDatatype → ValidatedDatatype → H5T_t
    cover all relevant entry points and versions
    add direct semantic fixture and fuzz seed
```

The principle prevents two undesirable outcomes:

- Delaying an urgent, low-risk security patch until a large rewrite is ready.
- Shipping the narrow patch and then forgetting that the underlying invariant remains misplaced or absent.

## 12. Verification

Every migrated record family should include:

- Truncation at every byte boundary.
- Zero, maximum, and `N-1/N/N+1` count and extent tests.
- Integer overflow and allocation-budget tests.
- Deep nesting and non-progress cases.
- Self-reference, overlap, duplicate-reference, and structure-specific cycle cases.
- Stable finding-code and offset assertions.
- Tests proving that validation failure has no activation side effects.
- Differential tests against legacy decoding for valid files.
- Dedicated in-memory fuzz targets under fixed hardened limits.
- Integrated full-file CVE and OSS-Fuzz coverage.
- Performance measurements demonstrating that validation remains lazy.

## Design conclusion

The required primitive is not a particular cursor or slice type. The required architectural boundary is:

> Parsing bytes may describe structure, but it does not authorize the library to act on that structure.

Local decoder rewrites establish basic memory safety. Semantic validators establish whether records form a valid object. A bounded coordinator establishes whether references form a valid and affordable traversal. Only after those stages succeed may HDF5 construct or activate native state.

## Appendix A

Phase 2 should be the first end-to-end proof that the architecture works—not merely the first use of a bounded cursor. It should take one precisely scoped record from untrusted bytes all the way to a native object while preserving the trust boundary:

```text
bytes + exact extent
    → Raw<T>
    → validate semantic invariants
    → Validated<T>
    → materialize
    → Native<T>
```

“Complete” means every input path within the declared pilot scope uses this sequence. A decode or validation failure must terminate that path; it cannot fall back to the legacy decoder.

Select one precisely scoped record family, supported-version set, and entry point, and migrate it completely through raw decoding, semantic validation, and native materialization. An internal datatype entry point that accepts an explicit byte buffer and extent is a useful pilot, although a suitable CVE may identify a better first boundary.

The pilot should establish the following interfaces:

- **Raw decoding** accepts immutable bytes, their proven extent, and applicable resource limits. It performs checked arithmetic and bounded allocation and returns only inert fields, bounded child slices, references, and findings. It does not construct an H5T_t or mutate existing native state.
- **Semantic validation** consumes the raw record and establishes the record-local invariants required for construction. Success returns an opaque validated result; compatibility handling, if needed, is represented as an explicit normalization plan.
- **Materialization** accepts only the validated result. It constructs the native object transactionally and does not reinterpret the original unvalidated bytes.
- **Dispatch** sends migrated inputs through the new path. Raw-decode and validation failures are terminal and never fall through to the legacy decoder. The legacy path remains reachable only for record classes or versions explicitly outside the pilot’s declared scope.

For a compound datatype, the semantic test should include an invariant such as:

```txt
member_end = checked_add(member_offset, validated_member_size)
member_end <= enclosing_compound_size
```

A fixture in which all encoded fields are present but a member extends beyond the enclosing datatype is therefore essential. It proves that the phase adds semantic validation, not just truncated-input detection.

The pilot’s test set should cover:

- Valid records for every class and version claimed by the pilot.
- Zero, boundary, `N−1`, `N`, and `N+1` extents and counts.
- Arithmetic overflow and allocation-budget exhaustion.
- Unterminated strings and incomplete child records.
- Nested records at and beyond the recursion limit.
- At least one fully encoded but semantically inconsistent record.
- Stable finding codes and byte ranges for each rejection.
- Proof that rejection occurs before native construction or publication.
- Differential behavior against the legacy decoder for valid inputs.
- Explicit compatibility-normalization tests where historical behavior is retained.
- Bounded fuzzing of the raw decoder and validator.
- Sanitizer testing and representative 32-bit and 64-bit builds, particularly around encoded-size conversion and size_t arithmetic.
- Performance measurements for the valid-input path.

The phase is complete when:

1. The declared pilot scope has no route from failed validation to legacy decoding.
2. Native construction cannot be invoked without a validated result.
3. Every byte access and allocation is derived from a proven extent and budget.
4. At least one non-local field relationship is validated before construction.
5. Failure cleanup leaves no partially published native state.
6. Valid-input compatibility and performance have been measured.
7. The migrated scope, unsupported cases, findings, and tests are documented.

The phase should not claim a bounded file-open operation. Superblock bootstrap, object-header continuation graphs, shared messages, and aggregate dataset semantics remain outside the guarantee until their later phases are complete.

The point of the vertical slice is to expose the difficult integration questions early: ownership of raw bytes, validated-result lifetime, cleanup, normalization, dispatch, findings, and prevention of legacy fallback. Migrating several parsers only through local bounds checks would defer all those architectural risks.
