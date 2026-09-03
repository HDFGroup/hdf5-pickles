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

"""Regression checks for the upstream line-citation gate.

Driven against a SYNTHETIC upstream tree rather than the real one: the real
checkout moves under us, so a test anchored to it would fail for the same reason
the gate exists to report about prose.  The synthetic tree makes each case exact
-- this line is blank, this line is past the end -- and keeps the test runnable
where no HDF5 checkout exists.

The skip path is a case too, and the important one: this gate is green-by-
absence whenever HDF5_SOURCE_DIR is unset, so "it skipped" must be visible in
the output and must never be spelled like a pass.

NO CITATION IS SPELLED OUT IN THIS FILE.  Every one is interpolated from a
derived name, because a literal here would be scanned by the very gate under
test and reported as a citation of a file that does not exist upstream.  That
is not a hypothetical: the sibling pickle gate landed with exactly that defect
and its own test was the only thing failing it.
"""

from __future__ import annotations

import itertools
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "tools" / "check_upstream_citations.py"

# The synthetic upstream file: line 3 holds a statement, line 4 is blank, and
# line 5 is a bare closing brace.
SOURCE = "int f(void)\n{\n    return g();\n\n}\n"
STATEMENT_LINE, BLANK_LINE, BRACE_LINE, PAST_EOF = 3, 4, 5, 500


def build_tree(tmp):
    """A directory the checker accepts as an HDF5 checkout."""
    src = Path(tmp) / "src"
    src.mkdir(parents=True)
    (src / "H5public.h").write_text("#define H5_VERS_MAJOR 9\n"
                                    "#define H5_VERS_MINOR 9\n"
                                    "#define H5_VERS_RELEASE 9\n")
    name = "H5" + "Synthetic" + ".c"
    (src / name).write_text(SOURCE)
    return src, name


def absent_name(src):
    """A source name the synthetic tree does not contain, derived not written."""
    for n in itertools.count():
        name = f"H5Absent{n}.c"
        if not (src / name).exists():
            return name


def run(citing_text, tree=None, tmpdir=None):
    probe = Path(tmpdir) / "citing_file.yml"
    probe.write_text(citing_text)
    cmd = [sys.executable, str(CHECKER), "--paths", str(probe)]
    if tree:
        cmd += ["--tree", str(tree)]
    out = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT),
                         env={"PATH": "/usr/bin:/bin"})
    return out.stdout + out.stderr


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        src, name = build_tree(tmp)
        tree = src.parent
        cite = lambda ln, f=None: f"# see src/{f or name}:{ln} for the check\n"

        def expect(label, text, tag=None, tree_arg=tree):
            out = run(text, tree_arg, tmp)
            if tag is None:
                assert "UPSTREAM CITATION CHECK OK" in out, f"{label}\n{out}"
                assert "UPSTREAM_" not in out.replace(
                    "UPSTREAM CITATION CHECK OK", ""), f"{label}\n{out}"
            else:
                assert tag in out, f"{label}: expected {tag}\n{out}"
            print(f"  ok: {label}")

        # POSITIVE CONTROL.  Without it the negatives prove nothing: a checker
        # that rejected everything would pass all of them.
        expect("a citation of a real statement passes", cite(STATEMENT_LINE))

        # A range is checked on its first line, which is where the drift shows.
        expect("a range citation passes when it starts on a statement",
               f"# see src/{name}:{STATEMENT_LINE}-{BRACE_LINE} for the check\n")

        # NEGATIVES, one tag each.
        expect("a citation of a blank line is caught", cite(BLANK_LINE),
               "UPSTREAM_NOT_A_STATEMENT")
        expect("a citation of a bare brace is caught", cite(BRACE_LINE),
               "UPSTREAM_NOT_A_STATEMENT")
        expect("a citation past the end of the file is caught", cite(PAST_EOF),
               "UPSTREAM_OUT_OF_RANGE")
        expect("a citation of a file not in the tree is caught",
               cite(STATEMENT_LINE, absent_name(src)), "UPSTREAM_UNKNOWN_FILE")

        # The nearest-statement hint is what makes a failure a grep rather than
        # an archaeology exercise, so it is part of the contract.
        out = run(cite(BLANK_LINE), tree, tmp)
        assert f"the nearest statement is :{STATEMENT_LINE}" in out, out
        print("  ok: the failure names the nearest statement")

        # THE SKIP PATH.  Green-by-absence has to be visible, and must not be
        # spelled like a pass.
        out = run(cite(BLANK_LINE), Path(tmp) / "not-a-checkout", tmp)
        assert "UPSTREAM CITATION CHECK SKIPPED" in out, out
        assert "CHECK OK" not in out, out
        assert "HDF5_SOURCE_DIR" in out, out
        print("  ok: a tree that is not a checkout skips loudly, not silently")

    print("UPSTREAM CITATION GATE TEST OK: the positive control passes, each of "
          "three defect shapes is caught by its own tag, and the skip is visible")
    return 0


if __name__ == "__main__":
    sys.exit(main())
