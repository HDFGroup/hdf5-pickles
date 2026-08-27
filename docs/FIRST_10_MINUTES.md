# H5Lens in 10 Minutes

This is the shortest useful route through H5Lens: get the toolchain, inspect a
known HDF5 file, run the metadata policy, and understand one finding. Commands
run from the repository root.

## 1. Get a working toolchain

The supported installation path is the
[development container](../.devcontainer/README.md). In GitHub Codespaces,
open the repository in a Codespace; locally, use **Dev Containers: Reopen in
Container**. It installs GNU poke, HDF5 tools, Python dependencies, and the
repository's command-line tools together.

For a local installation, provide GNU poke, a C++17 compiler, Python with
PyYAML, CMake, and the HDF5 command tools, then configure the project:

```sh
cmake -S . -B build
cmake --build build --parallel
```

`h5policy` itself is an interpreted GNU poke tool, so it is ready once GNU poke
and the repository are available; building also gives you `build/h5markers`.

## 2. Inspect a file without decoding its payload

Start with the tracked example:

```sh
./tools/h5explain examples/file.h5
```

At the prompt, follow the root link to the sample dataset:

```h5explain
root
ls
cd ("DirectChunkData")
msgs
```

`msgs` identifies the dataset's dataspace, datatype, filters, and layout. For
a reproducible non-interactive inspection, run:

```sh
./tools/h5explain -c root -c ls examples/file.h5
```

The output names `DirectChunkData`; that path is the bridge between the byte
layout and the object you are about to preflight.

## 3. Preflight the same file

Run the untrusted-file profile before asking an HDF5 consumer to read it:

```sh
./tools/h5policy --profile untrusted-strict examples/file.h5
```

The command emits JSON and, for this example, exits `1` with
`"decision": "accept_with_warnings"`. Exit `1` is a valid policy verdict, not
a tool failure: see the [decision and exit-code reference](../h5policy/README.md#decisions).

## 4. Interpret the finding

The example reports `H5_ADVISORY_DECODE_FILTER` for
`/DirectChunkData`. It says the dataset declares the deflate/gzip filter, so a
consumer must decompress untrusted data to read values. `h5policy` has not
decompressed anything: it reports that activation boundary from metadata alone.

For another file, read these fields in order:

1. `decision` tells you whether the selected profile accepted, warned, or
   rejected the reachable metadata.
2. `analysis.complete` and `analysis.walk_completed` tell you whether the
   reachable walk finished.
3. `findings[].code`, `object`, and `offset` identify what needs investigation.

Use `--continue-after-rejection` with the `forensic` profile when you need a
broader diagnostic report; it does not weaken the acceptance decision.

## Continue from here

- Follow the [H5Lens tutorial](TUTORIAL.md) for a guided metadata walk.
- Read the [`h5policy` guide](../h5policy/README.md) for profiles, decisions,
  output fields, and safety boundaries.
- Browse the generated [HDF5 format reference](generated/README.md) when you
  need an on-disk structure.
- Use the [tool guide](TOOLS.md) for mutation, differential, repair, and CVE
  case workflows.
