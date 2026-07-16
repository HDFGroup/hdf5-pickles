# Tools

## Command Entry Points

The top-level `tools/` directory collects repository commands.  Most entries are
relative symlinks to the tool-owned implementations:

```text
tools/h5explain          -> ../h5explain/tools/h5explain
tools/h5patch            -> ../h5patch/tools/h5patch
tools/h5policy           -> ../h5policy/tools/h5policy
tools/h5policy-diff      -> ../h5policy/tools/h5policy-diff
tools/h5policy-fuzz      -> ../h5policy/tools/h5policy-fuzz
tools/h5policy-fuzzlib   -> ../h5policy/tools/h5policy-fuzzlib
tools/h5policy-crashfuzz -> ../h5policy/tools/h5policy-crashfuzz
tools/h5policy-gencorpus -> ../h5policy/tools/h5policy-gencorpus
```

`tools/pkdoc.py` is a repository-level helper script used by the documentation
targets.

## Marker Scanner

`h5markers` is a multithreaded file scanner for concrete on-disk markers used
by HDF5 and Onion files. It covers the published format specifications and
implementation-defined signatures used by the current HDF5 library. See
[MARKERS.md](MARKERS.md) for the complete list and its sources.

`h5markers` can be used to quickly identify the locations of these markers in large files, which can be useful for debugging, data recovery, or understanding file structure.

Build:

```bash
cmake -S . -B build
cmake --build build
```

Usage:

```bash
# List all known markers
build/h5markers --list-markers

# Scan a file with the default thread count
build/h5markers path/to/file.h5

# Scan with an explicit thread count (-j is a synonym for --threads)
build/h5markers --threads 8 path/to/file.h5.onion
build/h5markers -j 8 path/to/file.h5.onion

# Restrict the scan (and listing) to one group of markers
build/h5markers --group HDF5 path/to/file.h5
build/h5markers --group Onion --list-markers path/to/file.h5.onion

# Show usage
build/h5markers --help
```

The scanner prints one line per detected marker with the marker name and its file offset in both
hexadecimal and decimal. Progress is reported on stderr when scanning in a terminal.

For example, scanning the sample file `file.h5` in this repository produces the following output:

```text
HDF5_SIGNATURE  0x0000000000000000 (0)
OHDR            0x0000000000000030 (48)
OHDR            0x00000000000000C3 (195)
TREE            0x00000000000001DF (479)
```

## h5explain Interactive Explorer

`h5explain` starts GNU poke with the repository pickles loaded and installs a small command layer for incremental HDF5 byte-level exploration:

```sh
./tools/h5explain [OPTIONS] FILE [OFFSET]
./tools/h5explain --help
```

`OFFSET` may be decimal or hexadecimal, for example `48` or `0x30`. Without an offset, the tool starts at the HDF5 superblock.

Commands supplied with `-c`/`--command` or on a piped standard input run as a batch session that exits instead of entering the REPL:

```sh
printf 'root\nls\n' | ./tools/h5explain file.h5
./tools/h5explain -c root -c ls file.h5
```

**Navigation commands:** `root`, `h5super`, `cd ("PATH")`, `go (OFF#B)`, `go (OFF#B, "PATH")`, `gos ("0xADDR")`, `gos ("0xADDR", "PATH")`, `back`, `pwd`

`cd` accepts a link name, a relative or absolute path, and `.`/`..` components. `back` retraces the full history one step per call. `go`/`gos` refuse offsets at or past the end of the file.

Version 1 object headers have no signature, so `go`/`gos` infer them from the version and message count. When a kind was inferred rather than confirmed by a signature, `pwd` and `info` mark it `(inferred: no signature)`; reaching the same address through `root` or `cd` corroborates it and the marker disappears.

**Inspection commands:** `explain`, `explain (N)`, `explain_msg (N)`, `info`, `msgs`, `cur`, `ls` / `links`, `traverse`, `dump`, `h5dump`

**Policy commands:** `check`, `check_all`, `profile`, `profile ("NAME")`

`check` runs the h5policy oracle over the open file and reports the findings that bear on the cursor — matched by byte extent or by object path, since h5policy anchors findings both ways. When nothing bears on the cursor it distinguishes *reached*, *not reached*, *not recorded for this kind*, and *walk stopped early*, so silence is never mistaken for a clean bill of health. See [`h5explain/README.md`](h5explain/README.md#policy-checks).

Use `msgs` to list object-header messages, then `explain (N)` or `explain_msg (N)` to explain message `N` in the current object header. Type `help` at the prompt for a full description of each command.

`traverse` is the only command that recursively walks chunk indexes. Ordinary navigation and `info` map the current primitive only, so large chunk indexes are not traversed accidentally.

`back` returns to the location before the most recent navigation step (`go`, `gos`, `cd`, `root`, `h5super`). Only one level of history is kept.
