# Tools

## Command Entry Points

The top-level `tools/` directory collects repository commands.  Most entries are
relative symlinks to the tool-owned implementations:

```text
tools/h5explain          -> ../h5explain/tools/h5explain
tools/h5patch            -> ../h5patch/tools/h5patch
tools/h5policy           -> ../h5policy/tools/h5policy
tools/h5policy-diff      -> ../h5policy/tools/h5policy-diff
tools/h5policy-fuzz      -> ../h5policy/tools/h5policy-fuzz
tools/h5policy-fuzzlib   -> ../h5policy/tools/h5policy-fuzzlib
tools/h5policy-crashfuzz -> ../h5policy/tools/h5policy-crashfuzz
tools/h5policy-gencorpus -> ../h5policy/tools/h5policy-gencorpus
tools/h5policy-probe     -> ../h5policy/tools/h5policy-probe
tools/h5policy-truncate  -> ../h5policy/tools/h5policy-truncate
tools/h5policy-lazy      -> ../h5policy/tools/h5policy-lazy
tools/h5policy-seamcheck -> ../h5policy/tools/h5policy-seamcheck
tools/h5mutate           -> ../h5policy/tools/h5mutate
```

`tools/pkdoc.py`, `tools/check_tutorial.py`, `tools/finding_registry.py`, and
`tools/h5cve` are repository-level helper scripts (not symlinks): `pkdoc.py`
generates and checks the format-reference sidecars, `check_tutorial.py`
executes the GNU poke sessions embedded in `TUTORIAL.md`,
`finding_registry.py` loads and exports the sharded finding registry, and
`h5cve` is the CVE case orchestrator described below.

## h5cve Case Orchestrator

`tools/h5cve` chains the existing tools into one provenance-stamped CVE case
bundle and auto-populates the [`registry/cve-case.yml`](registry/cve-case.yml)
schema.  It duplicates no tool logic — it shells out to `h5policy`, `h5markers`,
`h5explain`, and the exact-build probe, and maps the primary finding to its
invariant through [`registry/findings/`](registry/findings/).

```text
h5cve init  <id> --poc FILE                 # bundle: PoC, sha256, skeleton case.yml
h5cve triage <case>                         # oracle + census + registry mapping
h5cve verify <case> --baseline BINDIR [--candidate BINDIR]   # exact-build probes
h5cve variants <case> [--seed VALID]        # typed semantic variants via h5mutate
h5cve minimize <case>                        # deferred: structure-aware reducer
h5cve promote <case>                        # draft tests expectation + registry case
h5cve census <root>                         # read-only oracle census of an HDF5 tree
h5cve matrix [--baseline BINDIR] [--output F]  # exact-build canary matrix
h5cve evidence [--matrix F]                 # measured libhdf5 verdict per family
h5cve verification                          # §12 requirement status per family
```

`triage` names the violated invariant from the primary finding. Ambiguous
finding codes are emitted by more than one walker, so the mapping is resolved
with the finding **message** via grouped rules in
`registry/findings/routes/`. When no rule matches, triage asserts **nothing**
and reports the candidate families instead — an unnamed invariant is a visible
gap, a wrong one is a wrong fix.
Production codes that have not reached that semantic review are source-tracked
in `registry/finding-backlog.yml`; triage deliberately leaves their mapping
unset until they move into the finding catalog.

`triage` also records **every** family the file implicates, not just the
primary's, in `family_coverage`.  The strict profile stops at the first
rejection, so on a file with several unrelated defects `record` names one family
and a single canary would be all `verify` ever ran — a `verified` canary is then
a statement about one finding, not about the file.  The forensic profile
continues after rejection, so its finding list is the superset triage resolves.
`verify` runs a canary for each of those families and reports one row apiece;
a family with no canary is reported as an explicit `coverage_gap` row rather
than omitted, and a forbidden activation in any of them fails the command.

## Exact-Build Canary Matrix

