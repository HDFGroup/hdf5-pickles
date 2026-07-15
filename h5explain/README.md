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

Findings that h5policy reports at offset 0 are not treated as bytes at offset 0.
That offset is its "no location" placeholder — used by the finding-limit marker,
the walk-budget and mapping-failure findings, and any finding whose real
location was not printable — and most files put the superblock there, which
would otherwise collect all of them. Those findings name their scope in the
object field instead, and a genuine finding at offset 0 (a bad superblock
signature, object `superblock`) is matched by object path.

When nothing bears on the cursor, `check` says which of five things it means:

- **reached** — the walk read this structure and found nothing wrong with it.
- **not reached** — the walk completed without ever coming here, so nothing
  vouches for these bytes. h5policy only vets reachable metadata.
- **not recorded** — h5policy accounts for extensible-array secondary and data
  blocks from the index header rather than walking them, so the record cannot
  speak to them either way. Only those two kinds land here.
- **stopped early** — the walk halted (corruption under a profile that does not
  continue, or a resource budget), so absence proves nothing. The `forensic`
  profile keeps walking past corruption and restores the distinction.
- **record full** — the reachability record hit its ceiling, so absence proves
  nothing.

The answers come from h5policy's reachability record: the structures its walk
actually read, with the kind it read each as. That record is why the superblock
gets no special case — it is reached when the walk located it, and a file whose
signature was never found has no located superblock, which is exactly where
"reached by definition" would have lied.

Because the record carries the kind, `check` also reports when the two readings
disagree — h5policy read a B-tree header where the cursor decoded a local heap,
say. Two structures cannot share those bytes, so one reading is wrong, and that
is worth knowing on its own.

h5policy stores at most 4096 findings per run. Past that cap `check` stops
claiming there are none on the cursor, because a finding on those very bytes may
have been dropped rather than never raised; it says so and reports reachability
separately.

### When the policy pickles load

They roughly double startup (~0.3s), so they load only when the session may use
them. An interactive session always loads them: the user can type `check` at any
prompt. A batch session has all of its commands up front, and reaching a policy
command means naming it, so the commands decide:

```sh
h5explain -c root -c ls file.h5        # no policy command -> not loaded, ~0.35s
h5explain -c root -c check file.h5     # names check -> loaded, ~0.59s
h5explain --no-policy -c ls file.h5    # never load
h5explain --policy -c 'load "mine.pk"' file.h5   # force, e.g. when a script
                                                 # reaches check indirectly
```

GNU poke does not allow `load` inside a function, so `check` cannot pull its own
implementation in on demand; the decision has to be made before poke starts.
When the pickles are absent, the policy commands say so and name the flag rather
than failing as undefined variables.

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

The same holds at startup: a file whose superblock does not decode still opens.
`h5explain` reports the failure, notes that the B-tree constants are unset, and
leaves the cursor on the superblock, so `dump`, `check`, and manual navigation
all still work — a superblock that does not parse is exactly the case worth
exploring.

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
