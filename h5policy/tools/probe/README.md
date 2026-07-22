# Exact-build libhdf5 probe

`h5policy-probe` runs a **selected** libhdf5 build against one file and reports,
as JSON, what that exact build did and which OS-observable activation events
occurred. It is the release-gate answer to two questions the other harnesses
cannot pin down:

- **Which build?** `h5policy-diff` observes whatever libhdf5 h5py bundles;
  `h5policy-crashfuzz` drives whatever tools are on `PATH`. Here `--hdf5-bindir`
  names the build under test, the probe is compiled against it, and every result
  carries that build's version, linked-library path, configuration, and
  `libhdf5.settings` hash.
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
