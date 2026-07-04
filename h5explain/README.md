# h5explain

`h5explain` is an interactive GNU poke front end for byte-level HDF5 metadata
exploration.  It opens an HDF5 file, loads the reusable format pickles from the
repository, and installs navigation commands for moving through superblocks,
object headers, links, B-trees, heaps, and chunk indexes.

Run from the repository root:

```sh
./tools/h5explain [-n|--non-strict] FILE [OFFSET]
./tools/h5explain --help
```

`OFFSET` may be decimal or hexadecimal, for example `48` or `0x30`.  Without an
offset, the explorer starts at the HDF5 superblock.

## Commands

Navigation:

```text
root
h5super
cd ("NAME")
go (OFF#B)
go (OFF#B, "PATH")
gos ("0xADDR")
gos ("0xADDR", "PATH")
back
pwd
```

Inspection:

```text
info
msgs
cur
ls
links
traverse
dump
h5dump
```

Type `help` at the prompt for the full command descriptions.

## Layout

- [`tools/h5explain`](tools/h5explain) is the shell driver.
- [`pickles/h5explain.pk`](pickles/h5explain.pk) is the interactive command
  layer.
- [`../pickles/`](../pickles/) contains the shared HDF5 format definitions that
  `h5explain` loads.
- [`../tools/h5explain`](../tools/h5explain) is the top-level symlink entry
  point.

`traverse` is the only command that recursively walks chunk indexes.  Ordinary
navigation and `info` map the current primitive only, so large chunk indexes are
not traversed accidentally.
