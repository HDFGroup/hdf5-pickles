# h5policy Tests

Regression corpus for the `h5policy` oracle.  Every fixture has an expected,
controlled outcome; a change that alters any decision is surfaced for review.

## Layout

- `expected/*.yml` — the tracked specification: one expectation per YAML file
  with its input fixture, profile, expected decision, expected exit code,
  required finding codes, and forbidden outcomes (`crash`, `timeout`,
  `external_open`, `plugin_load`, `write`). A fixture can be reused by several
  expectations. Every report is also checked for schema version 1 and internally
  consistent file geometry, and the `utf-8-percent-v1` path contract;
  `expected_geometry` can pin individual values.
  An optional `h5cve` block declares the fixture's exact-build canary contract:

  ```yaml
  h5cve:
    family: chunk_index              # registry record whose exercise to run
    require_oracle_alignment: true   # a divergence from libhdf5 is a violation
    allowed_statuses: [unexercised, verified]
  ```

  The contract is what `../../tools/h5cve matrix` consumes; a fixture without one
  is reported as a coverage gap rather than inheriting a pass. `allowed_statuses`
  states intent, not observation — a fixture permitted to report `violation`
  carries a comment saying why, and the reason is recorded in
  `../../registry/cases/`.

  **Where a `violation` is declared depends on why it happens.** Two cases, and
  they go in different files:

  - *Normal for the family* — declare it inline. Every external-link fixture
    reports `violation` because the canary's forbidden activations include
    `external_open` and traversing an external link necessarily attempts one.
    That is the family's ordinary signature, so the four `external_link`
    expectations each carry `allowed_statuses: [violation]` directly.
  - *A reasoned exception to a libhdf5 defect on one file* — crash, or
    non-termination — belongs in `fixture_overrides` in
    `../../registry/h5cve-matrix-policy.yml`, with its reason, and the
    expectation must then OMIT `allowed_statuses` entirely. `h5cve matrix` reads
    an expectation's own value in *preference* to the override, so a value left
    here silently shadows the reasoned one — including a value copied from a
    neighbouring fixture.

  `malformed-bad_vds_gheap_free_zero_length.yml` records that correction being
  made once before, and `malformed-attr_gheap_free_undersized.yml` a second time.
  Either way the status is MEASURED first: the probe's own `--forbid` set is
  narrower than the matrix's, so `h5policy-probe --forbid crash` can report no
  violations on a file the matrix scores as one.

  A fixture may name more than one exercised family with `families:` instead of
  `family:`. This is required when one valid file is evidence for more than one
  semantic boundary.

  Fixtures and typed `fuzz_targets.recipes` can also carry a `verification`
  mapping for the §12 assurance categories. The supported keys are
  `count_and_extent_boundaries`, `integer_overflow_and_allocation_budget`,
  `deep_nesting_and_non_progress`, and `reference_semantics_cases`. Each value
  is a list of reviewed category names, for example:

  ```yaml
  verification:
    count_and_extent_boundaries: [zero, n, n_plus_one]
    deep_nesting_and_non_progress: [non_progress]
    reference_semantics_cases: [self_reference, overlap]
  ```

  `h5cve verification` consumes these annotations and lists their source
  fixtures or recipes. Missing required categories remain `partial` or
  `not_assessed`; an annotation never upgrades coverage by itself.
- `unit_datatype.pk` — synthetic checks for the bounded, depth-guarded
  datatype validator (recursion cap and truncation handling), run under poke.
- `unit_messages.pk` — fixed-envelope and dispatch checks for old/new mtime,
  B-tree K override, driver-info, reference-count, LINFO, and AINFO messages.
- `unit_limits.pk` — reduced-limit, in-memory characterization checks for the
  current `H5PolicyProfile` boundaries, complete built-in preset values,
  saturation, finding classes, profile validation, deterministic walk budgets,
  compound rules, feature switches, and run-mode defaults.
- `unit_report_wrapper.sh` — a deterministic hard-timeout simulation that
  validates the shell-generated partial report, its nullable geometry, and its
  byte-path encoding.
- `unit_paths.pk` — byte-level checks for valid and malformed UTF-8, percent
  ambiguity, controls, DEL, and uppercase `%HH` encoding.
- `check_path_encoding.py` — end-to-end strict-UTF-8 JSON and byte round-trip
  checks for arbitrary-byte file and HDF5 object paths.
- `check_cache_image_docs.py` — a focused documentation contract that checks
  the cache-image boundary text and compares it with live reports from all four
  profiles plus an explicit continuation override.
- `check_workflow_docs.py` — ties the operator assessment workflow's profiles
  and decisions to the CLI, and derives its finding, message-routing,
  invariant-family, verification, and exact-build counts from the registries.
- `check_lazy_docs.py` — derives the documented lazy-validation growth ratios
  from the tracked artifact and reproduces its deterministic ladder fields.
