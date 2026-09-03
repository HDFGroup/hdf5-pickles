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
| [`cases/`](cases/) | Real per-case records, mostly `oracle-hardened` -- h5policy rejects, the libhdf5 side is unfixed -- alongside contained, upstream-fixed and proactive-hardening entries. Two are `uninvestigated`: filed divergences held as a tracked queue rather than waved through as benign. The enumeration is deliberately not spelled out here, because it drifts; `check_registry.py` counts them. |

[`../tools/check_registry.py`](../tools/check_registry.py) derives the production
emit inventory from the pickle validators and the wrapper-generated timeout
report. It requires every emitted code to appear in exactly one of the semantic
catalog or the explicit backlog, validates source attribution, and rejects
untracked or stale codes. It also enforces the cross-file constraints: every
invariant referenced by a finding or route rule exists in its record, every
required fixture finding is catalogued, every generated fixture is owned by an
expectation, and no YAML key or finding code is defined twice.

It also gates **stale citations of retired case-record fields**. When a record
renames one of its own fields, every citation of the old name elsewhere is left
dangling — and worse, may keep asserting whatever the rename retracted. That has
happened: `registry_reading_note` was renamed from an earlier heading in two
records, and three files went on citing the dead name. So the deny-list is
*derived from git history* rather than declared: every top-level field name a
record has ever carried, minus the names any record carries now, is a dead name,
and a dead name may appear only in a record that once had it — which is where the
retraction narrative belongs. Nothing has to be remembered at rename time. A dead
name too generic to word-match safely is skipped and reported by name, so the gap
is visible; outside a git checkout the whole rule reports that it is unchecked.

A separate checker, `tools/check_source_citations.py`, gates the other kind of
citation that rots silently: **a line number into one of our own pickles**. A
renamed field leaves a name to compare against, so history can catch it; a line
number leaves nothing, and stays syntactically valid while the code moves under
it. Measured when that checker was written, **all six** such citations in the
tracked tree were stale — two by more than five hundred lines, two landing on
unrelated code.

So the citation has to say what it points at, and the checker holds it to that:

```
h5_datatype.pk:1180 (member_off > elm_size)
h5_walk.pk:820 (H5_CORRUPT_SUPERBLOCK_EXTENSION_ALIAS)
h5_group.pk:194-262 (h5policy_local_heap_data_addr, data_seg_addr)
```

Every substantial token in the parenthesised anchor must appear at the cited line
(±3 lines, or anywhere inside a declared range). Prose may wrap between the
citation and its anchor, including after a `#` comment marker, but nothing else
may come between them — so a citation with no anchor cannot quietly adopt the
next parenthetical in the sentence. When a citation does break, the error names
the missing token, which turns the repair into a grep.

Citations into the **libhdf5 tree** — 343 distinct file/line pairs, in records,
expectations, pickles and generators — get a weaker gate of their own,
`tools/check_upstream_citations.py`: the file exists, the line is in range, and
the line holds something other than whitespace, a lone brace or a comment
delimiter. That is all it can check without an anchor, and the anchor is what it
cannot have. Inferring one from the surrounding prose was built and measured
first: of 842 citation occurrences, 425 name no function at all in their context,
and the mismatches were dominated by sentences carrying two citations and two
function names, which cross-match into false positives. A gate whose false
positives look like its true positives gets switched off, so this one checks only
the part that needs no annotation — and misses, by construction, a citation that
drifts onto *another statement*.

It still earns its place. Measured when it was written, against develop
`b7b85e7abf9`: **nine** distinct citations had drifted onto a blank line, a bare
brace or a comment terminator, in **sixteen** places, each one or two lines from
the statement its own prose described. None was wrong when written; upstream
inserted lines above them.

The tree is not in this repository and its location is a per-machine path that
portable provenance forbids recording, so the checker reads `HDF5_SOURCE_DIR`
(the variable the devcontainer build script already uses) and reports itself
**SKIPPED** when that is unset or does not name a checkout. A skip is not a pass
and prints as its own word; the OK line names the upstream revision it agreed
with, because a citation is only correct *against a stated tree*.

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
  `tools/h5cve evidence` from the canary matrix (about 8 seconds).  It pins the
  build it measured in two fields, and the second one exists because the first
  is not enough: `libhdf5_version` is a bare string like `2.3.0`, and this
  repository has measured two builds of `2.3.0` five weeks apart that disagree
  about whether a defect is present.  So `libhdf5_build` carries
  `configured_on`, `build_mode`, `sanitizers` and `settings_sha256` alongside
  it.  Both are filled in from the matrix artifact by the generator —
  `--libhdf5-version` remains only as an override for an artifact produced
  before the artifact carried a build.

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

