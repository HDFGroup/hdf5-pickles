# Repository glossary

This glossary defines terms as this repository uses them.  It is deliberately
more specific than their everyday testing or HDF5 meanings; links point to the
authoritative workflow or tool documentation when a term has operational
details.

## Inputs and test artifacts

**Fixture**
: A controlled HDF5 input file used to exercise a condition with a known
  contract.  Fixtures can be valid, malformed, policy-denied, resource-bound,
  integration, or CVE specimens.  The corpus generator makes them small and
  deterministic; expectations state the required decision and findings.  Most
  generated fixture files are untracked, while `h5policy/tests/cve/*.h5` is
  tracked and must reproduce byte-for-byte.  See the [corpus
  generator](../h5policy/tools/h5policy-gencorpus) and [test
  layout](../h5policy/tests/README.md).

**Specimen**
: A file treated as evidence in an investigation or test.  A fixture is a
  deliberately controlled specimen; a supplied PoC can be a specimen before it
  is understood or reduced into a fixture.  For example,
  [zero-size chunk expectation](../h5policy/tests/expected/malformed-chunk_zero_stored_size.yml)
  names `malformed/chunk_zero_stored_size.h5` as its specimen.

**PoC / integration PoC**
: The full-file, public-API reproducer of a reported behavior.  In a CVE case
  it is kept separately from the smaller direct fixture, because it proves the
  user-visible integration path rather than only one invariant.  The
  [`cve_2020_10812` generator](../h5policy/tests/cve/make_cve_2020_10812.py)
  creates a complete HDF5 file for such a public-API path.

**Direct fixture**
: The smallest practical raw-record, aggregate-object, or reference-graph
  fixture that proves a particular invariant is enforced.  It is the focused
  companion to an integration PoC; for example, the
  [datatype precision-bounds fixture](../h5policy/tests/expected/malformed-bad_datatype_precision_bounds.yml)
  isolates one encoded datatype invariant.

**Reproducer**
: An input plus the command or program needed to demonstrate behavior.  The CVE
  process preserves both an integration PoC and a direct fixture when they are
  applicable.  For example, the
  [`make_mdci_dup_addr_witness.py` program](../h5policy/tests/cve/make_mdci_dup_addr_witness.py)
  and its generated HDF5 file form a cache-image reproducer.

**Corpus**
: The organized collection of regression inputs and their expectation files,
  primarily under `h5policy/tests/`.  It is not merely a bag of files: the
  expected decision, findings, profile, and forbidden outcomes are part of the
  contract.  The [regression-corpus layout](../h5policy/tests/README.md)
  identifies the HDF5 fixture classes and their paired expectations.

**Expectation**
: A YAML test specification in `h5policy/tests/expected/` that associates a
  fixture with a profile and asserts its decision, exit status, findings, and
  other report properties.  One fixture may have more than one expectation;
  [the zero-size chunk expectation](../h5policy/tests/expected/malformed-chunk_zero_stored_size.yml)
  requires the chunk-storage finding and declares its canary contract.

**Canary**
: An exact-build exercise for one registry family, run against a fixture with
  an explicit `h5cve` contract.  A valid canary shows that the exercise can
  complete; a malformed open-successfully fixture is also required to show the
  exercise can reach the defective family surface.  For example, the
  [`chunk_index` canary contract](../h5policy/tests/expected/malformed-chunk_zero_stored_size.yml)
  drives `H5Dopen2`, a point selection, and `H5Dread`.

**Canary contract**
: The `h5cve` block in an expectation.  It names the validation family, whether
  oracle alignment is required, and which matrix statuses are permitted.  An
  absent contract is reported as a coverage gap rather than silently passing;
  the [external-link expectation](../h5policy/tests/expected/policy-external_link.yml)
  explicitly permits the activation `violation` that its HDF5 file demonstrates.

**Variant / semantic neighbor**
: A related input formed by changing one typed semantic condition, usually to
  test boundary cases and siblings of an invariant.  `h5mutate` records the
  parent hash, intended invariant/finding, changed ranges, and checksum reseals
  for its variants; its [recipe implementation](../h5policy/tools/h5mutate)
  includes HDF5 continuation-target and heap-size neighbors.

**Fuzz seed**
: An input retained for a fuzz target so mutations start near a meaningful
  format boundary or known defect.  For example,
  [`sohm_tiny.h5`](../h5policy/tests/coverage/sohm_tiny.h5) starts mutations near
  a compact shared-object-header-message structure.

## Analysis, validation, and policy

**Raw record**
: An inert representation of encoded fields and references.  It contains no
  initialized native HDF5 objects, cache entries, plugins, or external-file
  handles; the [object-header message decoder](../h5policy/pickles/h5_messages.pk)
  produces this kind of description before validation.

