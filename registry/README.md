# Invariant registry

Data-only, machine-readable description of the invariants the `h5policy` oracle
enforces, the findings it emits, and how well each record family is covered. It
is the bridge described in [*A CVE strategy for the HDF5 library*](../docs/A%20CVE%20strategy%20for%20the%20HDF5%20library.md)
between `h5policy` as an independent semantic oracle and any native
implementation: a native library can consume these invariant ids and boundaries
without importing GPLv3 pickle source into a differently-licensed build.

Registry files plus a case directory, one schema version:

| File | Answers |
|---|---|
| [`findings.yml`](findings.yml) | For each reviewed stable finding code: what invariant does it prove, at which validation scope, for which record and versions, and — when the code is emitted by more than one walker — which role applies to a given occurrence. |
| [`finding-backlog.yml`](finding-backlog.yml) | Exact source inventory for future emitted codes whose semantic record/invariant mapping is still pending. It is currently empty; an entry here is visible migration debt, not a catalog mapping. |
| [`validation-coverage.yml`](validation-coverage.yml) | For each record family: which invariants exist (per [§5](../docs/A%20CVE%20strategy%20for%20the%20HDF5%20library.md) and §11.5), which finding each maps to, where the oracle enforces it, which tests and fuzz targets cover it, and its migration status. |
| [`h5cve-matrix-policy.yml`](h5cve-matrix-policy.yml) | Which exact-build canary statuses each fixture is permitted to report. `coverage_gap` and `unexercised` are visible outcomes, never aliases for success. |
| [`message-routing.yml`](message-routing.yml) | Measured inventory of finding **messages** that resolve to no record family. A shared code's family comes from its message via `contexts`, and for an `ambiguous` code a message matching no rule names no family at all. Regenerate with `python3 tools/message_routing.py --write`; `check_registry.py` fails on drift either way. |
| [`libhdf5-evidence.yml`](libhdf5-evidence.yml) | **Generated.** What the selected libhdf5 build actually did, per record family, measured by the canary matrix. |
| [`lazy-validation.json`](lazy-validation.json) | **Generated.** Measurement that validation cost tracks metadata rather than data volume, with a sensitivity control. |
| [`truncation-sweep.json`](truncation-sweep.json) | **Generated.** Result of the §12 truncation sweep: every prefix of each seed, and whether coverage was exhaustive or sampled. |
| [`verification-coverage.yml`](verification-coverage.yml) | **Generated.** Which of the [§12](../docs/A%20CVE%20strategy%20for%20the%20HDF5%20library.md) verification requirements each record family demonstrably meets. |
| [`cve-case.yml`](cve-case.yml) | The annotated **template** for a per-case record. Its fields are the §11.5 containment/systemic tracking block. |
| [`cases/`](cases/) | Real per-case records: one proactive hardening case and four libhdf5 divergence records, including one open backlog of uninvestigated items. |

[`../tools/check_registry.py`](../tools/check_registry.py) derives the production
emit inventory from the pickle validators and the wrapper-generated timeout
report. It requires every emitted code to appear in exactly one of the semantic
catalog or the explicit backlog, validates source attribution, and rejects
untracked or stale codes. It also enforces the cross-file constraints: every
invariant referenced by a finding or a context rule exists in its record, every
required fixture finding is catalogued, every generated fixture is owned by an
expectation, and no finding code is defined twice (a duplicate key is silently
dropped by YAML, so a whole definition can otherwise go dead unnoticed).

## Vocabulary (from the strategy doc)

`scope` — where the invariant is checked (§3, §11.2):
`local_decode`, `record_local`, `aggregate_object`, `reference_graph`,
`resource`, `policy`. Triage classifies the **first** incorrect security
decision, not the eventual crash site.

`severity` — the `h5policy` finding class as emitted by `h5policy_emit_error`:
`corrupt`, `resource`, `policy`, `warning`.

`ambiguous` / `contexts` — twenty-six codes are emitted by more than one walker: a
checksum mismatch or an out-of-file address means a different thing in a chunk
index than in an object header. Those entries are marked `ambiguous: true`,
which says their top-level `record`/`invariant` name only **one** of the code's
roles and are a fallback, not an attribution.

The only per-occurrence discriminator `h5policy` reports is the finding
**message**, which is composed at the emission site, so `contexts` is an ordered
list of substring rules matched against it (first match wins):

```yaml
contexts:
  - match: "v2 B-tree chunk child address outside file"
    record: chunk_index
    invariant: chunk.child_address   # omit when none is catalogued yet
    evidence: curated
```

