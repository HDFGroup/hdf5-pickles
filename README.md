# SHAPE5: HDF5 Pickles and Policy Workbench

`SHAPE5` is a machine-readable specification of the HDF5 file format using
[GNU poke](https://www.jemarch.net/poke/) pickles.

The repository has two closely related goals:

- describe HDF5 on-disk structures as executable binary format definitions that
  can be loaded in GNU poke for inspection and exploration;
- provide `h5policy`, an independent HDF5 metadata preflight oracle for hostile
  or untrusted files.

`h5policy` is intentionally a metadata-only boundary. It does not call libhdf5,
load plugins, decompress data, open external files, repair inputs, write files,
or deserialize application payloads. It maps HDF5 bytes with GNU poke, validates
the metadata it can reach, applies a selected security profile, and emits a JSON
decision with stable exit codes.

## Quick Start

Run `h5policy` against an HDF5 file:

```sh
./h5policy/tools/h5policy --profile untrusted-strict --json file.h5
./h5policy/tools/h5policy --profile forensic --json --continue-after-corruption file.h5
```

Run the deterministic regression suite:

```sh
cd h5policy/tests
./run.sh
```

Run the differential harness against a file or directory of HDF5 files:

```sh
./h5policy/tools/h5policy-diff file.h5
./h5policy/tools/h5policy-diff --dir /path/to/corpus
```

Build the marker scanner and generated format docs:

```sh
cmake -S . -B build
cmake --build build
cmake --build build --target docs
```

## h5policy

`h5policy` classifies each input as one of:

```text
0  accept
1  accept_with_warnings
2  reject_corrupt
3  reject_policy
4  reject_resource
5  unsupported_coverage_gap
70 internal_error
```

Profiles differ in feature policy and resource budgets, not in whether corrupt
metadata is rejected:

| Profile            | Mapping     | Resource budgets | Feature policy                         |
| ------------------ | ----------- | ---------------- | -------------------------------------- |
| `legacy`           | strict      | unlimited        | all features allowed                   |
| `trusted-fast`     | strict      | generous         | external refs / VDS / filters allowed  |
| `untrusted-strict` | strict      | tight            | denied by default                      |
| `forensic`         | non-strict  | unlimited        | never follows refs; reports anomalies  |

Current validation coverage includes superblocks, object headers and
continuation chunks, root and reachable object headers, dataspaces, datatypes,
layouts, filter pipelines, fill values, links, attributes, free-space info,
metadata cache image messages, old-style group metadata, chunk indexes, and dense
link/attribute storage.

Checksum coverage includes the HDF5 Jenkins checksums used by v2/v3 superblocks,
v2 object headers and continuations, chunk-index metadata, and dense metadata:
fractal heap headers/direct blocks/indirect blocks (`FRHP`, `FHDB`, `FHIB`) plus
v2 B-tree headers/leaves/internal nodes (`BTHD`, `BTLF`, `BTIN`).

See [h5policy/README.md](h5policy/README.md) for the policy profile details and
CLI examples.

## Validation Loop

The `h5policy/tests` tree is a generated regression corpus with tracked
expectations. `./run.sh` regenerates fixtures, runs GNU poke unit checks, checks
every expected case, and then runs the differential harness against libhdf5 via
`h5py` with optional `h5dump`/`h5debug` signals.

Useful tools:

- [`h5policy/tools/h5policy`](h5policy/tools/h5policy): the policy oracle.
- [`h5policy/tools/h5policy-diff`](h5policy/tools/h5policy-diff): compares
  h5policy decisions and extracted features with libhdf5.
- [`h5policy/tools/h5policy-fuzz`](h5policy/tools/h5policy-fuzz): structure-aware
  fuzzer that mutates seeds, repairs selected checksums, and promotes soundness
  gaps into permanent fixtures.
- [`h5policy/tools/h5policy-gencorpus`](h5policy/tools/h5policy-gencorpus):
  regenerates valid, malformed, policy, resource, coverage, and CVE fixtures.

See [h5policy/tests/README.md](h5policy/tests/README.md) for the corpus,
differential, and fuzzing workflow.

## Core Pickles

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

> This material is based upon work supported by the U.S. National Science
> Foundation under Federal Award No. 2534078. Any opinions, findings, and
> conclusions or recommendations expressed in this material are those of the
> author(s) and do not necessarily reflect the views of the National Science
> Foundation.
