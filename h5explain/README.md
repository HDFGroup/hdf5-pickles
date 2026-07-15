# h5explain

`h5explain` is an interactive GNU poke front end for byte-level HDF5 metadata
exploration.  It opens an HDF5 file, loads the reusable format pickles from the
repository, and installs navigation commands for moving through superblocks,
object headers, links, B-trees, heaps, and chunk indexes.

Run from the repository root:

```sh
./tools/h5explain [OPTIONS] FILE [OFFSET]
./tools/h5explain --help
```

`OFFSET` may be decimal or hexadecimal, for example `48` or `0x30`.  Without an
offset, the explorer starts at the HDF5 superblock.

## Scripting

`h5explain` runs a batch session when commands arrive from `--command` options,
or, when none are given, from a piped standard input.  Either source suppresses
the banner and exits instead of entering the REPL, so sessions stay diffable:

```sh
printf 'root\nls\n' | ./tools/h5explain file.h5
./tools/h5explain -c root -c 'cd ("group_a")' -c msgs file.h5
```

Batch mode exits with poke's status.  poke reports an unhandled exception on
stderr and keeps going, so scripted callers should assert on output rather than
on the exit status alone.

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
explain
explain (N)
explain_msg (N)
info
msgs
cur
ls
links
traverse
dump
h5dump
```

Use `msgs` to list object-header messages, then `explain (N)` or
`explain_msg (N)` to explain message `N` in the current object header.  Type
`help` at the prompt for the full command descriptions.

## Tests

```sh
./tests/run.sh
```

The runner regenerates the fixtures in `tests/fixtures` with `h5py`, then drives
`h5explain` in batch mode over them.  The fixtures are build artifacts; the
tracked specification is `tests/test_h5explain.py`.  Tests never assert absolute
file offsets, which depend on the libhdf5 that wrote the fixture — where an
address is needed they scan for the primitive's signature instead.

## Layout

- [`tools/h5explain`](tools/h5explain) is the shell driver.
- [`pickles/h5explain.pk`](pickles/h5explain.pk) is the interactive command
  layer.
- [`tests/`](tests/) contains the fixture generator and the regression suite.
- [`../pickles/`](../pickles/) contains the shared HDF5 format definitions that
  `h5explain` loads.
- [`../tools/h5explain`](../tools/h5explain) is the top-level symlink entry
  point.

`traverse` is the only command that recursively walks chunk indexes.  Ordinary
navigation and `info` map the current primitive only, so large chunk indexes are
not traversed accidentally.
