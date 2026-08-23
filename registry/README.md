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
| [`findings/`](findings/) | Authoritative finding registry: static catalog shards by record family plus grouped message-route shards for ambiguous codes. See its [maintenance guide](findings/README.md). |
| [`finding-backlog.yml`](finding-backlog.yml) | Exact source inventory for future emitted codes whose semantic record/invariant mapping is still pending. It is currently empty; an entry here is visible migration debt, not a catalog mapping. |
| [`validation-coverage.yml`](validation-coverage.yml) | For each record family: which invariants exist (per [§5](../docs/A%20CVE%20strategy%20for%20the%20HDF5%20library.md) and §11.5), which finding each maps to, where the oracle enforces it, which tests and fuzz targets cover it, and its migration status. |
| [`h5cve-matrix-policy.yml`](h5cve-matrix-policy.yml) | Which exact-build canary statuses each fixture is permitted to report. `coverage_gap` and `unexercised` are visible outcomes, never aliases for success. |
| [`message-routing.yml`](message-routing.yml) | Measured inventory of finding **messages** that resolve to no record family. A shared code's family comes from its grouped route rules, and for an `ambiguous` code a message matching no rule names no family at all. Regenerate with `python3 tools/message_routing.py --write`; `check_registry.py` fails on drift either way. |
| [`libhdf5-evidence.yml`](libhdf5-evidence.yml) | **Generated.** What the selected libhdf5 build actually did, per record family, measured by the canary matrix. |
| [`lazy-validation.json`](lazy-validation.json) | **Generated.** Measurement that validation cost tracks metadata rather than data volume, with physical-file endpoints, a sensitivity control, and the explicit latest-format/timestamps-disabled fixture policy. |
| [`truncation-sweep.json`](truncation-sweep.json) | **Generated.** Result of the §12 truncation sweep: every prefix of each seed, and whether coverage was exhaustive or sampled. |
| [`verification-coverage.yml`](verification-coverage.yml) | **Generated.** Which of the [§12](../docs/A%20CVE%20strategy%20for%20the%20HDF5%20library.md) verification requirements each record family demonstrably meets. |
| [`ssp-control-evidence.yml`](ssp-control-evidence.yml) | Checked, deliberately narrow mapping from selected HDF5 SSP controls to record/invariant/finding, fixture, canary, and exact-build measurement. It is technical evidence, not complete control attestation. |
| [`cve-case.yml`](cve-case.yml) | The annotated **template** for a per-case record. Its fields are the §11.5 containment/systemic tracking block. |
| [`cases/`](cases/) | Real per-case records: two oracle-hardened memory-safety cases, one proactive hardening case, and six libhdf5 divergence records, including one open backlog of uninvestigated items. |

[`../tools/check_registry.py`](../tools/check_registry.py) derives the production
emit inventory from the pickle validators and the wrapper-generated timeout
report. It requires every emitted code to appear in exactly one of the semantic
catalog or the explicit backlog, validates source attribution, and rejects
untracked or stale codes. It also enforces the cross-file constraints: every
invariant referenced by a finding or route rule exists in its record, every
required fixture finding is catalogued, every generated fixture is owned by an
expectation, and no YAML key or finding code is defined twice.

## Vocabulary (from the strategy doc)

`scope` — where the invariant is checked (§3, §11.2):
`local_decode`, `record_local`, `aggregate_object`, `reference_graph`,
`resource`, `policy`. Triage classifies the **first** incorrect security
decision, not the eventual crash site.

`severity` — the `h5policy` finding class as emitted by `h5policy_emit_error`:
`corrupt`, `resource`, `policy`, `warning`.

`ambiguous` / routes — some codes are emitted by more than one walker: a
checksum mismatch or an out-of-file address means a different thing in a chunk
index than in an object header. Those entries are marked `ambiguous: true`,
which says their top-level `record`/`invariant` name only **one** of the code's
roles and are a fallback, not an attribution.

The only per-occurrence discriminator `h5policy` reports is the finding
**message**, which is composed at the emission site. Reviewed routing for an
ambiguous code lives in a route shard that groups messages resolving to the
same role:

