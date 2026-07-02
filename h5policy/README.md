# h5policy

`h5policy` is a GNU poke policy workbench for HDF5 metadata preflight.

This overlay intentionally freezes the Phase 0 boundary:

- no libhdf5 calls
- no plugin loading
- no decompression
- no external file opens
- no repair
- no writes
- no application deserialization

Phase 1 validates the superblock and the root object header. It opens the target
file read-only, maps metadata with the selected profile, checks basic file
geometry and checksums, scans root object-header message prefixes for chunk
overruns, and emits a JSON decision with stable exit codes.

Phase 2 adds bounded root object-header message validators for dataspace,
datatype, layout, filter pipeline, link, attribute, fill value, continuation,
free-space info, and metadata cache image messages.

Phase 3 walks reachable object headers through compact hard-link messages with
explicit visited sets and profile budgets for metadata bytes, object count,
object-header continuation chunks, attributes, traversal depth, and chunk-index
references. Continuation chunks are followed with loop detection. Dense link
storage, old-style group B-trees, and chunk-index roots are bounded and reported
as `unsupported_coverage_gap` until their pickle decoders are covered.

Phase 4 adds policy reporting summaries. JSON output now includes `features`
for security-relevant constructs such as external links, external storage, VDS,
dynamic filters, unknown messages, maximum rank, and maximum logical dataset
bytes, plus `metrics` for traversal/accounting counters.

Profiles implement the four HDF5 security profiles from the audit report
(main.pdf, Table 5). They differ in feature policy and resource budgets, not in
whether corruption is caught — every profile still rejects genuinely unmappable
metadata:

| Profile            | Mapping     | Resource budgets | Feature policy                         |
| ------------------ | ----------- | ---------------- | -------------------------------------- |
| `legacy`           | strict      | unlimited        | all features allowed                   |
| `trusted-fast`     | strict      | generous         | external refs / VDS / filters allowed  |
| `untrusted-strict` | strict      | tight            | denied (default)                       |
| `forensic`         | non-strict  | unlimited        | never follows refs; reports anomalies  |

For example, an external-link file or a 128 GiB logical dataset is rejected
under `untrusted-strict` but accepted under `trusted-fast` and `legacy`; a
truncated file is `reject_corrupt` under all four.

Run:

```sh
./h5policy/tools/h5policy --profile untrusted-strict --json file.h5
./h5policy/tools/h5policy --profile trusted-fast --json file.h5
./h5policy/tools/h5policy --profile legacy --json file.h5
./h5policy/tools/h5policy --profile forensic --json --continue-after-corruption file.h5
```

Exit codes:

```text
0  accept
1  accept_with_warnings
2  reject_corrupt
3  reject_policy
4  reject_resource
5  unsupported_coverage_gap
70 internal_error
```