- `valid/ malformed/ policy/ resource/ coverage/ integration/ cve/` — generated
  fixtures (git-ignored build output; see below).

## Running

```sh
./run.sh
```

This regenerates the git-ignored fixtures before checking registry ownership, so
the same command works in a fresh clone as well as an existing build tree, and
then runs every gate in one pass:

| gate | asserts |
|---|---|
| corpus generation | every fixture referenced by the tracked expectations is created before consistency checks inspect it |
| registry consistency | the cross-file constraints, including that the manifest's claim about libhdf5 matches what was measured |
| unit checks | datatype, message, file-space-info, profile limits, reachability, consumer API, byte-path serializer, `h5policy_analyze` seam, timeout report |
| byte-path JSON report | arbitrary-byte host and HDF5 paths produce strict UTF-8 JSON and round-trip through `utf-8-percent-v1` |
| corpus cases | every `expected/*.yml`: decision, exit code, required findings, evidence locations, forbidden outcomes |
| differential | h5policy's parse against libhdf5 via h5py / h5dump / h5debug |
| exact-build probe + canary matrix | what the selected libhdf5 build actually does per fixture (skipped without `h5cc`) |
| seam self-check | the in-process seam agrees with the CLI and is order-independent — the gate on batching analyses |
| truncation sweep | a bounded prefix sweep; the exhaustive one is on-demand |
| lazy validation | validation cost tracks metadata, not data volume, with a sensitivity control |
| mutation family | every typed `h5mutate` mutant triggers its intended invariant |

The truncation sweep and lazy-validation ladders are strategy-doc §12
measurements, and the mutation family feeds its fuzz-target requirement; the
seam self-check is not a §12 item but the gate that makes batching analyses
safe. See [`TOOLS.md`](../../docs/TOOLS.md) for running any of them standalone, and
[`registry/verification-coverage.yml`](../../registry/verification-coverage.yml)
for what §12 currently scores.

The suite is also wired into CTest (top-level `CMakeLists.txt`), so
`ctest -R h5policy_regression` runs it from a CMake build. The test is skipped
if `poke` or `python3` + `h5py` are unavailable.

The smaller `cache_image_docs_regression` CTest test runs the cache-image
documentation contract directly. It is also part of the top-level
`docs-check` target, so a profile, decision, analysis-state, or documentation
change at that hard boundary is reviewed as documentation drift.

`h5policy_workflow_docs_regression` checks the operator workflow without
running an HDF5 analysis. It fails when the CLI profiles or decisions, finding
or message inventory, invariant-family status, verification score, or pinned
exact-build evidence changes without a matching documentation update.

`lazy_validation_docs_regression` similarly checks the narrative against
`registry/lazy-validation.json`, reruns the measurement when its optional
dependencies are available, and ignores wall-clock fields while requiring the
physical sizes and deterministic counters to match.

## Two-tier semantic integration cases

The end-to-end corpus tests profile semantics at two complementary levels:

1. **Shipped presets** run unchanged. These cases state the behavior users get
   from the four public profiles. For example, the same valid depth-66 hard-link
   hierarchy is rejected as a strict resource limit and accepted by forensic.
2. **Reduced boundaries** clone a shipped preset, override a small allowlisted
   set of typed leaf fields, and then invoke the ordinary `h5policy_run` entry
   point. This makes large production ceilings practical to exercise with tiny,
   deterministic files while retaining the real parser, walk, accounting,
   finding, and decision paths.

`profile_overrides` is an internal test-harness facility. It does not add
arbitrary profiles or limit switches to the public CLI, which continues to
accept only the four named presets. The harness rejects unknown groups, unknown
fields, non-integer values, and values outside the declared Poke integer type.
An expectation can additionally assert `forbidden_findings`, exact subsets of
`expected_metrics` and `expected_features`, `expected_mapping_mode`, or use
`expected_geometry` and `allow_missing_file` for report-boundary cases. A
compact example is:

```yaml
file: integration/value_sites.h5
profile: untrusted-strict
profile_overrides:
  resources:
    max_single_value_bytes: 2
expected_decision: reject_resource
expected_exit: 4
required_findings: [H5_RESOURCE_SINGLE_VALUE_BYTES]
expected_metrics:
  attribute_count: 1
```

Every structured-evidence location is checked for its role, integer bounds, and
containment in the physical file. `expected_finding_evidence_locations` can
also match role/length and decode the cited fixture bytes as a little-endian
integer, so tests verify the reported range rather than pinning generator-
version-dependent absolute offsets.

`little_endian_value` takes either an integer literal or the string
`from_evidence_actual`. Choose by asking who decides the value:

- A **literal** is right when the generator writes it. The continuation
  self-overlap fixture's `52` is `root_off + 4`, chosen by
  `_make_continuation_overlaps_source`, so pinning it asserts a real decision.
