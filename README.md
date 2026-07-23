# H5Lens: HDF5 Pickles and Policy Workbench

`H5Lens` is a machine-readable description of HDF5 on-disk metadata using
[GNU poke](https://www.jemarch.net/poke/) pickles. It is both a format
exploration kit and the home of `h5policy`, an independent metadata preflight
oracle for hostile or untrusted HDF5 files.  It also includes the early
`h5patch` repair planner for proposing and applying conservative metadata
repairs.

## What's Here

- [`pickles/`](pickles/) contains the reusable HDF5 format definitions loaded by
  GNU poke. Its `h5_format_constants.pk` module is the canonical source for
  literals shared by declarative mappings and independent validators.
- [`h5policy/`](h5policy/) contains the policy oracle, focused validators,
  security profiles, regression corpus, differential harness, and fuzzing tools.
- [`h5patch/`](h5patch/) contains the experimental metadata repair planner,
  JSON patch-plan format, apply workflow, and repair tests.
- [`h5explain/`](h5explain/) contains the interactive GNU poke explorer for
  byte-level HDF5 metadata navigation.
- [`src/`](src/) contains the marker scanner implementation.
- [`tools/`](tools/) collects top-level command symlinks and repository helper
  scripts such as the documentation generator.
- [`docs/`](docs/) contains YAML format notes and generated Markdown reference
  pages, plus a [tool relationship overview](docs/tool-overview.md).
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
./tools/h5policy --profile untrusted-strict file.h5
```

Run every regression suite through CTest:

```sh
cmake -S . -B build
ctest --test-dir build --output-on-failure -j4
```

Create a what-if metadata repair plan:

```sh
./tools/h5patch plan damaged.h5 -o repair.plan.json
./tools/h5patch explain repair.plan.json
```

Build the marker scanner and generated format docs:

```sh
cmake -S . -B build
cmake --build build
cmake --build build --target docs
```

Explore the sample file interactively:

```sh
./tools/h5explain file.h5
```

See [`h5explain/README.md`](h5explain/README.md) for interactive navigation
commands and [`TUTORIAL.md`](TUTORIAL.md) for a guided GNU poke walkthrough.

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

## h5patch In Under A Minute

`h5patch` plans byte-level repairs for damaged HDF5 metadata, applies only an
approved JSON plan, writes an audit log, and verifies the result with
`h5policy`. Planning is a what-if operation: it does not modify the input file.

The current catalog contains `12` evidence-gated repair classes. At a glance,
they cover:

- file bootstrap and superblock repairs: signature, base address, consistency
  flags, and checksums;
- reachable object-header repairs: v1 message counts, v2 checksums, v4
  chunk-layout element size, and typed scale-offset/N-bit filter parameters;
- counted or indexed metadata repairs: free-space section totals, symbol-table
  node counts, and depth-0 v2 B-tree total-record counts; and
- trailing-checksum repairs for reached free-space, v2 B-tree,
  extensible-array, and shared-message metadata.

This overview is intentionally non-exhaustive. The authoritative and exhaustive
[repair catalog](h5patch/README.md#repair-catalog) documents each repair,
its evidence requirements, atomic checksum handling, and fail-closed cases.

## Acknowledgments

> This material is based upon work supported by the U.S. National Science
> Foundation under Federal Award No. 2534078. Any opinions, findings, and
> conclusions or recommendations expressed in this material are those of the
> author(s) and do not necessarily reflect the views of the National Science
> Foundation.
