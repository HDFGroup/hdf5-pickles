# h5policy

`h5policy` is a GNU poke policy workbench for HDF5 metadata preflight. It parses
HDF5 bytes independently of `libhdf5`, validates the metadata it can reach, applies
a security profile, and emits a stable JSON decision.

The tool is intentionally a metadata-only boundary:

- no libhdf5 calls
- no plugin loading
- no decompression
- no external file opens
- no repair
- no writes
- no application deserialization

That boundary is the point. `h5policy` is meant to answer "what would this file
make an HDF5 stack do?" before application code, filters, VFDs, external links,
or payload decoders get a chance to run.

## Quick Start

Run from the repository root:

```sh
./h5policy/tools/h5policy --profile untrusted-strict --json file.h5
./h5policy/tools/h5policy --profile trusted-fast --json file.h5
./h5policy/tools/h5policy --profile legacy --json file.h5
./h5policy/tools/h5policy --profile forensic --json --continue-after-corruption file.h5
```

Useful mode flags:

- `--strict` / `--non-strict` force GNU poke strict or non-strict mapping.
- `--continue-after-corruption` keeps walking after the first corruption finding
  so diagnostics include every reachable issue.
- `--json` prints the machine-readable result.

## Decisions

Exit codes are part of the interface:

```text
0   accept
1   accept_with_warnings
2   reject_corrupt
3   reject_policy
4   reject_resource
5   unsupported_coverage_gap
70  internal_error
```

`unsupported_coverage_gap` is a bounded answer, not a silent accept. It means the
file reached a recognized HDF5 feature that is not yet decoded deeply enough for
the selected policy.

JSON output includes:

- `decision`: the final classification.
- `findings`: stable finding codes and locations.
- `features`: security-relevant constructs such as external links, external
  storage, VDS, dynamic filters, unknown messages, maximum rank, and maximum
  logical dataset bytes.
- `metrics`: traversal and accounting counters used by profile budgets.

## Profiles

Profiles differ in feature policy and resource budgets, not in whether corrupt
metadata is rejected. A truncated or checksum-bad file is corrupt under every
profile.

| Profile            | Mapping     | Resource budgets | Feature policy                         |
| ------------------ | ----------- | ---------------- | -------------------------------------- |
| `legacy`           | strict      | unlimited        | all features allowed                   |
| `trusted-fast`     | strict      | generous         | external refs / VDS / filters allowed  |
| `untrusted-strict` | strict      | tight            | denied by default                      |
| `forensic`         | non-strict  | unlimited        | never follows refs; reports anomalies  |

Examples:

- An external-link file is rejected by `untrusted-strict`, but accepted by
  `trusted-fast` and `legacy`.
- A very large logical dataset can be rejected by `untrusted-strict` resource
  budgets while remaining structurally valid.
- `forensic` favors complete reporting over early exit, but still never follows
  external references or decodes payload data.

## Validation Coverage

Current coverage includes:

- HDF5 superblocks, EOF/base-address geometry, and v2/v3 superblock checksums.
- Object headers, continuation chunks, object-header checksums, message prefix
  bounds, and reachable object traversal with visited sets.
- Dataspace, datatype, layout, filter pipeline, fill value, link, attribute,
  free-space info, and metadata cache image messages.
- Compact hard links, dense link storage, dense attribute storage, old-style
  group metadata, and chunk-index metadata.
- Logical dataset byte accounting kept separate from raw storage accounting, so
  datatype semantics can be compared against `libhdf5` while layout checks still
  use on-disk storage size.

Checksum coverage includes the HDF5 Jenkins checksums used by:

- v2/v3 superblocks
- v2 object headers and continuation chunks
- chunk-index metadata
- dense metadata fractal heaps: `FRHP`, `FHDB`, `FHIB`
- dense metadata v2 B-trees: `BTHD`, `BTLF`, `BTIN`

## Companion Tools

- [`tools/h5policy`](tools/h5policy): the policy oracle.
- [`tools/h5policy-diff`](tools/h5policy-diff): compares h5policy decisions and
  extracted features with `libhdf5` via `h5py` and optional HDF5 command-line
  tools.
- [`tools/h5policy-fuzz`](tools/h5policy-fuzz): structure-aware fuzzer for
  h5policy, using `libhdf5` via `h5py` as the oracle.
- [`tools/h5policy-crashfuzz`](tools/h5policy-crashfuzz): mutates files against
  installed HDF5 tools and triages crashers with h5policy.
- [`tools/h5policy-fuzzlib`](tools/h5policy-fuzzlib): shared fuzzing engine
  (mutation strategies, seed loading, guided corpus) imported by both fuzzers.
- [`tools/h5policy-gencorpus`](tools/h5policy-gencorpus): regenerates the valid,
  malformed, policy, resource, coverage, and CVE regression fixtures.

See [`tests/README.md`](tests/README.md) for the corpus, differential harness,
and fuzzing workflow.
