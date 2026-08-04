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
  is understood or reduced into a fixture.

**PoC / integration PoC**
: The full-file, public-API reproducer of a reported behavior.  In a CVE case
  it is kept separately from the smaller direct fixture, because it proves the
  user-visible integration path rather than only one invariant.

**Direct fixture**
: The smallest practical raw-record, aggregate-object, or reference-graph
  fixture that proves a particular invariant is enforced.  It is the focused
  companion to an integration PoC.

**Reproducer**
: An input plus the command or program needed to demonstrate behavior.  The CVE
  process preserves both an integration PoC and a direct fixture when they are
  applicable.

**Corpus**
: The organized collection of regression inputs and their expectation files,
  primarily under `h5policy/tests/`.  It is not merely a bag of files: the
  expected decision, findings, profile, and forbidden outcomes are part of the
  contract.

**Expectation**
: A YAML test specification in `h5policy/tests/expected/` that associates a
  fixture with a profile and asserts its decision, exit status, findings, and
  other report properties.  One fixture may have more than one expectation.

**Canary**
: An exact-build exercise for one registry family, run against a fixture with
  an explicit `h5cve` contract.  A valid canary shows that the exercise can
  complete; a malformed open-successfully fixture is also required to show the
  exercise can reach the defective family surface.

**Canary contract**
: The `h5cve` block in an expectation.  It names the validation family, whether
  oracle alignment is required, and which matrix statuses are permitted.  An
  absent contract is reported as a coverage gap rather than silently passing.

**Variant / semantic neighbor**
: A related input formed by changing one typed semantic condition, usually to
  test boundary cases and siblings of an invariant.  `h5mutate` records the
  parent hash, intended invariant/finding, changed ranges, and checksum reseals
  for its variants.

**Fuzz seed**
: An input retained for a fuzz target so mutations start near a meaningful
  format boundary or known defect.

## Analysis, validation, and policy

**Raw record**
: An inert representation of encoded fields and references.  It contains no
  initialized native HDF5 objects, cache entries, plugins, or external-file
  handles.

**Child reference**
: A typed, inert description of another encoded region or resource, such as an
  address and extent.  Decoding it does not follow, load, or open its target.

**Raw decode / bounded raw decode**
: Reading encoded fields from an explicit, bounded byte extent while checking
  availability, arithmetic, sizes, and progress.  It produces inert raw
  records; it does not itself establish cross-record semantics or construct
  native HDF5 state.

**Validation closure**
: The set of raw records that must be inspected to establish the semantics
  needed for an operation.  It is normally smaller than the whole file.

**Invariant**
: A format, arithmetic, range, progress, graph, or policy condition that must
  hold for safe handling.  CVE triage is organized around the *missing
  invariant*, rather than the eventual crash location or a generic error code.

**Semantic boundary**
: The smallest complete set of records, relationships, and entry points where
  an invariant can be established correctly.  It can be larger than one encoded
  record.

**Validated record / validation certificate**
: The conceptual opaque value returned after the local and contextual checks
  for a raw record have passed.  Only such validated descriptions may be
  materialized in the design described by the CVE strategy.

**Materialization**
: Construction of native HDF5 structures from validated descriptions.  It is
  separate from raw decoding and validation so malformed bytes cannot directly
  create native state.

**Activation**
: An operation with side effects or externally consequential work, including
  cache publication, ID registration, index initialization, plugin loading,
  decompression, callbacks, or external-file access.  Validation must precede
  any activation that depends on untrusted content.

**Activation event**
: An activation that the exact-build probe can observe at the OS boundary,
  currently including file opens, `dlopen`, writes, and network operations.
  Internal events such as cache insertion are outside that probe's visibility.

**Profile**
: A named policy preset that combines budgets, feature permissions,
  compatibility behavior, and analysis depth.  The shipped presets are
  `legacy`, `trusted-fast`, `untrusted-strict`, and `forensic`; all retain hard
  safety invariants.

**Forensic profile**
: The profile intended for bounded investigation: it continues reporting where
  configured, never follows references, and does not materialize or activate
  untrusted content.

**Finding**
: A stable, located report of a detected condition.  Findings distinguish
  corruption (`CORRUPT_*`), resource limits (`RESOURCE_*`), prohibited features
  (`POLICY_*`), and unsupported coverage (`UNSUPPORTED_*`); they carry a code
  and relevant location/path, and may carry typed evidence.