`evidence` records where a rule came from: `curated` from a fixture's own
`h5cve.family` block, `fixture` from the structure the corpus fixture that
produces the message actually corrupts. Neither is inferred from the message
text alone. A rule may name a `record` without an `invariant`: that still
selects the right exact-build canary, and the missing invariant is a visible
entry on the backlog rather than a wrong one asserted silently.

When an ambiguous code's message matches no rule, `h5cve triage` asserts
**nothing** and reports the candidate records instead. An unnamed invariant is a
gap; a wrong one is a wrong fix. Adding the missing rule is the fix.

`migration_status` — `h5policy` is the oracle and enforces its invariants
independently; libhdf5 enforcement is a **separate** claim that must be proven
per §11.5, never assumed from `h5policy` accepting or rejecting.

## Current coverage

| | |
|---|---|
| production finding codes | 263, all source-tracked |
| catalogued finding codes | 263 across 16 record families |
| explicit catalog backlog | 0 |
| catalogued ambiguous codes | 26, carrying 49 `contexts` rules |
| expectations with an `h5cve` contract | 128 of 180 |
| families with an exact-build canary | 15 of 16 |

`validation_controls` is the family without a canary, by design: it covers
budgets, base address, free-space managers and profile validity, which have no
single traversal surface to exercise. Its fixtures state `coverage_gap` in
`allowed_statuses` rather than claiming a canary ran.

Of the 52 uncontracted expectations, 51 are fixtures the oracle **accepts**. A
family cannot be derived mechanically for those: the only findings present are
incidental advisories (a deflate-filter notice, say) that describe a property of
the file rather than what the fixture exercises, so assigning a family from one
points the canary at the wrong structure. They need hand-assignment. The other
is the focused forensic cache-image regression, which shares the existing
cache-image fixture and canary rather than duplicating its exact-build row.

## Claimed vs measured libhdf5 behaviour

`h5policy` is the oracle and enforces its invariants independently. libhdf5
enforcement is a **separate** claim, never assumed from `h5policy` accepting or
rejecting. Two artifacts keep that claim honest:

- `validation-coverage.yml`'s `validators.hdf5` is the hand-maintained **claim**.
- `libhdf5-evidence.yml` is the **measurement**, regenerated by
  `tools/h5cve evidence` from the canary matrix (about 8 seconds).

`check_registry.py` fails on any disagreement between them, so a verdict cannot
drift from what was observed — either the build changed and the evidence needs
regenerating, or someone asserted something nothing measured. They are separate
files on purpose: a generator that rewrites the claim it is checked against
proves nothing.

Current verdicts, against libhdf5 2.2.0:

| verdict | families |
|---|---|
| `enforced` | 10 |
| `partial` — some invariants enforced, some not | 5 |
| `unmeasured` — no canary (`validation_controls`) | 1 |

Only `reject_corrupt` specimens count toward a verdict. Activation events
(`external_open`) and crashes are recorded separately, since a build can enforce
an invariant and still crash or activate on the way to it — `chunk_index` and
`virtual_dataset` are both `enforced` and both have a fixture that crashes the
build. The divergences behind the five `partial` verdicts are written up in
[`cases/`](cases/).

## §12 verification status

[`verification-coverage.yml`](verification-coverage.yml), regenerated by
`tools/h5cve verification`, scores each family against the eleven §12
requirements. Statuses are four-valued and `not_assessed` is **not** a soft
`met`:

| status | meaning |
|---|---|
| `met` | mechanically demonstrated, evidence listed |
| `partial` | demonstrated for some of the requirement, not all |
| `absent` | mechanically demonstrated to be missing |
| `not_assessed` | not determinable from artifacts; needs classification |

**50 of 176 requirement-slots are currently `met`.** The distribution matters
more than the total:

- OSS-Fuzz integration is the only requirement still `absent` for every family.
- Lazy validation is `partial` everywhere: measured, and holding, but on the
  oracle as a whole rather than family by family.
- Three are `not_assessed` for every family — boundary counts, integer overflow
  versus allocation budget, and deep nesting versus non-progress. These are
  deliberately **not** inferred from finding-code spelling; settling them needs
  fixtures classified by the case they represent.
- Dedicated fuzz targets exist for 1 family of 16.
- 12 families pin evidence locations as well as finding codes; the remaining
  4 need cursor arithmetic at the emit site rather than test metadata.
- Truncation is `met` for 11 families and `partial` for 3 whose seed exceeds
  the sweep budget; see [`truncation-sweep.json`](truncation-sweep.json).
- The strongest column is no-activation-on-failure, `met` for 12 families,
  because the exact-build probe measures it directly.

`check_registry.py` enforces the report's structure — every manifest record
present, every requirement scored — but not its content. Gating on content would
be permanently red and therefore ignored; the file is a distance measure.