- **`from_evidence_actual`** is right when the bytes come from the h5py-written
  base fixture. `_write` builds those with `libver="latest"` — whatever the
  *linked* libhdf5 calls newest — so their content moves with the writing
  library and no literal stays correct. The sentinel asserts instead that the
  bytes at the location the finding cites decode to the value that same finding
  reports, which is a statement about the oracle's self-consistency and holds
  under any writer.

The same reasoning applies to a location's `length`: pin it when the generator
fixes it, and omit it when it is base-fixture geometry, as the continuation
fixture's `actual_source` extent is. A misspelled sentinel raises rather than
silently passing.

## Who wrote the corpus

Every valid fixture is written by h5py and every malformed and CVE fixture is
byte-patched from one, so the whole corpus inherits whatever the linked libhdf5
emits. Two properties of that writer have already moved underneath it:

- the **format-version bound**, because fixtures ask for `libver="latest"` —
  whatever the *linked* library calls newest. A 2.x-linked h5py writes a
  version-5 layout message where a 1.14-linked one writes version 4.
- whether the **root group's object header carries the 16-byte timestamp
  block**. No libver bound controls this and h5py cannot set `track_times` on
  the root group, so the generator cannot pin it. When it differs, every object
  header runs 16 bytes short and every address after it shifts.

`h5policy-gencorpus` therefore measures both from a file it has just written and
records them in the tracked `CORPUS-WRITER.txt`. `run.sh` diffs that file, and
`cve/`, against `HEAD` after regenerating: a corpus produced by a different
writer then surfaces as a named cause rather than as unexplained byte movement.

```
== tracked-fixture reproducibility ==
  regeneration changed tracked generated file(s):
    h5policy/tests/CORPUS-WRITER.txt
    h5policy/tests/cve/vds_nentries_mult_overflow.h5
  the writer itself differs from the one that produced the committed
  corpus (-committed / +this host):
    -root_ohdr_times            False
    +root_ohdr_times            True
```

The check compares against `HEAD`, not the index, because the committed bytes
are what the next checkout gets — staging a drifted fixture must not silence it.
It is skipped outside a git checkout so a tarball still runs.

The reduced-boundary layer also reuses valid nested datatypes, multi-level
dense-link B-trees, and continuation-heavy object headers to distinguish
resource ceilings from structural corruption. A focused
`integration/multi_filter_dataset.h5` fixture supplies both a four-chunk
fixed-array index and a two-filter shuffle+gzip pipeline: its baseline case is
valid with the normal gzip advisory, while separate overrides reduce only the
chunk or filter count ceiling.

Modern chunk indexes have dedicated deep fixtures as well. A 400-chunk
two-unlimited-dimension dataset forces a raw-data `BTIN` root with `BTLF`
children; paired mutations cover a child checksum, an out-of-file child, and a
checksum-valid cycle, while integration overrides cover depth and exact
metadata-byte saturation. A 300-chunk one-unlimited-dimension dataset reaches
`EAIB`, direct `EADB`s, an `EASB`, and nested `EADB`s, with a child-checksum
mutation proving the walk goes beyond the header and inline records.

Dense links and attributes each have creation-order-indexed fixtures. Their
type-6/type-9 trees have internal roots and child leaves; paired leaf-checksum
mutations prove h5policy follows the secondary graph independently of the name
index, while valid cases exercise heap-ID and creation-order reconciliation.

SOHM has matching end-to-end coverage. A two-dataset repack produces a genuine
`SMLI`, while 51 distinct shared dataspaces force a type-7 `BTIN` root and
`BTLF` children. Repaired mutations cover list and B-tree record locations, a
deep checksum, an out-of-file child, and a cycle; reduced overrides prove the
same tree stops at its depth ceiling and saturates metadata bytes while charging
the first child allocation. Another boundary case pins the SMLI distinction:
its checksum covers one used record while metadata accounting charges all 50
configured record slots. A separate set of 24 oversized shared compound
datatypes forces a depth-one type-1 huge-object tree; its own checksum, child
range, cycle, object-extent, depth, and metadata-ceiling cases cover the heap's
second recursive index, while the accepting base resolves indirect unfiltered
huge bodies. A second accepting fixture shares a one-byte fill value through a
tiny ID, proving that the inline body is dispatched without heap-data access.

Legacy chunk-index cases cover the subtler finite-ceiling boundary directly.
A four-chunk v1 B-tree distinguishes equality from overflow within one leaf;
a generated 130-chunk, multi-level v1 tree proves that an internal-node walk
continues at equality into a later child and stops only after that child proves
an additional chunk exists. Both rejecting cases remain resource decisions and
saturate `chunk_index_refs` at the selected ceiling.

## Differential harness

