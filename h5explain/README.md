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
cd ("PATH")
go (OFF#B)
go (OFF#B, "PATH")
gos ("0xADDR")
gos ("0xADDR", "PATH")
back
pwd
```

`cd` takes a single link name, a multi-level relative path (`group_a/values`),
an absolute path (`/group_a/values`), or any of those containing `.` and `..`.
A path that is absolute or reaches upwards is resolved from the root, so it
needs a labeled starting point; a purely downward relative path is walked from
the current header and works even where `go`/`gos` parked the cursor on an
unlabeled one.  A `cd` that fails part-way leaves the cursor where it was.

`back` retraces the full location history one step at a time, not just the last
move.  `go` and `gos` refuse an offset at or past the end of the file.

## Policy checks

`check` runs the [`h5policy`](../h5policy/) oracle over the open file and reports
what bears on the cursor; `check_all` reports every finding. `profile` shows or
sets the profile they use (`untrusted_strict`, `forensic`, `trusted_fast`,
`legacy`).

```text
check
check_all
profile
profile ("forensic")
```

h5policy is a whole-file oracle: it walks metadata reachable from the
superblock, so `check` always runs the full analysis and then filters. A finding
bears on the cursor when its bytes fall inside the current primitive **or** when
it is about the object the cursor is parked on — h5policy anchors each finding
both at the offending bytes and at the object path, and the two often differ.

When nothing bears on the cursor, `check` says which of four things it means:

- **reached** — the walk went here and found nothing.
- **not reached** — the walk completed without ever coming here, so nothing
  vouches for these bytes. h5policy only vets reachable metadata.
- **not recorded** — h5policy marks visited addresses to break cycles, not to
  record coverage, so only object headers and continuations can be reported as
  reached or not. For heaps, fixed/extensible array blocks, and B-tree headers
  it says so rather than guessing.
- **stopped early** — the walk halted (corruption under a profile that does not
  continue, or a resource budget), so absence proves nothing. The `forensic`
  profile keeps walking past corruption and restores the distinction.

Loading the policy pickles costs roughly 0.2s of extra startup on every session.

## Confidence

Most HDF5 primitives start with a signature, so `h5explain` can confirm what it
is looking at.  Version 1 object headers carry none: there, `go`/`gos` guess
from the version and message count, and raw data can match that probe.  When
the kind was guessed rather than confirmed, `pwd` and `info` say so:

```text
(unlabeled) at 401UL#B (object header) (inferred: no signature)
```

Reaching the same address through `root`, `cd`, or another structural pointer
corroborates the kind, so no marker appears.  A primitive that then fails to
decode is reported as a warning naming the offset, rather than as a poke
exception.

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
- [`pickles/h5explain_check.pk`](pickles/h5explain_check.pk) adds the h5policy
  commands. It must load after `h5explain.pk`; its header explains why.
- [`tests/`](tests/) contains the fixture generator and the regression suite.
- [`../pickles/`](../pickles/) contains the shared HDF5 format definitions that
  `h5explain` loads.
- [`../tools/h5explain`](../tools/h5explain) is the top-level symlink entry
  point.

`traverse` is the only command that recursively walks chunk indexes.  Ordinary
navigation and `info` map the current primitive only, so large chunk indexes are
not traversed accidentally.
