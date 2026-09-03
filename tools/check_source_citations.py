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

"""Keep `<pickle>.pk:<line>` citations pointing at what they claim.

A line-number citation into our own source is the one kind of claim in this repo
that rots silently: the number stays syntactically valid while the code moves
under it, and nothing reading the prose can tell.  Measured when this checker was
written: ALL SIX such citations in the tracked tree were stale.  Two were off by
more than five hundred lines; one landed on a `var` declaration and one on a
local-heap owner counter, neither related to the claim; the remaining two landed
in comment blocks about the right subject but the wrong site.

WHY THIS IS NOT THE SAME RULE AS the stale case-field gate in
check_registry.py.  That one derives retired FIELD NAMES from git history, so a
citation of a renamed field is caught by the name alone.  A line number carries
no name to compare, so there is nothing to derive -- the citation has to say
what it is pointing at, and this checker holds it to that.

THE CONVENTION, therefore: every such citation names its anchor.

    h5_datatype.pk:1180 (member_off > elm_size)      # a code fragment
    h5_walk.pk:806 (H5_CORRUPT_SUPERBLOCK_EXTENSION_ALIAS)
    h5_group.pk:234-243 (data_seg_addr)              # a range

The anchor is free text in parentheses immediately after the citation -- only
whitespace may intervene, so a YAML folded scalar may wrap between the two; the
checker requires every non-trivial token in it to appear near the cited line.
That makes the citation self-checking and, more importantly, self-repairing: when
it breaks, the error names the token, so finding the new line is a grep rather
than an archaeology exercise.

An anchor may be a fragment of the cited line rather than a single identifier,
which is what makes it readable in prose -- `(member_off > elm_size)` says more
than `(member_off)`.  Tokens are matched independently and punctuation is
ignored, so reflow inside the cited statement does not fail the gate.

WHY THE ANCHOR IS MANDATORY rather than checked only when present: an optional
anchor is an anchor nobody adds.  The alternative design -- infer the anchor from
the citing prose and look for it near the target -- was rejected on measurement:
of the six citations here, at least one (a comment about which OFFSET a finding
reports) shares no identifier with its target at all, so inference would have
reported a correct citation as broken.  A gate whose false positives look exactly
like its true positives does not get trusted, and an untrusted gate gets
disabled.

SCOPE is deliberately our own pickles.  Citations into the libhdf5 tree
(`H5Dio.c:1435`) are far more numerous and cannot be checked here: that tree is
not in this repo, it moves independently, and those citations are pinned to a
stated upstream version rather than to a file we control.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
PICKLE_DIR = ROOT / "h5policy" / "pickles"

# This file states the convention, so it quotes citations that point nowhere.
ALLOWED = {"tools/check_source_citations.py"}

# `name.pk:12` or `name.pk:12-34`, optionally followed by an anchor in
# parentheses.
#
# Only whitespace -- optionally with one `#` comment-continuation marker -- may
# sit between the citation and its anchor.  Both of those appear for real reasons:
# a YAML folded scalar wraps prose wherever it likes, and half of these citations
# live in `#` comment blocks where a wrap starts the next line with `# `.  What
# the narrowness buys is that a citation with NO anchor cannot reach forward and
# adopt an unrelated parenthetical: anything else in between, a comma or a full
# stop included, ends the match.
#
# The anchor may not contain a nested paren, which keeps it from swallowing the
# rest of a sentence.  An anchor that wants call syntax writes the parts as a
# list instead: `(h5policy_mark_visited_btree, snod_addr)`.
CITATION = re.compile(
    r"\b(?P<file>[a-z0-9_]+\.pk):(?P<lo>\d+)(?:-(?P<hi>\d+))?"
    r"(?:[ \t\n]*(?:#[ \t]*)?\((?P<anchor>[^()]{1,120})\))?")

# Tokens too common to anchor anything: matching them would pass a citation that
# points at the wrong line but happens to sit near an `if` or a `var`.
STOPWORDS = {
    "if", "var", "return", "the", "and", "or", "not", "for", "while", "else",
    "true", "false", "int", "uint", "byte", "bytes", "at", "in", "is", "of",
    "to", "as", "a", "an", "it", "its", "this", "that", "with", "by", "on",
}

# Slack for a single-line citation.  A range citation must find its anchor
# inside the range it declares; a single line gets a few lines either way, so
# ordinary reflow inside a statement does not fail the gate while a real move
# still does.
SLACK = 3

# An anchor token has to be substantial enough to be evidence.  Short tokens are
# kept only when they are operators or numbers written in the source, which is
# why the filter is on the WORD tokens alone.
MIN_TOKEN = 3


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


def anchor_tokens(anchor: str) -> list[str]:
    """The words in an anchor that are worth requiring at the target."""
    words = re.findall(r"[A-Za-z_][A-Za-z0-9_.]*|\d+", anchor)
    return [w for w in words
            if w.lower() not in STOPWORDS and len(w) >= MIN_TOKEN]


def check_citation(cite, source_lines, rel, lineno):
    """Yield problem strings for one citation."""
    name = cite.group("file")
    lo = int(cite.group("lo"))
    hi = int(cite.group("hi")) if cite.group("hi") else lo
    anchor = cite.group("anchor")
    where = f"{rel}:{lineno} cites {name}:{cite.group('lo')}" + \
            (f"-{cite.group('hi')}" if cite.group("hi") else "")

    if source_lines is None:
        yield (f"CITATION_UNKNOWN_PICKLE {where} -- no such file under "
               f"h5policy/pickles/")
        return
    if hi < lo:
        yield f"CITATION_BAD_RANGE {where} -- range ends before it starts"
        return
    if lo < 1 or hi > len(source_lines):
        yield (f"CITATION_OUT_OF_RANGE {where} -- {name} has "
               f"{len(source_lines)} lines")
        return
    if not anchor:
        yield (f"CITATION_NO_ANCHOR {where} -- add the token it points at in "
               f"parentheses, e.g. `{name}:{lo} (some_identifier)`; see "
               f"tools/check_source_citations.py")
        return

    tokens = anchor_tokens(anchor)
    if not tokens:
        yield (f"CITATION_EMPTY_ANCHOR {where} -- the anchor `{anchor}` has no "
               f"token substantial enough to check")
        return

    slack = 0 if cite.group("hi") else SLACK
    window = source_lines[max(0, lo - 1 - slack):min(len(source_lines), hi + slack)]
    haystack = "\n".join(window)
    missing = [t for t in tokens if t not in haystack]
    if missing:
        yield (f"CITATION_ANCHOR_MISSING {where} -- {', '.join(missing)} "
               f"not found in {name}:{max(1, lo - slack)}-{min(len(source_lines), hi + slack)}; "
               f"the code moved, or the anchor is wrong")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--paths", nargs="*",
                    help="limit the scan to these paths (default: tracked files)")
    args = ap.parse_args()

    if args.paths:
        files = []
        for p in args.paths:
            path = Path(p)
            if path.is_dir():
                files += [str(q.relative_to(ROOT)) for q in sorted(path.rglob("*"))
                          if q.is_file()]
            else:
                files.append(str(path))
    else:
        files = tracked_files()
        if files is None:
            print("NOTE not a git checkout; source citations unchecked")
            return 0

    sources: dict[str, list[str] | None] = {}

    def pickle_lines(name):
        if name not in sources:
            path = PICKLE_DIR / name
            sources[name] = (path.read_text().splitlines()
                             if path.exists() else None)
        return sources[name]

    problems = []
    scanned = cited = 0
    for rel in files:
        if rel in ALLOWED:
            continue
        path = ROOT / rel
        if not path.is_file() or not is_text(path):
            continue
        # A citation inside the pickles themselves is a cross-reference between
        # source files and is checked the same way; nothing here excludes them.
        scanned += 1
        try:
            text = path.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        if ".pk:" not in text:
            continue
        # Scanned over the WHOLE text rather than line by line: prose in a YAML
        # folded scalar wraps wherever it wants, so a citation and its anchor
        # routinely straddle a newline.  Only whitespace may separate them
        # (CITATION), which is what keeps a match from reaching an unrelated
        # parenthetical further down.
        for cite in CITATION.finditer(text):
            cited += 1
            lineno = text.count("\n", 0, cite.start()) + 1
            problems += list(check_citation(
                cite, pickle_lines(cite.group("file")), rel, lineno))

    for p in problems:
        print(p)
    if problems:
        print(f"SOURCE CITATION CHECK FAILED: {len(problems)} problem(s) over "
              f"{cited} citation(s) in {scanned} file(s)")
        return 1
    print(f"SOURCE CITATION CHECK OK: {cited} pickle line citation(s) in "
          f"{scanned} tracked text file(s) name their anchor and point at it")
    return 0


if __name__ == "__main__":
    sys.exit(main())