**Child reference**
: A typed, inert description of another encoded region or resource, such as an
  address and extent.  Decoding it does not follow, load, or open its target;
  the [continuation family](../registry/validation-coverage.yml) uses an
  `object_header_chunk` child reference.

**Raw decode / bounded raw decode**
: Reading encoded fields from an explicit, bounded byte extent while checking
  availability, arithmetic, sizes, and progress.  It produces inert raw
  records; it does not itself establish cross-record semantics or construct
  native HDF5 state.  The [bounded-raw-decode design](What%20is%20bounded%20raw%20decode.md)
  applies this separation to HDF5 messages and heap blocks.

**Validation closure**
: The set of raw records that must be inspected to establish the semantics
  needed for an operation.  It is normally smaller than the whole file; for an
  HDF5 continuation message, the
  [closure](../registry/findings/catalog/object_header_continuation.yml) includes
  the reachable continuation chunks and their non-overlap relationships.

**Invariant**
: A format, arithmetic, range, progress, graph, or policy condition that must
  hold for safe handling.  CVE triage is organized around the *missing
  invariant*, rather than the eventual crash location or a generic error code.
  For example, `chunk.stored_size` in the
  [coverage manifest](../registry/validation-coverage.yml) requires stored
  filtered-chunk bytes to cover the filter framing.

**Semantic boundary**
: The smallest complete set of records, relationships, and entry points where
  an invariant can be established correctly.  It can be larger than one encoded
  record.  For example, the external-file-list boundary includes both the EFL
  message and the local-heap path it references in the
  [coverage manifest](../registry/validation-coverage.yml).

