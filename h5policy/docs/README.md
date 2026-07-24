# h5policy Tool Guide

The `h5policy` tool suite validates HDF5 metadata, cross-checks that independent
parser against `libhdf5`, generates its regression corpus, and fuzzes both the
policy oracle and installed HDF5 tools. This guide describes the commands under
[`h5policy/tools`](../tools) and explains the differential harness's
cross-invariants.

Run the examples below from the repository root.

## Tool map

| Tool | Purpose |
| --- | --- |
| [`h5policy`](../tools/h5policy) | Parse reachable HDF5 metadata independently of `libhdf5`, apply a security profile, and emit a JSON decision. |
| [`h5policy-diff`](../tools/h5policy-diff) | Compare h5policy decisions and structural facts with `libhdf5` through h5py and optional HDF5 command-line tools. |
| [`h5policy-fuzz`](../tools/h5policy-fuzz) | Mutate HDF5 seeds and look for h5policy crashes, hangs, and unsafe acceptances relative to h5py's `libhdf5`. |
| [`h5policy-crashfuzz`](../tools/h5policy-crashfuzz) | Mutate HDF5 seeds against the installed HDF5 command-line tools and triage any crashers with h5policy. |
| [`h5policy-gencorpus`](../tools/h5policy-gencorpus) | Regenerate deterministic valid, malformed, policy, resource, coverage, integration, and CVE fixtures. |
| [`h5policy-fuzzlib`](../tools/h5policy-fuzzlib) | Provide the shared mutation engine, seed loader, and guided corpus used by both fuzzers; this is a support module, not a normal CLI. |

## `h5policy`

`h5policy` is the primary metadata preflight oracle. It reads HDF5 bytes through
GNU poke rather than `libhdf5`, validates the reachable metadata it understands,
applies a named policy profile, and writes one JSON report to standard output.
It is deliberately metadata-only and read-only: it does not load plugins,
decompress dataset payloads, open external files, repair the input, write to it,
or perform application deserialization.

```sh
./h5policy/tools/h5policy --profile untrusted-strict file.h5
./h5policy/tools/h5policy --profile forensic \
    --continue-after-rejection file.h5
./h5policy/tools/h5policy --profile trusted-fast \
    --max-walk-seconds 60 file.h5
```

The four profiles are:

- `legacy`: compatibility-biased, with unlimited data budgets but bounded
  analysis.
- `trusted-fast`: normal validation, generous budgets, and permissive feature
  policy.
- `untrusted-strict`: strict mapping, tight budgets, and features denied by
  default. This is the default profile.
- `forensic`: non-strict mapping and deeper, bounded reporting without following
  external references.

`--strict` and `--non-strict` override the profile's mapping mode.
`--continue-after-rejection` continues the reachable walk after any rejecting
finding so the report can include multiple problems. `--max-walk-seconds N`
overrides the profile's internal walk deadline; the shell wrapper retains a
hard wall-clock backstop.

The process exit code mirrors the JSON `decision`:

| Exit | Decision | Meaning |
| ---: | --- | --- |
| 0 | `accept` | The file passed the selected profile. |
| 1 | `accept_with_warnings` | The file was accepted with non-rejecting findings. |
| 2 | `reject_corrupt` | The metadata is structurally corrupt. |
| 3 | `reject_policy` | A structurally recognized feature violates policy. |
| 4 | `reject_resource` | A resource or denial-of-service budget was exceeded. |
| 5 | `unsupported_coverage_gap` | Safe validation stopped at a recognized but insufficiently covered feature. |
| 70 | `internal_error` | The oracle itself failed to render a normal decision. |

`unsupported_coverage_gap` is an explicit refusal, not an acceptance. See the
[main h5policy README](../README.md) for the report schema, validation coverage,
and boundary, and [H5PolicyProfile.md](H5PolicyProfile.md) for the complete
profile semantics.

### Metadata cache-image hard boundary

