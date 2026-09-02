#!/usr/bin/env python3
# Copyright (C) 2026 The HDF Group.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Keep `src/H5xxx.c:<line>` citations pointing at a line that holds code.

This repository cites the libhdf5 tree constantly -- 343 distinct file/line
pairs across registry records, fixture expectations, pickles and generators --
and those citations rot in a way nothing can see: upstream inserts a line, every
number below it shifts, and the citation stays syntactically perfect while
pointing one line off.  Measured when this checker was written, against develop
`b7b85e7abf9`: NINE distinct citations had drifted onto a blank line, a bare
brace or a comment terminator, in sixteen places, every one of them off by one
or two lines from the statement its own prose described.

WHAT THIS CHECKS, and deliberately no more:

    the file exists in the upstream tree
    the line is within the file
    the line holds something other than whitespace, a lone brace, or a
    comment delimiter

WHY NOT MORE.  The obvious stronger gate is the one
tools/check_source_citations.py applies to our own pickles: require an anchor
and look for it near the cited line.  For upstream citations the anchor would
have to be inferred from the surrounding prose, and that was BUILT AND MEASURED
before this file was written: of 842 citation occurrences, 425 carry no function
name in their context at all, and the mismatches it did report were dominated by
sentences that carry two citations and two function names -- "walks past
libhdf5's own guard (H5Dchunk.c:1185) ... leaving only assert(...) in
H5D__chunk_lock (H5Dchunk.c:4638)" cross-matches into a false positive.  A gate
whose false positives look exactly like its true positives gets disabled, so
this one checks only what needs no annotation to check.

The cost of that choice, stated plainly: a citation that drifts onto ANOTHER
STATEMENT is invisible here.  This catches the crude half.

WHY IT CAN SKIP.  The upstream tree is not in this repository and its location
is a per-machine path, which portable provenance forbids recording.  So the
tree comes from $HDF5_SOURCE_DIR (the variable .devcontainer/build-hdf5.sh
already uses) and the check reports itself SKIPPED when that is unset or does
not look like an HDF5 checkout.  A skip is not a pass and says so.  The OK line
names the upstream revision it agreed with, because "the citations are correct"
is meaningless without saying correct against WHAT -- the numbers here were
right when written, and drifted because develop moved underneath them.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]

# `src/H5Dchunk.c:733`, `H5Olayout.c:123-124`.  The `src/` prefix is optional
# because both spellings are in use; the line range is optional and only its
# first number is checked (the last line of a range is routinely a closing
# brace, which is exactly what this checker rejects for a single citation).
CITATION = re.compile(r"\b(?:src/)?(?P<file>H5[A-Za-z0-9_]*\.c):(?P<lo>\d+)(?:-(?P<hi>\d+))?")

# A line that carries no statement.  A citation landing here is drift: nobody
# points a reader at a blank line or at the `*/` that ends a comment banner.
EMPTY_LINE = {"", "{", "}", "};", "*/", "/*", "} /* end for */", "} /* end if */",
              "} /* end else */", "} /* end while */"}

# This file quotes citations to explain the convention, and the audit note in
# the registry record quotes the pre-repin numbers on purpose.
ALLOWED = {"tools/check_upstream_citations.py"}


def upstream_tree():
    """The libhdf5 checkout to check against, or None with a reason."""
    raw = os.environ.get("HDF5_SOURCE_DIR", "").strip()
    if not raw:
        return None, "HDF5_SOURCE_DIR is unset"
    tree = Path(raw).expanduser()
    if not (tree / "src" / "H5public.h").is_file():
        return None, f"{raw} does not look like an HDF5 checkout (no src/H5public.h)"
    return tree, None


