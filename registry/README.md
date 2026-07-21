# Invariant registry

Data-only, machine-readable description of the invariants the `h5policy` oracle
enforces, the findings it emits, and how well each record family is covered. It
is the bridge described in [*A CVE strategy for the HDF5 library*](../docs/A%20CVE%20strategy%20for%20the%20HDF5%20library.md)
between `h5policy` as an independent semantic oracle and any native
implementation: a native library can consume these invariant ids and boundaries
without importing GPLv3 pickle source into a differently-licensed build.

Four files plus a case directory, one schema version:

| File | Answers |
|---|---|
| [`findings.yml`](findings.yml) | For each stable finding code: what invariant does it prove, at which validation scope, for which record and versions, and — when the code is emitted by more than one walker — which role applies to a given occurrence. |
| [`validation-coverage.yml`](validation-coverage.yml) | For each record family: which invariants exist (per [§5](../docs/A%20CVE%20strategy%20for%20the%20HDF5%20library.md) and §11.5), which finding each maps to, where the oracle enforces it, which tests and fuzz targets cover it, and its migration status. |
| [`h5cve-matrix-policy.yml`](h5cve-matrix-policy.yml) | Which exact-build canary statuses each fixture is permitted to report. `coverage_gap` and `unexercised` are visible outcomes, never aliases for success. |
| [`cve-case.yml`](cve-case.yml) | The annotated **template** for a per-case record. Its fields are the §11.5 containment/systemic tracking block. |
| [`cases/`](cases/) | Real per-case records: one proactive hardening case and four libhdf5 divergence records, including one open backlog of uninvestigated items. |

[`../tools/check_registry.py`](../tools/check_registry.py) enforces the
cross-file constraints: every invariant referenced by a finding or a context
rule exists in its record, every expectation points at a catalogued finding and
an existing fixture, every generated fixture is owned by an expectation, and no
finding code is defined twice (a duplicate key is silently dropped by YAML, so
a whole definition can otherwise go dead unnoticed).

## Vocabulary (from the strategy doc)

`scope` — where the invariant is checked (§3, §11.2):
`local_decode`, `record_local`, `aggregate_object`, `reference_graph`,
`resource`, `policy`. Triage classifies the **first** incorrect security
decision, not the eventual crash site.

`severity` — the `h5policy` finding class as emitted by `h5policy_emit_error`:
`corrupt`, `resource`, `policy`, `warning`.

`ambiguous` / `contexts` — twenty codes are emitted by more than one walker: a
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
| catalogued finding codes | 117 across 16 record families |
| codes emitted by more than one walker | 20, carrying 38 `contexts` rules |
| expectations with an `h5cve` contract | 127 of 178 |
| families with an exact-build canary | 15 of 16 |

`validation_controls` is the family without a canary, by design: it covers
budgets, base address, free-space managers and profile validity, which have no
single traversal surface to exercise. Its fixtures state `coverage_gap` in
`allowed_statuses` rather than claiming a canary ran.

The 51 uncontracted expectations are fixtures the oracle **accepts**. A family
cannot be derived mechanically for those: the only findings present are
incidental advisories (a deflate-filter notice, say) that describe a property of
the file rather than what the fixture exercises, so assigning a family from one
points the canary at the wrong structure. They need hand-assignment.

`h5policy` remains the oracle and enforces its invariants independently.
libhdf5 enforcement is a **separate** claim, proven per §11.5 by the exact-build
probe and never assumed from `h5policy` accepting or rejecting — see
[`h5cve-matrix-policy.yml`](h5cve-matrix-policy.yml) for the divergences
currently known and allowed.

`check_registry.py` is not yet wired into `run.sh`; run it manually.