`h5cve matrix` runs the selected libhdf5 build against every corpus fixture that
declares an `h5cve` contract, and reports one row per fixture/family:

| status | meaning |
|---|---|
| `verified` | the family exercise ran and every required entry point succeeded |
| `unexercised` | the exercise was selected but did not complete — typically because libhdf5 rejected the file, which is the expected result for a malformed fixture |
| `violation` | a forbidden activation occurred, or the build diverged from the oracle where the fixture requires alignment |
| `coverage_gap` | no canary exists for that family, or the fixture declares no contract |

[`registry/h5cve-matrix-policy.yml`](registry/h5cve-matrix-policy.yml) pins which
statuses each fixture may report; the matrix exits non-zero on anything else. A
fixture must state its family and permitted statuses explicitly, so a new canary
or a changed traversal surface cannot silently inherit a passing outcome.

Only `reject_corrupt` is compared against the build for alignment.
`reject_resource` and `reject_policy` are decisions about the selected *profile*
— a traversal budget or a denied feature — which libhdf5 has no equivalent of,
so those rows report `not_comparable` rather than a divergence.

A canary that passes on a valid fixture does not show it could detect a defect.
Each family therefore also needs a malformed fixture that libhdf5 opens
successfully and that carries the family's defect: one rejected at `H5Fopen`
never reaches the family surface at all. All 15 families with canaries currently
have such a specimen.

`h5cve evidence` turns a matrix run into a per-family verdict on the selected
build (`enforced`, `partial`, `diverges`, `unmeasured`) and writes
[`registry/libhdf5-evidence.yml`](registry/libhdf5-evidence.yml). That file is
the **measurement**; `validation-coverage.yml`'s `validators.hdf5` is the
hand-maintained **claim**, and `tools/check_registry.py` fails on any
disagreement — so a claim about libhdf5 cannot drift from what was observed.
Regenerate after changing the build under test or the corpus:

```sh
tools/h5cve evidence --libhdf5-version 2.2.0    # ~8s, runs the matrix itself
```

`h5cve verification` scores each family against the eleven §12 verification
requirements and writes
[`registry/verification-coverage.yml`](registry/verification-coverage.yml).
Statuses are `met`, `partial`, `absent` or `not_assessed` — the last is not a
soft `met`, and requirements that would need fixtures classified by hand are
marked that way rather than inferred. `check_registry.py` enforces that every
record is scored on every requirement, but not the scores themselves: the file
measures distance from §12 rather than gating on it.

## Truncation Sweep

Every prefix of a valid file is a file an attacker can hand you, and each one
must be *decided*: `h5policy` has to terminate with a verdict rather than escape
with an exception, hang, or report an internal error.
`tools/h5policy-truncate` walks those prefixes and asserts exactly that.

```sh
tools/h5policy-truncate h5policy/tests/valid/*.h5      # exhaustive, minutes
tools/h5policy-truncate --max-prefixes 512 SEED...     # bounded
```

Analysis runs **in-process** through the `h5policy_analyze` seam, all prefixes
in one poke session: ~250 prefixes/second against ~2/second for the CLI, which
is what makes an exhaustive sweep practical at all.

Coverage is reported per seed as `exhaustive` (every byte boundary) or `sampled`
(the budget forced striding, spending half of it on every boundary of the
metadata-dense head). A sampled sweep is not an exhaustive one and does not
satisfy §12. `run.sh` runs a bounded subset as a regression check; the full
corpus sweep is on-demand, like the fuzzer.

Results land in [`registry/truncation-sweep.json`](registry/truncation-sweep.json),
which `h5cve verification` reads to score the §12 truncation requirement.

## Lazy-Validation Measurement

"Validation remains lazy" is falsifiable: the cost of validating a file must be
a function of its **metadata**, not of how much raw data it carries.
`tools/h5policy-lazy` measures that on the report's deterministic counters —
`metadata_bytes_seen` and `walk_operations` — rather than wall-clock, which is
dominated by interpreter startup and too noisy to assert on.