def upstream_revision(tree):
    """A short revision for the OK line, or a version string when not a checkout."""
    try:
        done = subprocess.run(["git", "-C", str(tree), "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True)
        if done.returncode == 0 and done.stdout.strip():
            return done.stdout.strip()
    except OSError:
        pass
    try:
        text = (tree / "src" / "H5public.h").read_text()
        nums = [re.search(rf"#define {k}\s+(\d+)", text)
                for k in ("H5_VERS_MAJOR", "H5_VERS_MINOR", "H5_VERS_RELEASE")]
        if all(nums):
            return ".".join(n.group(1) for n in nums)
    except OSError:
        pass
    return "unknown revision"


def tracked_files():
    out = subprocess.run(["git", "-C", str(ROOT), "ls-files"],
                         capture_output=True, text=True)
    if out.returncode != 0:
        return None
    return [p for p in out.stdout.splitlines() if p]


def is_text(path: Path) -> bool:
    try:
        with open(path, "rb") as f:
            return b"\0" not in f.read(8192)
    except OSError:
        return False


def check_file(rel, text, tree, source_cache):
    """Yield problem strings for one citing file."""
    for cite in CITATION.finditer(text):
        name = cite.group("file")
        lo = int(cite.group("lo"))
        lineno = text.count("\n", 0, cite.start()) + 1
        where = f"{rel}:{lineno} cites src/{name}:{cite.group('lo')}"

        if name not in source_cache:
            path = tree / "src" / name
            source_cache[name] = (path.read_text(errors="replace").splitlines()
                                  if path.is_file() else None)
        body = source_cache[name]

        if body is None:
            yield (f"UPSTREAM_UNKNOWN_FILE {where} -- no src/{name} in the "
                   f"upstream tree; renamed, removed, or a typo")
            continue
        if lo < 1 or lo > len(body):
            yield (f"UPSTREAM_OUT_OF_RANGE {where} -- src/{name} has "
                   f"{len(body)} lines")
            continue
        stripped = body[lo - 1].strip()
        if stripped in EMPTY_LINE:
            near = ""
            for delta in (1, -1, 2, -2):
                cand = lo + delta
                if 1 <= cand <= len(body) and body[cand - 1].strip() not in EMPTY_LINE:
                    near = (f"; the nearest statement is :{cand}, "
                            f"{body[cand - 1].strip()[:60]!r}")
                    break
            yield (f"UPSTREAM_NOT_A_STATEMENT {where} -- that line is "
                   f"{stripped!r}{near}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--paths", nargs="*",
                    help="limit the scan to these paths (default: tracked files)")
    ap.add_argument("--tree", help="upstream checkout (default: $HDF5_SOURCE_DIR)")
    args = ap.parse_args()

    if args.tree:
        os.environ["HDF5_SOURCE_DIR"] = args.tree
    tree, why = upstream_tree()
    if tree is None:
        # A skip is not a pass, and the message has to say what would make it
        # run -- a silent skip is how a gate stops being a gate.
        print(f"UPSTREAM CITATION CHECK SKIPPED: {why}; set HDF5_SOURCE_DIR to "
              f"an HDF5 checkout to verify {'the given paths' if args.paths else 'the tree'}")
        return 0

    files = args.paths if args.paths else tracked_files()
    if files is None:
        print("NOTE not a git checkout; upstream citations unchecked")
        return 0

    source_cache: dict[str, list[str] | None] = {}
    problems = []
    scanned = cited = 0
    for rel in files:
        if rel in ALLOWED:
            continue
        path = ROOT / rel
        if not path.is_file() or not is_text(path):
            continue
        try:
            text = path.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        if ".c:" not in text:
            continue
        scanned += 1
        cited += len(CITATION.findall(text))
        problems += list(check_file(rel, text, tree, source_cache))

    for p in problems:
        print(p)
    rev = upstream_revision(tree)
    if problems:
        print(f"UPSTREAM CITATION CHECK FAILED: {len(problems)} problem(s) over "
              f"{cited} citation(s), against upstream {rev}")
        return 1
    print(f"UPSTREAM CITATION CHECK OK: {cited} libhdf5 line citation(s) in "
          f"{scanned} tracked file(s) point at a statement in upstream {rev}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
