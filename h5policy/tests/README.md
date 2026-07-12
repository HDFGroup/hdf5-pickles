# h5policy Tests

Regression corpus for the `h5policy` oracle.  Every fixture has an expected,
controlled outcome; a change that alters any decision is surfaced for review.

## Layout

- `expected/*.yml` — the tracked specification: one case per file with its
  profile, expected decision, expected exit code, required finding codes, and
  forbidden outcomes (`crash`, `timeout`, `external_open`, `plugin_load`,
  `write`).
- `unit_datatype.pk` — synthetic checks for the bounded, depth-guarded
  datatype validator (recursion cap and truncation handling), run under poke.
- `unit_limits.pk` — reduced-limit, in-memory characterization checks for the
  current `H5PolicyLimits` boundaries, saturation, finding classes, compound
  rules, feature switches, and run-mode defaults.
- `valid/ malformed/ policy/ resource/ coverage/ cve/` — generated fixtures
  (git-ignored build output; see below).

## Running

```sh
./run.sh
```

This regenerates the fixtures, runs the datatype and profile-limit unit checks,
runs `h5policy` over every `expected/*.yml` case and asserts the result, then
runs the differential harness.

The suite is also wired into CTest (top-level `CMakeLists.txt`), so
`ctest -R h5policy_regression` runs it from a CMake build. The test is skipped
if `poke` or `python3` + `h5py` are unavailable.

## Differential harness

`../tools/h5policy-diff` cross-checks h5policy's independent parse against
`libhdf5`, catching field-offset bugs that the corpus alone can miss:

- **h5py** is the structural reference — does `libhdf5` open the bytes, and what
  external links, dataset shapes, and `H5Tget_size` values does it report;
- **h5dump** / **h5debug** are independent "does `libhdf5` accept these bytes"
  signals (optional; skipped if not on `PATH`).

It fails if h5policy accepts a file that `libhdf5` structurally rejects, calls a
structurally valid file corrupt with no deeper `libhdf5` evidence, disagrees on
external references, or over-counts a dataset's **rank**. A `reject_corrupt` on a
file that h5py can structurally traverse is downgraded to an `A+` warning when a
bounded, out-of-process `libhdf5` probe also errors while inspecting attributes,
reading small datasets, or running optional `libhdf5` tools; those eager catches
are security-useful, not hard false positives.

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
them.  `cve/` is reserved for minimized CVE seeds.
