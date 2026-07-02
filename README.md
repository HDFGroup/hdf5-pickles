# SHAPE5: Specification for HDF5 Analysis, Parsing, and Encoding

`SHAPE5` is a machine-readable specification of the HDF5 file format using [GNU poke](https://www.jemarch.net/poke/) pickles.

The goal is to describe HDF5 on-disk structures as executable binary format definitions that can be loaded in GNU poke to inspect, validate, and reason about HDF5 files.

This repository is a work in progress. The current pickles focus on core HDF5 metadata structures, including the superblock, B-trees, object headers, and related messages.

## Quick Start

The pickles are meant to be loaded by GNU poke from the repository root:

```sh
POKE_LOAD_PATH=$PWD/pickles poke file.h5
```

For a guided walk through the sample file, see [`TUTORIAL.md`](TUTORIAL.md). To use the interactive explorer instead of the raw poke REPL:

```sh
./tools/h5explain file.h5
```

The C++ marker scanner and generated documentation targets are built with CMake:

```sh
cmake -S . -B build
cmake --build build
cmake --build build --target docs
cmake --build build --target docs-check
```

The Emacs front end can be byte-compiled and tested with:

```sh
cmake --build build --target emacs-check
```

That target requires Emacs 30+, GNU poke on `PATH`, `h5py`, and `numpy`.

## Repository Layout

### Core Pickles

- [`pickles/common.pk`](pickles/common.pk): shared helpers and common definitions
- [`pickles/superblock.pk`](pickles/superblock.pk): HDF5 superblock definitions
- [`pickles/messages.pk`](pickles/messages.pk): object header message definitions
- [`pickles/ohdr.pk`](pickles/ohdr.pk): object header definitions
- [`pickles/btree.pk`](pickles/btree.pk): umbrella loader for version 1 and version 2 B-tree definitions
- [`pickles/v1_btree.pk`](pickles/v1_btree.pk): version 1 B-tree and symbol table node definitions
- [`pickles/v2_btree.pk`](pickles/v2_btree.pk): version 2 B-tree definitions
- [`pickles/farray.pk`](pickles/farray.pk): fixed array chunk index definitions
- [`pickles/earray.pk`](pickles/earray.pk): extensible array chunk index definitions
- [`pickles/fheap.pk`](pickles/fheap.pk): fractal heap header, indirect block, direct block, and heap ID definitions
- [`pickles/lheap.pk`](pickles/lheap.pk): local heap definitions
- [`pickles/gheap.pk`](pickles/gheap.pk): global heap definitions
- [`pickles/fsm.pk`](pickles/fsm.pk): free-space manager header and section information definitions
- [`pickles/sohm.pk`](pickles/sohm.pk): shared object header message table and list definitions
- [`pickles/drv_info.pk`](pickles/drv_info.pk): driver information block definitions
- [`pickles/dspace_enc.pk`](pickles/dspace_enc.pk): dataspace encoding definitions
- [`pickles/ref_enc.pk`](pickles/ref_enc.pk): object and dataset region reference encoding definitions
- [`pickles/vds.pk`](pickles/vds.pk): virtual dataset global heap block definitions
- [`pickles/lookup3.pk`](pickles/lookup3.pk): implementation of the lookup3 hash function used for checksums
- [`pickles/construct.pk`](pickles/construct.pk): helpers for constructing HDF5 metadata in memory
- [`pickles/h5explain.pk`](pickles/h5explain.pk): command layer loaded by the interactive explorer
- [`pickles/hdf5_poke_emacs.pk`](pickles/hdf5_poke_emacs.pk): machine-readable protocol helpers for the Emacs front end

### Documentation

- [`MARKERS.md`](MARKERS.md): list of known on-disk markers in HDF5 and Onion files
- [`TOOLS.md`](TOOLS.md): documentation for tools included in this repository, including the marker scanner and interactive explorer
- [`TUTORIAL.md`](TUTORIAL.md): step-by-step tutorial for using the pickles and tools in this repository
- [`docs/README.md`](docs/README.md): generated documentation workflow
- [`docs/spec/`](docs/spec/): prose sidecars for generated pickle documentation
- [`docs/generated/`](docs/generated/): generated Markdown documentation for selected pickles

### Emacs Front End

- [`emacs/hdf5-poke.el`](emacs/hdf5-poke.el): public entry point for the Emacs 30+ inspector
- [`emacs/hdf5-poke-core.el`](emacs/hdf5-poke-core.el): process, protocol, request tracking, and path helper layer
- [`emacs/hdf5-poke-ui.el`](emacs/hdf5-poke-ui.el): inspector modes, keymaps, renderers, tree browsing, and interactive commands
- [`emacs/README.md`](emacs/README.md): setup, commands, and test instructions for the Emacs module

### Tools

- [`tools/h5explain`](tools/h5explain): interactive HDF5 byte-level explorer built on GNU poke
- [`src/h5markers.cpp`](src/h5markers.cpp): C++ marker scanner for HDF5 and Onion on-disk signatures
- [`tools/pkdoc.py`](tools/pkdoc.py): generator for Markdown documentation from pickle files and YAML sidecars

### Examples

- [`examples/`](examples/): example HDF5 files and GNU poke sessions demonstrating the use of the pickles and tools in this repository

### Tests

- [`tests/hdf5-poke-test.el`](tests/hdf5-poke-test.el): protocol parser and renderer unit tests
- [`tests/hdf5-poke-process-test.el`](tests/hdf5-poke-process-test.el): process-level Emacs/GNU poke smoke tests
- [`tests/fixtures/`](tests/fixtures/): fixture generator and notes for build-tree HDF5 test files covering dense groups, old-style symbol tables, chunk-index families, and nested datatypes

## Acknowledgments

> This material is based upon work supported by the U.S. National Science Foundation under Federal Award No. 2534078. Any opinions, findings, and conclusions or recommendations expressed in this material are those of the author(s) and do not necessarily reflect the views of the National Science Foundation.
