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

"""Check that h5cve creates a complete private advisory handoff draft."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
H5CVE = ROOT / "tools/h5cve"
POC = ROOT / "h5policy/tests/malformed/continuation_overlaps_source.h5"
CASE_ID = f"_advisory_draft_check_{os.getpid()}"
CASE_DIR = ROOT / "cases" / CASE_ID


def fail(message: str) -> None:
    print(f"ADVISORY DRAFT CHECK FAILED: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> int:
    if CASE_DIR.exists():
        fail("temporary advisory-draft case already exists")
    try:
        result = subprocess.run(
            [str(H5CVE), "init", CASE_ID, "--poc", str(POC)],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )
        if result.returncode:
            fail(f"h5cve init failed: {result.stderr}")
        draft = CASE_DIR / "github-advisory.md"
        if not draft.is_file():
            fail("h5cve init did not create github-advisory.md")
        text = draft.read_text()
        for heading in (
            "## Title",
            "## CVE identifier",
            "## Description",
            "### Impact",
            "### Patches",
            "### Workarounds",
            "### References",
            "## Affected products",
            "## Severity",
            "## Weaknesses",
            "## Credits",
        ):
            if heading not in text:
                fail(f"draft lacks {heading!r}")
    finally:
        shutil.rmtree(CASE_DIR, ignore_errors=True)

    print("ADVISORY DRAFT CHECK OK: h5cve creates all repository-form fields")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
