# H5Lens Tutorial

This tutorial follows HDF5 metadata from the file superblock to a dataset and
its chunk index with `h5explain`. Along the way, it shows how the independent
`h5policy` oracle adds security context without reading dataset payloads.

The commands use the tracked `examples/file.h5` sample and assume you start from
the repository root. The [development container](../.devcontainer/README.md)
provides the complete toolchain.

## 1. Open the sample

Start the explorer:

```sh
./tools/h5explain examples/file.h5
```

`h5explain` opens at the HDF5 superblock. Ask where you are and inspect the
decoded structure:

```h5explain
pwd
info
```

The sample has a version 2 superblock at byte offset `0`. Its
`root_obj_addr_raw` field points to the root object header. `h5explain` follows
that relationship for you, so you do not need to convert the address bytes by
hand.

## 2. Find the dataset

Move to the root object header and list its hard links:

```h5explain
root
ls
```

The output includes:

```text
current: object header at 48UL#B [/]
Hard links:
  DirectChunkData -> 195UL#B
```

Follow the link by name and confirm the new location:

```h5explain
cd ("DirectChunkData")
pwd
```

Structural navigation gives the address a trustworthy path label:
`/DirectChunkData`. This is preferable to jumping directly to byte `195`,
because the relationship from the root corroborates what those bytes represent.

## 3. Explain the storage layout

List the dataset's object-header messages:

```h5explain
msgs
```

The messages describe its dataspace, datatype, fill value, filter pipeline, and
storage layout. Message `4` is the data-layout message; ask for a focused
explanation:

```h5explain
explain (4)
```

Look for these facts:

```text
layout_class=2UB (chunked)
chunk_index_addr=479UL#B
stored_element_size=4
```

The dataset is chunked, and its chunk records are indexed by metadata beginning
at byte offset `479`. The explanation converts the encoded address and supplies
the layout context needed to decode that index.

## 4. Add the policy view

Run the metadata preflight and show findings that bear on the current dataset:

```h5explain
check
```

For this sample, the strict profile accepts the metadata with a warning:

```text
h5policy: accept_with_warnings (profile untrusted_strict)
H5_ADVISORY_DECODE_FILTER
```

The dataset declares the deflate filter. Reading its values would require a
consumer to decompress untrusted payload data; `h5policy` reports that
activation boundary without decompressing the data itself.

`check` analyzes the whole reachable metadata graph and then filters its
findings to the cursor. Use `check_all` for the complete report or
`profile ("forensic")` when investigating a corrupt file past its first
rejection.

## 5. Follow the chunk index

Jump to the address reported by the layout explanation and inspect the node:

```h5explain
go (479#B)
info
```

`h5explain` recognizes a version 1 B-tree node with four records. It has already
set the raw-chunk key dimensionality from the dataset layout, so the offsets and
stored chunk sizes decode correctly.

Return to the dataset using navigation history:

```h5explain
back
pwd
```

The cursor returns to `/DirectChunkData`. Use `traverse` when you want to walk a
complete chunk index; ordinary navigation and `info` decode only the current
primitive.

## 6. Reproduce the path in batch mode

The same exploration can run without an interactive prompt:

```sh
./tools/h5explain \
  -c root \
  -c ls \
  -c 'cd ("DirectChunkData")' \
  -c 'explain (4)' \
  -c check \
  -c 'go (479#B)' \
  -c info \
  examples/file.h5
```

Batch sessions make investigations repeatable and easy to attach to a case
record. Assert on meaningful output such as object paths, message types, and
finding codes rather than relying only on the process exit status.

## Next steps

- Use the [`h5explain` guide](../h5explain/README.md) as the complete command
  reference.
- Continue with the [low-level GNU poke tutorial](POKE_TUTORIAL.md) to map the
  same structures directly and verify their checksums.
- Read [Writing HDF5 with GNU poke](POKE_CONSTRUCTION.md) before experimenting
  with write-through mappings or constructing a file.
- See the [tool guide](TOOLS.md) for the policy, repair, mutation, and CVE-case
  workflows that build on the same format definitions.