All profiles share the same cache-image decode boundary. h5policy validates the
`MDCI` message, bounded container and entry envelopes, and records the address
ranges shadowed by cache entries. It does not decode the cached entry bodies.
A structurally valid cache-image fixture therefore returns exit `5`,
`unsupported_coverage_gap`, and
`H5_UNSUPPORTED_PICKLE_COVERAGE_GAP`; `analysis.complete` and
`analysis.walk_completed` are `false`.

`--continue-after-rejection` is not a cache-image enable switch. With
continuation enabled, h5policy skips only shadowed addresses and continues
checking reachable unshadowed metadata, then reports
`analysis.stop_reason: "cache_image_coverage_gap"`. Without continuation, the
normal fail-fast stop reason is `"rejection"`. Neither mode accepts the file.

For example:

```sh
./h5policy/tools/h5policy --profile forensic \
    --continue-after-rejection h5policy/tests/valid/cache_image.h5
echo $?  # 5
```

The complete coverage description is in the
[main README](../README.md#metadata-cache-image-hard-boundary); the
[profile reference](H5PolicyProfile.md#metadata-cache-image-hard-boundary)
documents the control-flow semantics.

## `h5policy-diff`

`h5policy-diff` is an asymmetric differential oracle. It does not require
h5policy and `libhdf5` to produce identical results. Instead, it requires their
disagreements to remain inside a safe, deliberately scoped envelope. This finds
field-offset, version-selection, datatype-size, and dataspace-decoding mistakes
that fixtures written for known cases can miss.

```sh
./h5policy/tools/h5policy-diff file.h5 another.h5
./h5policy/tools/h5policy-diff --dir h5policy/tests
```

### Reference observations

For every input, the harness runs h5policy under the `forensic` profile so the
reachable walk accumulates full metrics. It obtains reference facts from:

- **h5py**, which supplies the primary structural result and the external-link,
  dataset-shape, datatype-size, and rank observations.
- **h5dump** and **h5debug**, when present on `PATH`, which supply independent
  acceptance signals. Their disagreement with h5py is normally a warning.
- A deeper, isolated h5py probe, used only when h5policy calls a structurally
  openable file corrupt. It checks attributes and creation-order indexes and
  reads bounded, non-object datasets. A full-data `h5dump` probe additionally
  exercises filter and decompression paths.

The primary h5py check follows hard links but does not follow soft or external
links. A file counts as structurally open only after that reachable graph has
been traversed successfully. An exception during traversal counts as rejection,
even if the initial `H5Fopen` succeeded. The h5py checks run in child processes;
a child crash, invalid result, or timeout also counts as `libhdf5` rejection
instead of taking down the harness.

### Cross-invariants

The cross-invariants are implications and comparisons across two independent
parsers:

| Invariant | Operational contract | Disagreement |
| --- | --- | --- |
| A | `libhdf5` structurally opens implies h5policy does not return `reject_corrupt`. | Hard failure unless the A+ or A~ exception applies. |
| A' | `libhdf5` rejects implies h5policy returns an explicit safe refusal. | Hard failure for acceptance or an internal/non-refusal result. |
| B | h5py and h5policy agree on whether at least one external link exists. | Hard failure. |
| C | Compare the maximum logical dataset byte count seen by each parser. | Advisory warning for either mismatch direction. |
| D | h5policy's maximum dataset rank does not exceed h5py's. | Overcount is a hard failure; undercount is a warning. |

B, C, and D are evaluated only when the primary h5py traversal succeeds.

#### A: no unsupported corruption accusation

```text
libhdf5 structurally opens  =>  h5policy decision != reject_corrupt
```

This detects corruption false positives. If `libhdf5` traverses the structure
successfully but h5policy calls it corrupt, h5policy may have read the wrong
field, applied the wrong format version, or imposed an invalid structural rule.

A concerns the corruption classification, not overall acceptance. A policy,
resource, or coverage refusal does not violate A because it does not claim the
bytes are structurally corrupt.

Two narrowly defined cases demote an apparent A failure to a warning:

- **A+** means the basic structural traversal succeeded, but another bounded
  `libhdf5` path supplied rejection evidence. Evidence includes errors while
  traversing children, enumerating attributes or creation-order indexes,
  reading small datasets, or running `h5dump`/`h5debug`. This supports
  h5policy's eager corruption finding without claiming the basic h5py walk
  exercised the same bytes.
- **A~** means all corruption findings are confined to active metadata that
  current read-only `libhdf5` paths deliberately leave unopened: file-global
  SOHM search or free-space-manager metadata, or dense secondary
  creation-order indexes. h5policy validates these structures eagerly even
  when `libhdf5` can enumerate through another index.

Both variants remain visible as warnings but do not make the harness exit
non-zero.

#### A': no unsafe acceptance

```text
libhdf5 rejects  =>  h5policy explicitly refuses
```

The safe refusal set is:

```text
reject_corrupt
reject_policy
reject_resource
unsupported_coverage_gap
```

An h5policy acceptance violates A': a consumer honoring the preflight would
process bytes that the reference implementation cannot structurally consume.
An `internal_error` is also not a safe refusal.

If h5policy refuses as `reject_policy`, `reject_resource`, or
`unsupported_coverage_gap`, A' passes but emits a classification warning.
Refusing before reaching the corruption is safe, but the harness records that
h5policy and `libhdf5` did not classify the failure in the same way.

#### B: external-link presence

```text
(h5policy external_links > 0) == (h5py external_links > 0)
```

B is a hard invariant because overlooking an external link can hide an external
dependency or boundary crossing. It compares presence, not the exact count;
two positive but unequal counts still pass B.

#### C: maximum logical dataset bytes

For each dataset, h5py computes:

```text
product(dataset.shape) * H5Tget_size(dataset datatype)
```

It uses `libhdf5`'s datatype size rather than NumPy's in-memory `itemsize`.
h5policy independently reports `max_logical_dataset_bytes_seen` from the
on-disk declarations.

C is advisory in the current implementation. Exact equality is clean; either
mismatch direction produces a warning:

- h5policy larger than h5py is labelled conservative. This can arise when a
  declared compound size is larger than `libhdf5`'s packed view.
- h5policy smaller than h5py is labelled an undercount and coverage gap.

The short invariant synopsis writes the intended no-overcount relation as
`h5policy <= h5py`, but the executable check intentionally makes neither
direction a hard corpus failure. Rank and decision agreement remain the hard
offset-decoding guards.

#### D: maximum dataset rank

```text
h5policy max_rank_seen <= h5py max_rank
```

A greater h5policy rank is a hard failure because it strongly suggests that a
dataspace field or offset was mis-decoded. A smaller rank passes the inequality
but produces an additional coverage warning. Equality is the only completely
clean result.

### Results and exit status

Each file receives one aggregate status:

- `[PASS]`: no hard failures or warnings.
- `[WARN]`: at least one informational disagreement and no hard failure.
- `[FAIL]`: at least one hard invariant failed.

Warnings do not affect the process exit code. The command exits `1` when any
file has a hard failure and `0` otherwise. Missing `h5dump` or `h5debug` is
reported and that optional oracle is skipped.

## `h5policy-fuzz`

`h5policy-fuzz` is a structure-aware fuzzer for the policy oracle. It mutates
valid HDF5 seeds, runs h5policy in forensic mode with a timeout, and normally
cross-checks the mutant against h5py's `libhdf5`. A fixed `--seed` reproduces
the same mutant stream, and every saved finding is a standalone HDF5 file.

```sh
./h5policy/tools/h5policy-fuzz --iters 500 --seed 20260703 \
    --seeds h5policy/tests/valid
./h5policy/tools/h5policy-fuzz --iters 2000 --guided --show-coverage
./h5policy/tools/h5policy-fuzz --iters 1000 --coverage-only --guided
```

The principal classifications are:

| Classification | Meaning | Severity |
| --- | --- | --- |
| `HANG` | h5policy exceeded its per-mutant timeout. | Hard |
| `CRASH` | h5policy returned an unknown exit or unparseable output. | Hard |
| `FALSE_ACCEPT` | `libhdf5` cleanly rejected a mutant that h5policy accepted. | Hard |
| `ACCEPT_VS_CRASH` | h5policy accepted, while the reference process crashed or timed out. | Advisory because the crashed oracle is not trustworthy ground truth. |
| `INTERNAL` | h5policy returned the controlled `internal_error` decision. | Advisory, but saved for investigation. |
| `FALSE_REJECT` | `libhdf5` opened while h5policy returned `reject_corrupt`. | Advisory |
| `OK` | Agreement or an otherwise uninteresting mutation. | Discarded |

`--guided` breeds mutants that reach new h5policy finding codes back into the
input pool, allowing later mutations to compound structural changes.
`--coverage-only` skips the `libhdf5` oracle for faster reach measurements.
Saved findings default to `h5policy/tests/fuzz-findings`; use `--out` to isolate
different campaigns.

## `h5policy-crashfuzz`

`h5policy-crashfuzz` tests the HDF5 commands installed on `PATH`, rather than
the possibly different `libhdf5` bundled with h5py. It is intended to find
crashes and hangs in the library version that users will actually run.

By default it exercises metadata-only and full-data `h5dump`, recursive `h5ls`,
`h5stat`, and `h5repack` when those commands are available. `h5debug` and
`h5copy` are optional and must be requested explicitly with `--tools`.

```sh
./h5policy/tools/h5policy-crashfuzz --iters 1000 --seed 20260703
./h5policy/tools/h5policy-crashfuzz --iters 5000 --guided \
    --tools h5dump,h5ls,h5stat,h5repack,h5debug
```

A crash is a command killed by a recognized signal, a timeout, or output that
contains a memory-failure marker. Findings are grouped by tool, fault kind, and
faulting function/message so repeated mutants hitting one defect form a single
signature. When `gdb` is available, the fuzzer uses a backtrace to improve that
signature.

Every crasher is passed through h5policy for triage. A crash on a file h5policy
accepts is the strongest result, but a crash on malformed input remains a tool
robustness problem. Reproducers and sidecar metadata default to
`h5policy/tests/crash-findings`. The command exits non-zero when it finds any
distinct crash signature.

## `h5policy-gencorpus`

`h5policy-gencorpus` recreates the deterministic fixture tree used by the
regression tests. Valid inputs are constructed with h5py; malformed inputs are
usually byte-patched from valid bases so generation does not depend on
`libhdf5` agreeing to create or reopen corrupt bytes.

```sh
./h5policy/tools/h5policy-gencorpus
./h5policy/tools/h5policy-gencorpus /tmp/h5policy-corpus
```

The default target is `h5policy/tests`. Generated `.h5` files are build
artifacts; the tracked expectations in `h5policy/tests/expected/*.yml` are the
regression specification. See the [test-suite README](../tests/README.md) for
the corpus layout and assertions.

## `h5policy-fuzzlib`

`h5policy-fuzzlib` is imported by both fuzzing front ends. It is not intended to
be invoked directly. It owns seed discovery, per-process mutant scratch paths,
the guided `Corpus` input pool, and these shared mutation strategies:

| Strategy | Mutation |
| --- | --- |
| `bitflip` | Flip one or more random bits. |
| `interesting` | Replace bytes with boundary values such as `0x00`, `0x7f`, `0x80`, and `0xff`. |
| `truncate` | Cut the file at a random offset to exercise short-read handling. |
| `super` | Change a v2/v3 superblock address and repair its checksum so deep validators see the mutated pointer. |
| `dict` | Splice real HDF5 signatures, versions, and message-type bytes at likely structural offsets. |
| `struct` | Mutate an interior field of a recognized checksummed block and repair the checksum so validation proceeds past the checksum gate. |

The checksum-repairing strategies are important: an ordinary bit flip inside a
checksummed structure is rejected immediately, while `super` and `struct` let
the mutant reach the deeper traversal and consistency checks under test.

## Typical workflow

Regenerate and run the deterministic suite first, use the differential harness
to inspect a particular corpus or reproducer, then use the fuzzers for broader
exploration:

```sh
./h5policy/tools/h5policy-gencorpus
./h5policy/tests/run.sh
./h5policy/tools/h5policy-diff --dir h5policy/tests
./h5policy/tools/h5policy-fuzz --iters 2000 --guided
./h5policy/tools/h5policy-crashfuzz --iters 2000 --guided
```
