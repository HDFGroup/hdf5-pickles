# Invariant registry

Data-only, machine-readable description of the invariants the `h5policy` oracle
enforces, the findings it emits, and how well each record family is covered. It
is the bridge described in [*A CVE strategy for the HDF5 library*](../docs/A%20CVE%20strategy%20for%20the%20HDF5%20library.md)
between `h5policy` as an independent semantic oracle and any native
implementation: a native library can consume these invariant ids and boundaries
without importing GPLv3 pickle source into a differently-licensed build.

Three files, one schema version:

| File | Answers |
|---|---|
| [`findings.yml`](findings.yml) | For each stable finding code: what invariant does it prove, at which validation scope, for which record and versions, and is the code shared across record families? |
| [`validation-coverage.yml`](validation-coverage.yml) | For each record family: which invariants exist (per [§5](../docs/A%20CVE%20strategy%20for%20the%20HDF5%20library.md) and §11.5), which finding each maps to, where the oracle enforces it, which tests and fuzz targets cover it, and its migration status. |
| [`cve-case.yml`](cve-case.yml) | The annotated **template** for a per-case record. Its fields are the §11.5 containment/systemic tracking block. Real cases live under [`cases/`](cases/). |

## Vocabulary (from the strategy doc)

`scope` — where the invariant is checked (§3, §11.2):
`local_decode`, `record_local`, `aggregate_object`, `reference_graph`,
`resource`, `policy`. Triage classifies the **first** incorrect security
decision, not the eventual crash site.

`severity` — the `h5policy` finding class as emitted by `h5policy_emit_error`:
`corrupt`, `resource`, `policy`, `warning`.

`migration_status` — `h5policy` is the oracle and enforces its invariants
independently; libhdf5 enforcement is a **separate** claim that must be proven
per §11.5, never assumed from `h5policy` accepting or rejecting.

## Scope of this checkpoint

This is the "schema + one real slice" cut. The three schemas are fully defined
and populated end-to-end for exactly one record family — `object_header_continuation`,
the family reworked to the interval model (strategy §5) — plus its case under
`cases/`. Bulk migration of every finding code and record family, and any
generator or linter that **consumes** these files (roadmap changes #5 and #6),
is deliberately out of scope here; the files are declarative for now. Values are
verified against the pickles and tests at authoring time, not enforced by CI
yet — treat a drift between registry and code as a registry bug until that
wiring exists.