```sh
tools/h5policy-lazy                                  # human-readable
tools/h5policy-lazy --output registry/lazy-validation.json
```

Three ladders, and the third is what makes the first two mean anything:

| ladder | varies | expectation |
|---|---|---|
| `data` | raw data ~1000x, structure fixed | counters flat |
| `filtered` | same with deflate, **one chunk throughout** | counters flat — a validator that decompressed to inspect payload would show it |
| `chunks` | chunk count 100x — real metadata growth | `walk_operations` **must rise** |

Without the control, flat counters could equally mean the counters are broken.
The `filtered` ladder pins the chunk count deliberately: letting it vary with
`n` would measure metadata growth rather than data volume.

Counters are bounded by ratio, not equality — decoding a larger stored-size
field can cost a few operations without any payload being touched, while a
validator that read payload would grow with `n`. Current result: cost flat
across a ~1000x data increase, with the control rising 375 → 987 → 7107.

## In-Process Seam Self-Check

Analysing through `h5policy_analyze` instead of the CLI is ~7x faster (the
pickles load once, not per file), but every analysis then shares interpreter
state. `h5policy_analyze`'s reset list is what keeps them independent, and a
leak there is worse than slowness: one hostile input could silently change every
verdict after it, and a fuzzer would report those corrupted verdicts as findings.

**`tools/h5policy-seamcheck` is the gate on any work that batches analyses.**

```sh
tools/h5policy-seamcheck --count 120        # default: forensic profile
tools/h5policy-seamcheck --profile legacy --count 60
```

Two checks, over adversarial mutants built with the fuzzer's own engine:

| check | asserts |
|---|---|
| **A** agreement | the seam's (decision, finding codes, feature flags) equals the CLI's, which is the shipped behaviour and therefore ground truth |
| **B** order | the same mutants in a *different* order give the same verdicts |

Both passes select the same profile by construction — a forensic CLI run against
a seam left on its `untrusted_strict` default produces a large and very
plausible-looking divergence that has nothing to do with state.

Its first production run found a real leak: `h5policy_heap_data_seg_size`
survived into the next analysis, and a larger value from an earlier file
silently disabled the bound three call sites check link-name offsets against.
Check **A** caught it; check **B** did not, because the leak saturates within a
few analyses and both orders then agree. Neither check subsumes the other.

## h5mutate Semantic Mutation Engine

`tools/h5mutate` applies **typed** mutations that each target one named invariant
in [`registry/validation-coverage.yml`](registry/validation-coverage.yml), reseal
the enclosing checksums, and emit a recipe sidecar (parent hash, intended
invariant/finding, changed byte ranges, reseals).  Each mutant is
self-validating — `family --verify` asserts h5policy emits the intended finding.

```text
h5mutate list  [--seed FILE]
h5mutate apply --seed FILE --recipe NAME --out FILE
h5mutate family --seed FILE --out-dir DIR [--verify]
```

The current slice covers the object-header continuation family (the interval
model): target overlapping the source chunk at start/interior/end, zero-size,
out-of-file, and alias onto an already-decoded chunk.  `run.sh` runs
`family --verify` as a pinned check, and `h5cve variants` uses it to populate a
case bundle.  The structure-aware **reducer** (`h5cve minimize`) is the
remaining half of roadmap change #5.

Bundles live under `cases/<id>/` (git-ignored working scratch); `promote` is
what lands tracked artifacts in `h5policy/tests/` and `registry/`.  The exact-
build probe (`tools/h5policy-probe`, and `h5policy/tools/probe/`) runs a selected
libhdf5 build under an `LD_PRELOAD` activation interposer inside a sandbox and
reports whether rejection preceded any OS-observable activation; see
[`h5policy/tools/probe/README.md`](h5policy/tools/probe/README.md).

