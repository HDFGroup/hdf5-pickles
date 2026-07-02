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
file read-only, maps metadata with the selected profile, checks basic file geometry
and checksums, scans root object-header message prefixes for chunk overruns, and
emits a JSON decision with stable exit codes.

Phase 2 adds bounded root object-header message validators for dataspace,
datatype, layout, filter pipeline, link, attribute, fill value, continuation,
free-space info, and metadata cache image messages. It still does not traverse the
object graph; child object headers, dense heaps, B-trees, and chunk indexes are
reserved for Phase 3.

Run:

```sh
./h5policy/tools/h5policy --profile untrusted-strict --json file.h5
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
