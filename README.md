# SHAPE5: Specification for HDF5 Analysis, Parsing, and Encoding

`SHAPE5` is a machine-readable specification of the HDF5 file format using [GNU poke](https://www.jemarch.net/poke/) pickles.

The goal is to describe HDF5 on-disk structures as executable binary format definitions that can be loaded in GNU poke to inspect, validate, and reason about HDF5 files.

This repository is a work in progress. The current pickles focus on core HDF5 metadata structures, including the superblock, B-trees, object headers, and related messages.

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
- [`pickles/lookup3.pk`](pickles/lookup3.pk): implementation of the lookup3 hash function used for checksums

### Documentation

- [`MARKERS.md`](MARKERS.md): list of known on-disk markers in HDF5 and Onion files
- [`TOOLS.md`](TOOLS.md): documentation for tools included in this repository, including the marker scanner and interactive explorer
- [`TUTORIAL.md`](TUTORIAL.md): step-by-step tutorial for using the pickles and tools in this repository

### Examples

- [`examples/`](examples/): example HDF5 files and GNU poke sessions demonstrating the use of the pickles and tools in this repository

## Acknowledgments

> This material is based upon work supported by the U.S. National Science Foundation under Federal Award No. 2534078. Any opinions, findings, and conclusions or recommendations expressed in this material are those of the author(s) and do not necessarily reflect the views of the National Science Foundation.
