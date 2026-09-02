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

"""Regression checks for the pickle line-citation gate.

Every case is driven against the REAL pickles, so a citation that passes here
passes because the code is genuinely at that line.  The anchor for the positive
control is looked up rather than hard-coded: hard-coding it would make this test
fail every time the pickle moved, which is the failure mode the gate exists to
report about prose, not about its own test.

Each negative asserts on the specific tag it should produce.  A test that only
asserted "exit != 0" would pass just as happily if every input produced
CITATION_UNKNOWN_PICKLE -- which is exactly what a broken regex would do.

The two positive cases for line wrapping earn their place: the citation and its
anchor may be separated by a newline (YAML folds prose) or by a newline plus a
`#` comment-continuation marker (half the citations in the tree live in comment
blocks).  Both were bugs in the first version of the checker, found by real
citations rather than by review.
"""

from __future__ import annotations

import itertools
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "tools" / "check_source_citations.py"
PICKLES = ROOT / "h5policy" / "pickles"


def run(text: str) -> str:
    """Run the checker over one throwaway file and return its output."""
    with tempfile.TemporaryDirectory() as tmp:
        probe = Path(tmp) / "citing_file.yml"
        probe.write_text(text)
        out = subprocess.run(
            [sys.executable, str(CHECKER), "--paths", str(probe)],
            capture_output=True, text=True, cwd=str(ROOT))
        return out.stdout + out.stderr


def find_anchor():
    """A (file, line, token) that really exists: the first `fun` in h5_group.pk.

    Deliberately derived, not written down.  A hard-coded line number here would
    have to be maintained in lockstep with the pickle, and this test would then
    be one more stale citation of exactly the kind it is guarding against.
    """
    src = (PICKLES / "h5_group.pk").read_text().splitlines()
    for i, line in enumerate(src, 1):
        m = re.match(r"fun (h5policy_[a-z0-9_]+)", line)
        if m:
            return "h5_group.pk", i, m.group(1)
    raise AssertionError("no `fun h5policy_*` in h5_group.pk to anchor on")


def find_missing_pickle():
    """A pickle name that is genuinely absent, derived rather than written down.

    Written down, the name is two things at once: the fixture this test feeds
    the checker, and a citation-shaped literal sitting in a tracked file -- so
    the repo-wide scan reports it, and this test file fails the very gate it
    tests.  That is not hypothetical; it is how the gate landed, and the whole
    tree was red until this function replaced the literal.

    Deriving the name fixes both halves.  The source no longer spells a
    citation at all -- every one it feeds the checker is interpolated -- so the
    scan has nothing to catch here and the file stays under the gate rather than
    being exempted from it.  And unlike a hard-coded placeholder, the derivation
    PROVES the file is absent instead of assuming it, which is the same rule
    find_anchor() follows for the positive control.
    """
    for n in itertools.count():
        name = f"h5_absent_{n}.pk"
        if not (PICKLES / name).exists():
            return name


def expect(label, text, tag=None):
    out = run(text)
    if tag is None:
        assert "SOURCE CITATION CHECK OK" in out, f"{label}: expected OK\n{out}"
        assert "CITATION_" not in out, f"{label}: unexpected problem\n{out}"
    else:
        assert tag in out, f"{label}: expected {tag}\n{out}"
    print(f"  ok: {label}")


def main() -> int:
    name, line, token = find_anchor()
    print(f"anchoring on {name}:{line} ({token})")

    # POSITIVE CONTROL.  Without this the negatives below prove nothing: a
    # checker that rejected every citation would pass all of them.
    expect("a correct citation passes",
           f"# see {name}:{line} ({token}) for the walker\n")

    # The two wrapping shapes, both real.
    expect("anchor may wrap onto the next line (YAML folded prose)",
           f"note: >-\n  the walker at {name}:{line}\n  ({token}) does the work\n")
    expect("anchor may wrap after a comment-continuation marker",
           f"# the walker at {name}:{line}\n# ({token}) does the work\n")

    # A range citation finds its anchor anywhere inside the declared range.
    expect("a range citation passes when the anchor is inside it",
           f"# see {name}:{max(1, line - 5)}-{line + 5} ({token})\n")

    # NEGATIVES.
    expect("a missing anchor is caught",
           f"# see {name}:{line} for the walker\n",
           "CITATION_NO_ANCHOR")

    # The regex must not reach past punctuation to adopt an unrelated
    # parenthetical as an anchor.  This is the case that would silently disable
    # the gate for prose that happens to bracket its next clause.
    expect("an unrelated parenthetical is not adopted as an anchor",
           f"# see {name}:{line}.  (It is worth reading.)\n",
           "CITATION_NO_ANCHOR")

    # The point of the whole exercise: right anchor, wrong line.
    #
    # The drift target is SEARCHED for rather than guessed: a line the token
    # happens to sit near would make this case pass for the wrong reason, and it
    # would do so silently, since a citation that finds its anchor produces no
    # output at all.  The search asserts the token is absent from the window the
    # checker will look at, so the case cannot go vacuous as the pickle grows.
    src = (PICKLES / name).read_text().splitlines()
    src_len = len(src)
    drifted = None
    for cand in range(line + 50, src_len - 5):
        window = "\n".join(src[max(0, cand - 1 - 3):cand + 3])
        if token not in window:
            drifted = cand
            break
    assert drifted, f"no line in {name} whose window lacks {token}"
    expect("an anchor that is not at the cited line is caught",
           f"# see {name}:{drifted} ({token})\n",
           "CITATION_ANCHOR_MISSING")

    expect("a line past the end of the file is caught",
           f"# see {name}:{src_len + 1000} ({token})\n",
           "CITATION_OUT_OF_RANGE")

    missing = find_missing_pickle()
    expect("a citation of a nonexistent pickle is caught",
           f"# see {missing}:10 (something)\n",
           "CITATION_UNKNOWN_PICKLE")

    expect("a backwards range is caught",
           f"# see {name}:{line}-{line - 5} ({token})\n",
           "CITATION_BAD_RANGE")

    # An anchor made only of stopwords is not evidence, and saying so beats
    # accepting `(the var)` as a check.
    expect("an anchor with no substantial token is caught",
           f"# see {name}:{line} (the var is)\n",
           "CITATION_EMPTY_ANCHOR")

    print("SOURCE CITATION GATE TEST OK: the positive control passes and each "
          "of six defect shapes is caught by its own tag")
    return 0


if __name__ == "__main__":
    sys.exit(main())
