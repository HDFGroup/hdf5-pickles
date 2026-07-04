# H5Lens: HDF5 Pickles and Policy Workbench

`H5Lens` is a machine-readable description of HDF5 on-disk metadata using
[GNU poke](https://www.jemarch.net/poke/) pickles. It is both a format
exploration kit and the home of `h5policy`, an independent metadata preflight
oracle for hostile or untrusted HDF5 files.

## What's Here

- [`pickles/`](pickles/) contains the reusable HDF5 format definitions loaded by
  GNU poke.
- [`h5policy/`](h5policy/) contains the policy oracle, focused validators,
  security profiles, regression corpus, differential harness, and fuzzing tools.
- [`tools/`](tools/) contains repository-level helpers such as the marker scanner
  and interactive `h5explain` workflow.
- [`docs/`](docs/) contains YAML format notes and generated Markdown reference
  pages.
- [`emacs/`](emacs/) contains an Emacs front end for inspecting HDF5 files
  through GNU poke.
- [`examples/`](examples/) contains poke scripts for generating and inspecting
  HDF5 structures.
- [`MARKERS.md`](MARKERS.md), [`TOOLS.md`](TOOLS.md), and
  [`TUTORIAL.md`](TUTORIAL.md) explain the format markers, helper tools, and a
  hands-on exploration path.

## Quick Start

Run `h5policy` against an HDF5 file:

```sh
./h5policy/tools/h5policy --profile untrusted-strict --json file.h5
```

Try the regression suite:

```sh
cd h5policy/tests
./run.sh
```

Build the marker scanner and generated format docs:

```sh
cmake -S . -B build
cmake --build build
cmake --build build --target docs
```

Explore the sample file interactively:

```sh
POKE_LOAD_PATH=$PWD/pickles poke file.h5
```

See [`TUTORIAL.md`](TUTORIAL.md) for a guided GNU poke walkthrough.

## h5policy In Under A Minute

`h5policy` maps HDF5 metadata with GNU poke, validates the metadata it can reach,
applies a selected security profile, and emits a JSON decision with stable exit
codes. It is intentionally metadata-only: it does not call `libhdf5`, load
plugins, decompress data, open external files, repair inputs, write files, or
deserialize application payloads.

Use [`h5policy/README.md`](h5policy/README.md) for profile behavior, exit codes,
coverage, checksum notes, and CLI examples. Use
[`h5policy/tests/README.md`](h5policy/tests/README.md) for the corpus,
differential harness, and fuzzing workflow.

## Acknowledgments

> This material is based upon work supported by the U.S. National Science
> Foundation under Federal Award No. 2534078. Any opinions, findings, and
> conclusions or recommendations expressed in this material are those of the
> author(s) and do not necessarily reflect the views of the National Science
> Foundation.