**Validated record / validation certificate**
: The conceptual opaque value returned after the local and contextual checks
  for a raw record have passed.  Only such validated descriptions may be
  materialized in the design described by the
  [CVE strategy](A%20CVE%20strategy%20for%20the%20HDF5%20library.md#6-materialization-and-activation).

**Materialization**
: Construction of native HDF5 structures from validated descriptions.  It is
  separate from raw decoding and validation so malformed bytes cannot directly
  create native state.  For example, an encoded datatype description becomes a
  native HDF5 datatype only at the materialization stage described in the
  [CVE strategy](A%20CVE%20strategy%20for%20the%20HDF5%20library.md#6-materialization-and-activation).

**Activation**
: An operation with side effects or externally consequential work, including
  cache publication, ID registration, index initialization, plugin loading,
  decompression, callbacks, or external-file access.  Validation must precede
  any activation that depends on untrusted content.  The
  [external-link policy fixture](../h5policy/tests/expected/policy-external_link.yml),
  for example, detects an HDF5 traversal that opens another file.

**Activation event**
: An activation that the exact-build probe can observe at the OS boundary,
  currently including file opens, `dlopen`, writes, and network operations.
  Internal events such as cache insertion are outside that probe's visibility;
  the [probe report schema](../h5policy/tools/probe/README.md) records observable
  HDF5 external opens separately from plugin loads.

**Profile**
: A named policy preset that combines budgets, feature permissions,
  compatibility behavior, and analysis depth.  The shipped presets are
  `legacy`, `trusted-fast`, `untrusted-strict`, and `forensic`; all retain hard
  safety invariants.  Their HDF5 feature and resource settings are listed in the
  [`h5policy` profile guide](../h5policy/README.md#profiles).

**Forensic profile**
: The profile intended for bounded investigation: it continues reporting where
  configured, never follows external references, and does not materialize or
  activate untrusted content.  The
  [`h5policy` profile guide](../h5policy/README.md#profiles) shows its HDF5
  traversal and reporting contract.

**Finding**
: A stable, located report of a detected condition.  Findings distinguish
  corruption (`CORRUPT_*`), resource limits (`RESOURCE_*`), prohibited features
  (`POLICY_*`), and unsupported coverage (`UNSUPPORTED_*`); they carry a code
  and relevant location/path, and may carry typed evidence.  For example,
  [`H5_CORRUPT_CHUNK_STORED_SIZE`](../registry/findings/catalog/chunk_index.yml)
  locates an invalid HDF5 chunk-index record.

**Evidence**
: Structured support for a conclusion.  In an `h5policy` finding it can include
  the actual and expected values, required comparison, and byte-precise
  locations.  In a case bundle it also includes commands, hashes, build
  identity, outputs, and exit codes.  The
  [case-record schema](../registry/cve-case.yml) shows where HDF5 specimen
  hashes, probe results, and invariant evidence are recorded.

**Decision**
: The final `h5policy` classification: `accept`, `accept_with_warnings`,
  `reject_corrupt`, `reject_policy`, `reject_resource`,
  `unsupported_coverage_gap`, or `internal_error`.  It is distinct from a
  libhdf5 probe outcome; the [`h5policy` guide](../h5policy/README.md#decisions)
  gives HDF5 report examples for these decisions.

**Coverage gap**
: An explicit statement that a requested validation family, canary contract, or
  deeply decoded construct is not covered.  It is a visible result, never a
  passing alias.  For example, an HDF5 expectation without an `h5cve` block
  produces the `coverage_gap` row described in the
  [canary-matrix guide](TOOLS.md#exact-build-canary-matrix).

## Current validation families

**Validation family**
: A named HDF5 format surface whose related invariants, validators, tests, fuzz
  targets, and migration status are tracked as one vertical slice.  For
  example, `chunk_index` groups child-pointer, cycle, record-layout, and stored
  chunk-extent checks in the
  [validation-coverage manifest](../registry/validation-coverage.yml).  The
  manifest is authoritative; the table below lists every current family and the
  exact-build exercise mapped to it by [`h5cve`](../tools/h5cve).

<!-- validation-family-inventory:start -->

| Family | HDF5 surface | Canary exercise |
|---|---|---|
| `object_header_continuation` | Object-header continuation chunks and their reference closure | `message_envelope` |
| `external_file_list` | External File List messages, heap path names, and file segments | `external_file_list` |
| `external_link` | External-link values containing target-file and object paths | `external_link` |
| `virtual_dataset` | Version 4 virtual-layout mappings, source names, and selections | `virtual_dataset` |
| `datatypes` | Encoded datatype recursion, member bounds, and size arithmetic | `datatype` |
| `btree_heap_index` | Generic B-tree, heap, and index traversal structure | `btree` |
| `dataset_layout_filter_fill` | Dataset layout, filter-pipeline, and fill-value messages | `dataset_layout` |
| `cache_image_dependency_graph` | Metadata cache-image envelopes, entries, and dependency graph | `cache_image` |
| `dataspace_dimension` | Dataspace rank, dimensions, maxima, products, and selections | `dataspace` |
| `address_space_bounds` | File addresses, end-of-address bounds, and file-space extents | `address_space` |
| `chunk_index` | Dataset chunk-index pointers, cycles, records, and extents | `chunk_index` |
| `dense_index` | Dense-link indexes, creation-order indexes, and fractal-heap IDs | `dense_index` |
| `heap_structures` | Local, global, and fractal heaps, including attribute storage | `heap_structures` |
| `shared_messages_legacy` | Shared-object-header messages and legacy-format compatibility | `shared_messages_legacy` |
| `message_envelope` | Object-header message versions, flags, lengths, and padding | `message_envelope` |
| `validation_controls` | File-space managers and global validation resource controls | `free_space` |

<!-- validation-family-inventory:end -->

## Measurement and comparison

**Probe**
: A measurement harness that drives a fixture or specimen and records behavior.
  The exact-build `h5policy-probe` compiles against the selected libhdf5 build,
  opens and traverses the file, samples data and attributes, and reports the
  outcome plus OS-observable activation events; see the
  [probe design and report](../h5policy/tools/probe/README.md).

**Exact-build probe**
: The `h5policy-probe` harness, including its C driver, `LD_PRELOAD` tracing
  interposer, sandbox, and build-identity reporting.  It answers what a named
  libhdf5 build actually did; it is not the `h5policy` parser.  Its
  [implementation notes](../h5policy/tools/probe/README.md) show how `h5cc`
  selects the HDF5 build under test.

**Probe outcome**
: The exact-build probe's result: `accepted`, `rejected_at_open`,
  `rejected_in_traversal`, `crashed`, `timeout`, or `build_unavailable`.
  These are deliberately different from `h5policy` decisions; the
  [probe report contract](../h5policy/tools/probe/README.md) records them beside
  the HDF5 entry points that ran.

**Exercise / entry point**
: The selected libhdf5 API path a canary drives after opening a file—for example
  an object walk, dataset read, or a family-specific API.  A fixture rejected
  at `H5Fopen` has not exercised a later family surface.  The
  [probe documentation](../h5policy/tools/probe/README.md) lists the calls made
  by exercises such as `chunk_index` and `free_space`.

**Canary matrix**
: The exact-build table produced by `h5cve matrix` across the corpus
  expectations.  It emits one row for each declared fixture/family contract
  and an explicit `coverage_gap` for an expectation with no contract.  Each
  contracted row selects the family's exercise, runs it against the chosen
  libhdf5 build, records oracle alignment and activation, and classifies the
  result as `verified`, `unexercised`, `violation`, or `coverage_gap`.
  `verified` means the required HDF5 entry points completed for that row; it is
  not a claim that the whole file or library is safe.  For example, the
  [matrix policy](../registry/h5cve-matrix-policy.yml) permits the external-link
  policy fixture's deliberate activation `violation`, while the
  [tool guide](TOOLS.md#exact-build-canary-matrix) defines all four statuses.

**Oracle**
: The authority used for a particular comparison, not one universal program.
  `h5policy` is the repository's policy oracle; differential tools may use the
  selected libhdf5 behavior as an external comparison oracle.  A case record
  must say which oracle and profile produced its result; the
  [case-record schema](../registry/cve-case.yml) keeps those HDF5 measurements
  distinct.

**Oracle alignment**
: A canary requirement that the selected libhdf5 build agrees with `h5policy`
  for the contracted corruption decision.  Resource and policy decisions are
  normally not comparable because they depend on the selected `h5policy`
  profile.  The [matrix policy](../registry/h5cve-matrix-policy.yml), for
  example, documents HDF5 corruption rows that deliberately diverge.

**Baseline build**
: The designated libhdf5 build used as the primary exact-build measurement in a
  case verification.  The generated
  [libhdf5 evidence](../registry/libhdf5-evidence.yml) records the current
  baseline version and build identity.

**Candidate build**
: An optional second libhdf5 build measured alongside the baseline, typically
  to evaluate a proposed fix or behavioral change.  The
  [case-record schema](../registry/cve-case.yml), for example, has separate
  baseline and candidate HDF5 probe results.

**Build identity**
: The portable provenance that identifies a probe build: its role (baseline or
  candidate), version, linked-library soname, `settings_sha256`, build mode,
  sanitizer list, and relevant toolchain information. Local install prefixes
  select the build on a workstation but are not recorded in durable evidence;
  see the identities in
  [`libhdf5-evidence.yml`](../registry/libhdf5-evidence.yml).

**Measured / source-derived / inferred / unmeasured**
: Evidence labels required in CVE case work.  *Measured* comes from a recorded
  run; *source-derived* comes from inspected code; *inferred* follows from
  evidence but was not directly observed; *unmeasured* marks an unavailable or
  unrun observation.  They must not be presented interchangeably; the
  [case-record schema](../registry/cve-case.yml) applies these labels to HDF5
  platform and build claims.

## CVE case workflow

**Case bundle**
: The self-contained, working case record under `cases/<id>/`.  It contains
  `case.yml`, `CASE.md`, `source-audit.md`, reproducers, probe reports, and
  command transcripts needed to support the conclusion.  It is development
  scratch; `h5cve promote` proposes tracked corpus and registry changes.  The
  [CVE strategy](A%20CVE%20strategy%20for%20the%20HDF5%20library.md#11-embedding-the-design-in-the-cve-process)
  defines the required HDF5 evidence in the bundle.

**Case record**
: The machine-readable CVE record based on `registry/cve-case.yml`.  It ties a
  defect to its invariant, oracle finding, validation closure, reproducers,
  remediation status, variants, and provenance; see the
  [machine-readable HDF5 template](../registry/cve-case.yml).

**Triage**
: Classifying the first incorrect security decision by its missing invariant,
  recording every implicated family, and mapping the primary `h5policy` finding
  through the finding registry.  It does not simply name the crash site; for
  example, the [finding registry](../registry/findings/README.md) maps an HDF5
  chunk stored-size finding to `chunk.stored_size` and `chunk_index`.

**Containment**
: The smallest supported-release change that prevents the known crash or unsafe
  behavior.  It can be necessary before the full architectural correction; for
  example, rejecting a filtered HDF5 chunk whose stored size is below filter
  framing contains the fault recorded in the
  [zero-size chunk case](../registry/cases/filtered-chunk-zero-stored-size.yml).

**Systemic closure**
: Enforcement of the missing invariant at the correct semantic boundary,
  together with sibling audit and the direct-test, fuzz-corpus, and coverage
  updates required by the strategy.  It is stronger than containment alone;
  the [zero-size chunk case](../registry/cases/filtered-chunk-zero-stored-size.yml)
  also examines nonzero sizes below filter framing and sibling filter paths.

**Sibling audit**
: A review of related decoder versions, record types, entry points, and
  reference resolvers for the same missing invariant.  For example, the
  [fill-value case](../registry/cases/fill-value-size-unchecked-in-new-decoder.yml)
  compares the old and new HDF5 fill-value message decoders.

**Promotion**
: The explicit boundary where reviewed case artifacts are proposed for tracked
  corpus, expectation, and registry changes.  Developing a case bundle does
  not itself authorize those repository-wide changes.  The
  [CVE workflow](A%20CVE%20strategy%20for%20the%20HDF5%20library.md#11-embedding-the-design-in-the-cve-process)
  shows how an HDF5 direct fixture, expectation, and registry record cross that
  boundary.

## Further reading

- [CVE strategy terminology and architecture](A%20CVE%20strategy%20for%20the%20HDF5%20library.md#terminology)
- [h5policy decisions and profiles](../h5policy/README.md#decisions)
- [Regression-corpus layout](../h5policy/tests/README.md)
- [Exact-build probe](../h5policy/tools/probe/README.md)
- [CVE tools and canary matrix](TOOLS.md)
