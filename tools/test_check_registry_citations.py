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

"""Regression checks for check_registry.py's stale case-field citation gate.

The gate derives its deny-list from git history: every top-level field name a
case record has ever carried, minus the names any record carries now, is a dead
name that may appear only in a record that once had it.  Nothing declares the
rename, which is the point -- whoever renames a field is exactly the person who
forgets the citations.

That derivation is the part worth pinning, because it is invisible: a refactor
that broke it would leave the checker passing and the gate silently dead.  So
this test RENAMES a field for real and asserts the citation is caught.

It works in a throwaway `git worktree` so the live tree is never perturbed -- a
test that edits tracked files leaves them dirty when it crashes, and the tracked
files here are case records.  The worktree is checked out at HEAD and the
CURRENT checker is copied in, so the test exercises the working-tree rule rather
than whatever HEAD happened to contain.

Assertions key on the CASE_FIELD_CITATION_STALE tag rather than the exit code:
check_registry.py has many other gates, and a worktree without a generated
corpus trips some of them.  Keying on the tag keeps this test about one rule.
"""

from __future__ import annotations

from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

import yaml

ROOT = Path(__file__).resolve().parents[1]
TAG = "CASE_FIELD_CITATION_STALE"
# Copied into the worktree so the rule under test is the working-tree one.
CHECKER_FILES = ("tools/check_registry.py", "tools/finding_registry.py")


def fail(message: str) -> None:
    print(f"CITATION GATE TEST FAILED: {message}", file=sys.stderr)
    raise SystemExit(1)


def solo_field() -> tuple[str, str]:
    """A committed top-level field owned by exactly one record.

    Renaming a field that a second record still carries proves nothing: the name
    stays live, so it is correctly not a dead name.  The gate's union semantics
    are deliberate, and picking a shared field would make this test vacuous.
    """
    owners: dict[str, list[str]] = {}
    for path in sorted((ROOT / "registry/cases").glob("*.yml")):
        doc = yaml.safe_load(path.read_text())
        if isinstance(doc, dict):
            for key in doc:
                owners.setdefault(key, []).append(path.name)
    for key, files in sorted(owners.items()):
        # Word-matchable, and present in HEAD so history knows the name.
        if len(files) != 1 or "_" not in key or len(key) < 10:
            continue
        blob = subprocess.run(
            ["git", "show", f"HEAD:registry/cases/{files[0]}"],
            cwd=ROOT, capture_output=True, text=True, check=False)
        if blob.returncode == 0 and f"\n{key}:" in blob.stdout:
            return key, files[0]
    fail("no committed single-owner case field to rename; cannot test the gate")
    raise AssertionError  # unreachable, keeps type checkers quiet


def run_checker(tree: Path) -> str:
    done = subprocess.run(
        [sys.executable, "tools/check_registry.py"],
        cwd=tree, capture_output=True, text=True, timeout=180, check=False)
    return done.stdout + done.stderr


def main() -> int:
    if subprocess.run(["git", "rev-parse", "--git-dir"], cwd=ROOT,
                      capture_output=True, check=False).returncode:
        print("CITATION GATE TEST SKIPPED: not a git checkout")
        return 0

    field, record = solo_field()
    with tempfile.TemporaryDirectory() as tmp:
        tree = Path(tmp) / "wt"
        add = subprocess.run(
            ["git", "worktree", "add", "--detach", "--quiet", str(tree), "HEAD"],
            cwd=ROOT, capture_output=True, text=True, check=False)
        if add.returncode:
            print(f"CITATION GATE TEST SKIPPED: git worktree unavailable "
                  f"({add.stderr.strip()[:120]})")
            return 0
        try:
            for rel in CHECKER_FILES:
                shutil.copy2(ROOT / rel, tree / rel)

            # 1. Unperturbed: the gate must be silent about this field.
            if re.search(rf"{TAG}.*\b{re.escape(field)}\b", run_checker(tree)):
                fail(f"gate reported {field!r} stale before any rename")

            # 2. Rename the field and cite the old name from a doc.  Nothing
            #    declares the rename anywhere -- history is the only evidence.
            rec = tree / "registry/cases" / record
            text = rec.read_text()
            if f"\n{field}:" not in text:
                fail(f"{record} lost its {field!r} key in the worktree")
            rec.write_text(text.replace(f"\n{field}:", f"\n{field}_renamed:", 1))
            doc = tree / "registry/README.md"
            doc.write_text(doc.read_text()
                           + f"\n<!-- see the record's {field} section -->\n")

            out = run_checker(tree)
            if not re.search(rf"{TAG}.*\b{re.escape(field)}\b", out):
                fail(f"gate missed a stale citation of the renamed {field!r}; "
                     f"the history-derived deny-list is not working")
            if "registry/README.md" not in out:
                fail("gate did not name the citing file")

            # 3. The retiring record may still name the field: that is where the
            #    retraction narrative belongs.  Citing it there is not a failure.
            rec.write_text(rec.read_text()
                           + f"\nwhy_renamed: the {field} field was renamed.\n")
            out = run_checker(tree)
            for line in out.splitlines():
                if TAG in line and f"registry/cases/{record}" in line:
                    fail("gate flagged the retiring record's own narrative")
        finally:
            subprocess.run(["git", "worktree", "remove", "--force", str(tree)],
                           cwd=ROOT, capture_output=True, check=False)

    print(f"CITATION GATE TEST OK: a renamed case field ({field}) is caught "
          f"from git history alone, and the retiring record may still name it")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