`../tools/h5policy-diff` cross-checks h5policy's independent parse against
`libhdf5`, catching field-offset bugs that the corpus alone can miss:

- **h5py** is the structural reference — does `libhdf5` open the bytes, and what
  external links, dataset shapes, and `H5Tget_size` values does it report;
- **h5dump** / **h5debug** are independent "does `libhdf5` accept these bytes"
  signals (optional; skipped if not on `PATH`).

It fails if h5policy accepts a file that `libhdf5` structurally rejects, returns
an internal error instead of a safe refusal, calls a structurally valid file
corrupt with no deeper `libhdf5` evidence, disagrees on external references, or
over-counts a dataset's **rank**. A policy, resource, or coverage refusal where
libhdf5 rejects is safe but retained as a classification warning. A
`reject_corrupt` on a file that h5py can structurally traverse is downgraded to
an `A+` warning when a bounded, out-of-process `libhdf5` probe also errors while
inspecting attributes, reading small datasets, or running optional `libhdf5`
tools; those eager catches are security-useful, not hard false positives. The
similarly narrow `A~` warning covers file-global SOHM/free-space metadata that
read-only libhdf5 paths leave unopened, and findings confined to dense
secondary creation-order indexes. Current libhdf5 can enumerate the primary
name index without authenticating every type-6/type-9 block; h5policy
intentionally validates those structures eagerly. Legal 16-byte superblock
length fields are instead h5policy compatibility refusals: libhdf5's shared
length decoder does not support the width, so h5policy stops at preflight.

The logical-**bytes** comparison is warning-level rather than a hard failure:
h5policy now tracks logical dataset bytes separately from raw storage bytes, so
covered datatype cases should match `libhdf5`'s `H5Tget_size` view while layout
and fill checks can still use on-disk storage size. Remaining `WARN C` mismatches
are treated as coverage or semantic-accounting work items, not as corpus
failures. Run standalone with:

```sh
../tools/h5policy-diff --dir .        # or: ../tools/h5policy-diff FILE ...
```

## Structure-aware fuzzing

`../tools/h5policy-fuzz` mutates the valid seeds and cross-checks each mutant
against `libhdf5`, hunting the cases the curated corpus can't enumerate: crashes,
hangs, and — the dangerous direction — files h5policy **accepts** that `libhdf5`
**rejects**.  It is a soak/exploration tool, run on demand (not part of
`run.sh`, which stays fast and deterministic):

```sh
../tools/h5policy-fuzz --iters 500 --seed 20260703 \
    --seeds valid cve            # deterministic; --strategy to restrict
```

Mutators include a **structure-aware** `super` strategy that corrupts a
superblock address field and *repairs the Jenkins checksum* so the mutation
reaches the deep validators (not just the superblock gate), and a `dict`
strategy that splices real HDF5 format tokens (`OHDR`/`FRHP`/`BTHD`/… signatures,
message-type and version bytes) at 8-byte-aligned offsets so a mutant *becomes* a
structure the deep validators recognise.  The `libhdf5` oracle runs **out of
process**, so a `libhdf5` crash on hostile input can't take the fuzzer down; such a
crash is read as the strongest possible "reject".

**Coverage-guided mode** (`--guided`) uses h5policy's own finding codes as a
coverage map: a mutant that reaches a new code is bred back into the seed pool so
mutations compound (a `dict`-placed header that a later `super` mutation points
the root at).  `--coverage-only` skips the oracle to measure reach quickly for
A/B experiments, and `--show-coverage` lists the codes reached.  In practice the
dictionary is the reliable win for breadth of validator paths; guiding helps most
for *depth* (stacking mutations toward deeper structures).

Findings are bucketed by severity — `HANG` / `CRASH` / `FALSE_ACCEPT` are hard
(non-zero exit); `ACCEPT_VS_CRASH` (h5policy accepts a file that *crashes*
`libhdf5` — an unreliable oracle, usually a `libhdf5` memory bug) and `FALSE_REJECT`
(over-strict, the safe direction) are advisory.  Mutants land in the git-ignored
`fuzz-findings/`.  A found soundness gap is **promoted** into a curated
`malformed/` fixture (via a `gencorpus` generator + `expected/*.yml`) so it
becomes a permanent regression guard — `bad_base_address`, `eof_past_metadata`,
`bad_snod_cache_type` and `bad_heap_segment` came from this loop.

## Fixtures

The `*.h5` files are **generated**, not committed, by
`../tools/h5policy-gencorpus` (requires `h5py`).  Regenerate them with:

```sh
../tools/h5policy-gencorpus .
```

Valid fixtures are written with `libver=latest`; malformed fixtures are
byte-patched from a valid base so we make no assumption about `libhdf5` accepting
them. `integration/` holds compact valid inputs designed for full-walk profile
semantics, and `cve/` is reserved for minimized CVE seeds.