## Marker Scanner

`h5markers` is a multithreaded file scanner for concrete on-disk markers used
by HDF5 and Onion files. It covers the published format specifications and
implementation-defined signatures used by the current HDF5 library. See
[MARKERS.md](MARKERS.md) for the complete list and its sources.

`h5markers` can be used to quickly identify the locations of these markers in large files, which can be useful for debugging, data recovery, or understanding file structure.

Build:

```bash
cmake -S . -B build
cmake --build build
```

Usage:

```bash
# List all known markers
build/h5markers --list-markers

# Scan a file with the default thread count
build/h5markers path/to/file.h5

# Scan with an explicit thread count (-j is a synonym for --threads)
build/h5markers --threads 8 path/to/file.h5.onion
build/h5markers -j 8 path/to/file.h5.onion

# Restrict the scan (and listing) to one group of markers
build/h5markers --group HDF5 path/to/file.h5
build/h5markers --group Onion --list-markers path/to/file.h5.onion

# Show usage
build/h5markers --help
```

The scanner prints one line per detected marker with the marker name and its file offset in both
hexadecimal and decimal. Progress is reported on stderr when scanning in a terminal.

For example, scanning the sample file `file.h5` in this repository produces the following output:

```text
HDF5_SIGNATURE  0x0000000000000000 (0)
OHDR            0x0000000000000030 (48)
OHDR            0x00000000000000C3 (195)
TREE            0x00000000000001DF (479)
```

## h5explain Interactive Explorer

`h5explain` starts GNU poke with the repository pickles loaded and installs a small command layer for incremental HDF5 byte-level exploration:

```sh
./tools/h5explain [OPTIONS] FILE [OFFSET]
./tools/h5explain --help
```

`OFFSET` may be decimal or hexadecimal, for example `48` or `0x30`. Without an offset, the tool starts at the HDF5 superblock.

Commands supplied with `-c`/`--command` or on a piped standard input run as a batch session that exits instead of entering the REPL:

```sh
printf 'root\nls\n' | ./tools/h5explain file.h5
./tools/h5explain -c root -c ls file.h5
```

**Navigation commands:** `root`, `h5super`, `cd ("PATH")`, `go (OFF#B)`, `go (OFF#B, "PATH")`, `gos ("0xADDR")`, `gos ("0xADDR", "PATH")`, `back`, `pwd`

`cd` accepts a link name, a relative or absolute path, and `.`/`..` components. `back` retraces the full history one step per call. `go`/`gos` refuse offsets at or past the end of the file.

Version 1 object headers have no signature, so `go`/`gos` infer them from the version and message count. When a kind was inferred rather than confirmed by a signature, `pwd` and `info` mark it `(inferred: no signature)`; reaching the same address through `root` or `cd` corroborates it and the marker disappears.

**Inspection commands:** `explain`, `explain (N)`, `explain_msg (N)`, `info`, `msgs`, `cur`, `ls` / `links`, `traverse`, `dump`, `h5dump`

**Policy commands:** `check`, `check_all`, `profile`, `profile ("NAME")`

`check` runs the h5policy oracle over the open file and reports the findings that bear on the cursor — matched by byte extent or by object path, since h5policy anchors findings both ways. When nothing bears on the cursor it distinguishes *reached*, *not reached*, *not recorded for this kind*, and *walk stopped early*, so silence is never mistaken for a clean bill of health. See [`h5explain/README.md`](h5explain/README.md#policy-checks).

Use `msgs` to list object-header messages, then `explain (N)` or `explain_msg (N)` to explain message `N` in the current object header. Type `help` at the prompt for a full description of each command.

`traverse` is the only command that recursively walks chunk indexes. Ordinary navigation and `info` map the current primitive only, so large chunk indexes are not traversed accidentally.

`back` returns to the location before the most recent navigation step (`go`, `gos`, `cd`, `root`, `h5super`). Only one level of history is kept.