No slot is `not_assessed` as of 2026-09-02. Every cell now says one of three
things: demonstrated, partly demonstrated, or reviewed-and-missing. A family
with no fixture for a category declares that in its record's
`verification_negatives` block, with the date it was reviewed and the reason,
and `h5cve verification` renders it `absent`. An empty annotation set with no
such declaration still renders `not_assessed`, so the mechanism cannot be used
to tidy a column -- it can only record a review that actually happened.

**58 of 176 requirement-slots are currently `met`.** None is `not_assessed`. The distribution matters
more than the total:

- OSS-Fuzz integration is the only requirement still `absent` for every family.
- Lazy validation is `partial` everywhere: measured, and holding, but on the
  oracle as a whole rather than family by family.
- Reviewed fixture/recipe annotations now carry the boundary, arithmetic,
  nesting and reference-semantics evidence outright: `not_assessed` in those
  four columns is 0, and what remains uncovered is `absent` with a reason --
  4 arithmetic, 5 nesting and 5 reference-semantics families. The annotations
  are a review of what each fixture's documented mechanism actually exercises,
  never an inference from finding-code spelling, which is why a family with many
  fixtures can still be `not_assessed` -- version, flag and checksum fixtures
  exercise none of these categories. What the sweep establishes is mostly which
  boundary VALUES the corpus lacks: `n` is thin nearly everywhere (3 families),
  `max` and `allocation_budget` reach 4 each, and `below_minimum` -- a value
  under a structure's own floor rather than one below a count -- is so far a
  single fixture.
- The 2026-09-02 sweep found that the `not_assessed` cells were mostly NOT
  missing coverage. 80 of 367 expectation files carried no `h5cve` family, and
  they included every depth and budget fixture in the tree; an uncontracted
  fixture cannot count for any family, so the arithmetic and nesting columns
  read as unassessed while the fixtures that would discharge them sat outside
  the contract. 22 were contracted, each with its canary measured first (a
  family contract puts a fixture into the matrix, so `allowed_statuses` is a
  measurement, not a guess): 15 `verified`, 5 `unexercised`, and 2 `violation`
  that earned matrix-policy overrides. Six are multi-family, because a shared
  v2-B-tree depth ceiling exercised on a client's index belongs to both. 58
  expectation files remain uncontracted; none of them is currently the only
  candidate for a `not_assessed` cell, because there are none left.
- The reviewed negatives split into two kinds, and the distinction is the
  useful part. STRUCTURAL: external links cannot nest, because h5policy decodes
  the target path and never opens it; a dataspace message is a rank byte and a
  flat array; `validation_controls` is profiles and budgets and references
  nothing. CONSTRUCTIBLE BUT NOT BUILT, which is the real backlog: a VDS naming
  itself as its own source, an external link naming its own file, two EFL slots
  sharing one heap name offset, a v2-B-tree node whose child address names an
  ancestor (the cycle fixtures that exist are contracted to the CLIENTS, so the
  shared engine's own guard has no specimen), and an MDCI flush-dependency
  cycle. One negative is neither: `address_space_bounds` has two fixtures
  carrying 16-byte lengths at and past 2**64, but compatibility preflight
  declines the width before either value is decoded, so annotating them would
  have been vacuous.
- Dedicated fuzz targets exist for 2 families of 16. `h5mutate` is a locator
  plus a recipe table per family, so the cost of the next family is its locator.
  A recipe is only counted once it emits its intended finding on seeds other
  than the one it was written against -- the heap recipes were verified on four
  structurally different heaps, and a fifth candidate was rejected for failing
  that bar.
- 14 families pin evidence locations as well as finding codes; the remaining
  2 need cursor arithmetic at the emit site rather than test metadata.
- Truncation is `met` for 12 families, `partial` for 4 whose seed exceeds the
  sweep budget, and `absent` for 0; see
  [`truncation-sweep.json`](truncation-sweep.json).
- No-activation-on-failure is `met` for 8 families and `partial` for 8 because
  the exact-build probe observes an activation or crash in those families.
  `external_file_list` joined that list on 2026-08-24 without libhdf5 changing:
  the probe's fallback single-element read moved from the origin to the last
  element, and the wrapped EFL segment it now reaches is opened before it is
  rejected. A count that goes DOWN because the harness asks a harder question is
  the intended direction -- see
  the EFL entry under [`cases/`](cases/). `message_envelope` joined on
  2026-09-02 for the same kind of reason -- not a libhdf5 change, but the
  regenerated matrix picking up `malformed/attr_gheap_free_undersized.h5`,
  whose global-heap free-space sentinel never terminates.

`check_registry.py` enforces the report's structure — every manifest record
present and every requirement scored — and derives the summary counts above.
It does not require any particular grade. Gating on the grades would be
permanently red and therefore ignored; the file is a distance measure.
