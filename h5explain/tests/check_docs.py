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

"""Check the documented h5explain history semantics against the implementation."""

from __future__ import annotations

from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[2]
PICKLE = ROOT / "h5explain/pickles/h5explain.pk"
README = ROOT / "h5explain/README.md"
TOOLS = ROOT / "TOOLS.md"
TESTS = ROOT / "h5explain/tests/test_h5explain.py"


def fail(message: str) -> None:
    print(f"H5EXPLAIN DOC CHECK FAILED: {message}", file=sys.stderr)
    raise SystemExit(1)


def normalized(text: str) -> str:
    return " ".join(text.split())


def section(path: Path, heading: str) -> str:
    lines = path.read_text().splitlines()
    starts = [index for index, line in enumerate(lines) if line == heading]
    if len(starts) != 1:
        fail(
            f"{path.relative_to(ROOT)} has {len(starts)} {heading!r} headings"
        )

    start = starts[0]
    level = len(heading) - len(heading.lstrip("#"))
    end = len(lines)
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if not line.startswith("#"):
            continue
        next_level = len(line) - len(line.lstrip("#"))
        if next_level <= level and line[next_level:next_level + 1] == " ":
            end = index
            break
    return "\n".join(lines[start:end])


def history_limit() -> int:
    matches = re.findall(
        r"^var H5EX_HIST_MAX = ([0-9]+)UL;$",
        PICKLE.read_text(),
        re.MULTILINE,
    )
    if len(matches) != 1:
        fail(f"found {len(matches)} H5EX_HIST_MAX declarations")
    limit = int(matches[0])
    if limit < 2:
        fail(f"history limit {limit} does not provide multi-step history")
    return limit


def check_document(path: Path, text: str, limit: int) -> None:
    requirements = (
        "bounded",
        "one step at a time" if path == README else "one location per call",
        f"Up to `{limit}` prior locations are retained",
        "oldest is discarded",
        "failed navigation",
        "adds no history entry",
    )
    missing = [requirement for requirement in requirements if requirement not in text]
    if missing:
        fail(
            f"{path.relative_to(ROOT)} lacks "
            + ", ".join(repr(requirement) for requirement in missing)
        )

    if re.search(r"only one (?:level|step).*history", text, re.IGNORECASE):
        fail(f"{path.relative_to(ROOT)} still claims one-level history")


def main() -> int:
    limit = history_limit()
    readme = normalized(section(README, "## Commands"))
    tools = normalized(section(TOOLS, "## h5explain Interactive Explorer"))
    check_document(README, readme, limit)
    check_document(TOOLS, tools, limit)

    tests = TESTS.read_text()
    if "def test_back_retraces_more_than_one_step():" not in tests:
        fail("the multi-step history behavior regression is missing")
    if tests.count('"back"') < 3:
        fail("the behavior regression no longer exercises repeated back calls")

    source = PICKLE.read_text()
    if "var off = apop (h5explain_hist_off);" not in source:
        fail("back no longer pops the retained location stack")
    if "if (h5explain_hist_off'length as uint<64> > H5EX_HIST_MAX)" not in source:
        fail("history no longer enforces its documented bound")
    for obsolete in ("walk of any depth", "the three arrays"):
        if obsolete in source:
            fail(f"implementation comment still contains {obsolete!r}")

    print(
        "H5EXPLAIN DOC CHECK OK: "
        f"back retains and retraces up to {limit} prior locations"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