**Evidence**
: Structured support for a conclusion.  In an `h5policy` finding it can include
  the actual and expected values, required comparison, and byte-precise
  locations.  In a case bundle it also includes commands, hashes, build
  identity, outputs, and exit codes.

**Decision**
: The final `h5policy` classification: `accept`, `accept_with_warnings`,
  `reject_corrupt`, `reject_policy`, `reject_resource`,
  `unsupported_coverage_gap`, or `internal_error`.  It is distinct from a
  libhdf5 probe outcome.

**Coverage gap**
: An explicit statement that a requested validation family, canary contract, or
  deeply decoded construct is not covered.  It is a visible result, never a
  passing alias.

## Measurement and comparison

**Probe**
: A measurement harness that drives a fixture or specimen and records behavior.
  The exact-build `h5policy-probe` compiles against the selected libhdf5 build,
  opens and traverses the file, samples data and attributes, and reports the
  outcome plus OS-observable activation events.

**Exact-build probe**
: The `h5policy-probe` harness, including its C driver, `LD_PRELOAD` tracing
  interposer, sandbox, and build-identity reporting.  It answers what a named
  libhdf5 build actually did; it is not the `h5policy` parser.

**Probe outcome**
: The exact-build probe's result: `accepted`, `rejected_at_open`,
  `rejected_in_traversal`, `crashed`, `timeout`, or `build_unavailable`.
  These are deliberately different from `h5policy` decisions.

**Exercise / entry point**
: The selected libhdf5 API path a canary drives after opening a file—for example
  an object walk, dataset read, or a family-specific API.  A fixture rejected
  at `H5Fopen` has not exercised a later family surface.

**Oracle**
: The authority used for a particular comparison, not one universal program.
  `h5policy` is the repository's policy oracle; differential tools may use the
  selected libhdf5 behavior as an external comparison oracle.  A case record
  must say which oracle and profile produced its result.

**Oracle alignment**
: A canary requirement that the selected libhdf5 build agrees with `h5policy`
  for the contracted corruption decision.  Resource and policy decisions are
  normally not comparable because they depend on the selected `h5policy`
  profile.

**Baseline build**
: The designated libhdf5 build used as the primary exact-build measurement in a
  case verification.

**Candidate build**
: An optional second libhdf5 build measured alongside the baseline, typically
  to evaluate a proposed fix or behavioral change.

**Build identity**
: The provenance that makes a probe result reproducible: the selected build's
  version, linked library path, configuration, and `libhdf5.settings` hash, as
  well as relevant toolchain information.

**Measured / source-derived / inferred / unmeasured**
: Evidence labels required in CVE case work.  *Measured* comes from a recorded
  run; *source-derived* comes from inspected code; *inferred* follows from
  evidence but was not directly observed; *unmeasured* marks an unavailable or
  unrun observation.  They must not be presented interchangeably.

## CVE case workflow

**Case bundle**
: The self-contained, working case record under `cases/<id>/`.  It contains
  `case.yml`, `CASE.md`, `source-audit.md`, reproducers, probe reports, and
  command transcripts needed to support the conclusion.  It is development
  scratch; `h5cve promote` proposes tracked corpus and registry changes.

**Case record**
: The machine-readable CVE record based on `registry/cve-case.yml`.  It ties a
  defect to its invariant, oracle finding, validation closure, reproducers,
  remediation status, variants, and provenance.

**Triage**
: Classifying the first incorrect security decision by its missing invariant,
  recording every implicated family, and mapping the primary `h5policy` finding
  through the finding registry.  It does not simply name the crash site.

**Containment**
: The smallest supported-release change that prevents the known crash or unsafe
  behavior.  It can be necessary before the full architectural correction.

**Systemic closure**
: Enforcement of the missing invariant at the correct semantic boundary,
  together with sibling audit and the direct-test, fuzz-corpus, and coverage
  updates required by the strategy.  It is stronger than containment alone.

**Sibling audit**
: A review of related decoder versions, record types, entry points, and
  reference resolvers for the same missing invariant.

**Promotion**
: The explicit boundary where reviewed case artifacts are proposed for tracked
  corpus, expectation, and registry changes.  Developing a case bundle does
  not itself authorize those repository-wide changes.

## Further reading

- [CVE strategy terminology and architecture](A%20CVE%20strategy%20for%20the%20HDF5%20library.md#terminology)
- [h5policy decisions and profiles](../h5policy/README.md#decisions)
- [Regression-corpus layout](../h5policy/tests/README.md)
- [Exact-build probe](../h5policy/tools/probe/README.md)
- [CVE tools and canary matrix](TOOLS.md)