```yaml
routes:
  - record: chunk_index
    invariant: chunk.child_address
    scope: reference_graph
    evidence: curated
    matches:
      - "v2 B-tree chunk child address outside file"
```

The loader expands these groups and applies longest-substring-first precedence,
so a broad match cannot shadow a more specific one.

`evidence` records where a rule came from: `curated` from a fixture's own
`h5cve.family` block, `fixture` from the structure the corpus fixture that
produces the message actually corrupts. Neither is inferred from the message
text alone. A rule may name a `record` without an `invariant`: that still
selects the right exact-build canary, and the missing invariant is a visible
entry on the backlog rather than a wrong one asserted silently.

When an ambiguous code's message matches no route, `h5cve triage` asserts
**nothing** and reports the candidate records instead. An unnamed invariant is a
gap; a wrong one is a wrong fix. Adding the missing rule is the fix.

`migration_status` — `h5policy` is the oracle and enforces its invariants
independently; libhdf5 enforcement is a **separate** claim that must be proven
per §11.5, never assumed from `h5policy` accepting or rejecting.

## Current coverage

Finding and routing counts are derived rather than copied into this document:

```sh
python3 tools/finding_registry.py stats
```

The exact-build canary inventory covers every record family. Its count is
derived and checked by `tools/check_quickstart.py`; see the
[tool guide](../docs/TOOLS.md#exact-build-canary-matrix) for the current,
machine-checked inventory and its malformed-fixture contract.

Not every expectation needs its own canary contract. Alternate-profile checks,
reduced-limit integrations, and multiple expectations over one fixture can
reuse the family exercise already named by a contracted valid/malformed pair.
An uncontracted expectation never inherits a passing matrix result: the
family-level inventory is derived from the explicit contracts and fails if a
record family lacks its required canaries.

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

Current verdicts, against libhdf5 2.3.0:

| verdict | families |
|---|---|
| `enforced` | 7 |
| `partial` — some invariants enforced, some not | 9 |

Only `reject_corrupt` specimens count toward a verdict. Activation events
(`external_open`), crashes and hangs are recorded separately, since a build can
enforce an invariant and still crash, hang or activate on the way to it.
`crashes_on` is a fault — SIGSEGV, SIGFPE, SIGABRT — and `hangs_on` a
non-termination the probe killed on its CPU limit; the probe spells both as a
forbidden `crash` event, so the bucket comes from its `outcome` rather than from
that name. The divergences behind the nine `partial` verdicts are written up in
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

**56 of 176 requirement-slots are currently `met`.** The distribution matters
more than the total:

- OSS-Fuzz integration is the only requirement still `absent` for every family.
- Lazy validation is `partial` everywhere: measured, and holding, but on the
  oracle as a whole rather than family by family.
- Reviewed fixture/recipe annotations now carry most of the boundary,
  arithmetic, nesting and reference-semantics evidence: `not_assessed` in those
  four columns is down to 2, 9, 9 and 6 families respectively. The annotations
  are a review of what each fixture's documented mechanism actually exercises,
  never an inference from finding-code spelling, which is why a family with many
  fixtures can still be `not_assessed` -- version, flag and checksum fixtures
  exercise none of these categories. What the sweep establishes is mostly which
  boundary VALUES the corpus lacks: `n` and `n_minus_1` are thin nearly
  everywhere, and `allocation_budget` is demonstrated for one family.
- Dedicated fuzz targets exist for 1 family of 16.
- 14 families pin evidence locations as well as finding codes; the remaining
  2 need cursor arithmetic at the emit site rather than test metadata.
- Truncation is `met` for 12 families, `partial` for 4 whose seed exceeds the
  sweep budget, and `absent` for 0; see
  [`truncation-sweep.json`](truncation-sweep.json).
- No-activation-on-failure is `met` for 10 families and `partial` for 6 because
  the exact-build probe observes an activation or crash in those families.

`check_registry.py` enforces the report's structure — every manifest record
present and every requirement scored — and derives the summary counts above.
It does not require any particular grade. Gating on the grades would be
permanently red and therefore ignored; the file is a distance measure.
