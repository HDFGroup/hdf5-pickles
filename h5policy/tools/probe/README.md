# Exact-build libhdf5 probe

`h5policy-probe` runs a **selected** libhdf5 build against one file and reports,
as JSON, what that exact build did and which OS-observable activation events
occurred. It is the release-gate answer to two questions the other harnesses
cannot pin down:

- **Which build?** `h5policy-diff` observes whatever libhdf5 h5py bundles;
  `h5policy-crashfuzz` drives whatever tools are on `PATH`. Here `--hdf5-bindir`
  names the build under test, the probe is compiled against it, and every result
  carries that build's version, linked-library soname, configuration,
  `settings_sha256`, build mode, and sanitizer list. The local directory is
  used to select and run the build but is not emitted into portable evidence.
- **Did rejection precede activation?** For a hostile file the corpus forbids
  external/VDS/EFL opens, filter-plugin `dlopen`, writes, and network. The probe
  observes those from outside the library and asserts them absent.

## Pieces

| File | Role |
|---|---|
| [`h5probe.c`](h5probe.c) | C program, linked against the selected build. Opens the file, visits every object, reads a bounded data/attr sample (exercising layout, filters, external storage), and prints a JSON decision + build identity. Installs no signal handlers — a libhdf5 crash dies with a signal the wrapper catches. |
| [`h5trace.c`](h5trace.c) | `LD_PRELOAD` interposer. Records file opens (read/write), `dlopen`, and network calls as raw events; the wrapper classifies them. Per-event unbuffered writes survive a crash. |
| [`../h5policy-probe`](../h5policy-probe) | Orchestrator: build selection + compile cache, sandboxed run, event classification, JSON, and `--forbid` assertions. |

## Outcome

`accepted` · `rejected_at_open` · `rejected_in_traversal` (opened a handle but a
later call refused, no crash) · `crashed` (signal) · `timeout` ·
`build_unavailable` (no `h5cc`/`cc`; skip, like the differential harness).

## Sandbox

Each run copies the input read-only into an isolated work dir (cwd), sets
`RLIMIT_CPU/AS/FSIZE/NOFILE/NPROC`, points `HDF5_PLUGIN_PATH` at an empty dir,
and preloads the interposer. **External/VDS/EFL targets are deliberately not
present** in the sandbox: the probe still records the foreign-open *attempt* (the
activation signal we want) even though the subsequent read then fails. A missing
external target therefore shows as `external_open > 0` with an
`rejected_in_traversal` outcome — that is correct, not a false alarm.

Network isolation is by observation only (the interposer records `socket`/
`connect`; assert `--forbid network`). Full namespace/seccomp isolation is out of
scope for this layer.

## Scope: OS-level only

This is the OS-observable half of roadmap change #3. It cannot see libhdf5
*internal* events — metadata-cache insertion, public-ID registration,
materialization ordering, in-process core-filter decompression, user callbacks,
or legacy-decoder fallback. Proving "rejection precedes activation" for those
needs internal event counters in a patched libhdf5 build (the deferred option B),
a separate cross-repo effort. Case records mark internal-only assertions
`unverified` accordingly.

## Usage

```sh
# One file against the build behind h5cc on PATH, asserting no activation:
h5policy-probe FILE --forbid external_open,plugin_load,write,network,crash --json

# A specific build:
h5policy-probe FILE --hdf5-bindir /path/to/hdf5/bin --json
```

Exit `0` clean · `2` a forbidden event (or crash) occurred · `3` build/toolchain
unavailable. Compiled artifacts are cached under `.build/` (git-ignored), keyed
by the toolchain + configuration so a build swap recompiles.

## Durability of a refusal, and the `durability` block

A refusal is evidence of safety only if it **holds**. libhdf5 has at least two
structures whose validation runs once per open and whose rejected result is then
reused:

- the **metadata cache image**, whose load is one-shot — `H5C_protect` clears
  `load_image` before calling `H5C__load_cache_image`, so the failing call
  consumes the attempt;
- the **local heap**, whose free-list validation sits inside
  `if (NULL == heap->dblk_image)` (`src/H5HLcache.c:713`), so a failed attempt
  leaves the image behind and the next protect skips the check.

In both, the first call fails and the file is then used. A probe that watches one
call cannot tell that apart from a refusal that holds, and `rejected_in_traversal`
reads as "libhdf5 refuses this" either way.

So every run ends with a **durability pass**: a *fresh* `H5Fopen`, then the same
read issued twice.

```json
"durability": {"first_call_failed": true, "verdict": "not_durable"}
```

`verdict` is `not_applicable` when the first call succeeded (there was no refusal
to test), `durable` when both calls failed, and `not_durable` when the first
failed and the second succeeded. That last case has one reading: the refusal did
not hold, and any verdict taken from the first call alone overstates what the
library refuses. `--forbid nondurable_rejection` turns it into exit 2.

Two design points, both learned the hard way:

- **The pass uses its own open.** The main pass has already primed whatever
  caches it touched, so repeating a call there would measure the main pass rather
  than the file.
- **It stays out of `outcome`, `materialization` and the activation counters.**
  Folding a retry into the primary verdict is exactly how an earlier
  creation-order fallback came to hide real refusals: only the retry's result
  reached `call_errors`, and files libhdf5 had refused were reported as accepted.
  The primary verdict still comes from the first pass alone.

Measured over the WHOLE corpus (317 files: valid, malformed, policy and cve):
272 `not_applicable`, 24 `durable`, 13 with no verdict (the probe crashed or the
open was refused), and **8 `not_durable`** --
`malformed/heap_free_list_chain_break.h5` and seven metadata-cache-image
fixtures (`malformed/mdci_*`, `cve/mdci_dup_addr_witness.h5`).

CORRECTION, and the reason the number is quoted with its scope: an earlier note
here said "of 18 valid and 60 malformed corpus fixtures, none report
`not_durable`, so the signal is specific rather than ambient". That sweep was an
alphabetical `head -60` and never reached the `mdci_*` files. The signal is
specific — 8 of 317 — but it was never zero, and the cache-image cluster is a
SECOND structure with the same property: `H5C_protect` clears `load_image`
before calling `H5C__load_cache_image`, so the failing call consumes the attempt
and every later access succeeds. Different mechanism, same observable.

## Resource limits, and the `limits` block

The probed process runs under `RLIMIT_CPU`, `RLIMIT_AS`, `RLIMIT_FSIZE`,
`RLIMIT_NOFILE` and `RLIMIT_NPROC` (`--cpu`, `--mem-mb`, `--fsize-mb`). Each
request is **lowered to the hard limit the probe itself inherited**, because
`setrlimit` above that limit raises, and a raise inside `preexec_fn` reaches the
caller as `SubprocessError: Exception occurred in preexec_fn` — no limit named
and no value, which reads as a broken probe rather than as a tight `ulimit`.

The clamp is reported rather than silent. Every `--json` result carries:

```json
"limits": {"mem_mb": 976, "mem_mb_requested": 2048, "cpu_seconds": 30,
           "fsize_mb": 64, "fsize_mb_requested": 64,
           "clamped_to_inherited_rlimit": true}
```

Read it before trusting a `rejected_in_traversal` on a file whose defect is an
allocation amplification: under a lowered cap, "the library refused it" and "the
allocation hit your `ulimit`" look identical from outside. An ASAN build takes
no `RLIMIT_AS` at all (the shadow map needs terabytes of address space) and is
bounded by `hard_rss_limit_mb`, which follows the clamped value.
