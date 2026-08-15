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

"""Regression checks for check_hygiene.py's explicit-path mode."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "tools/check_hygiene.py"


def fail(message: str) -> None:
    print(f"HYGIENE PATH TEST FAILED: {message}", file=sys.stderr)
    raise SystemExit(1)


def run(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECKER), "--paths", str(path.relative_to(ROOT))],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="hygiene-path-", dir=ROOT) as raw_tmp:
        tmp = Path(raw_tmp)
        clean = tmp / "clean.txt"
        clean.write_text("portable bundle evidence\n")
        result = run(tmp)
        if result.returncode:
            fail(f"clean path failed: {result.stderr}")

        leaked = tmp / "leaked.txt"
        leaked.write_text(str(Path("/").joinpath("home", "example", "input.h5")))
        result = run(tmp)
        if result.returncode != 1 or "host path" not in result.stderr:
            fail("host-path content was not rejected")

        leaked.write_text("".join(("g", "h", "s", "a", " reference")))
        result = run(tmp)
        if result.returncode != 1 or "advisory identifier" not in result.stderr:
            fail("advisory identifier content was not rejected")

    with tempfile.TemporaryDirectory(prefix="hygiene-outside-") as raw_tmp:
        outside = Path(raw_tmp)
        result = subprocess.run(
            [sys.executable, str(CHECKER), "--paths", str(outside)],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )
        if result.returncode != 1 or "inside the repository" not in result.stderr:
            fail("out-of-repository path was not rejected")

    print("HYGIENE PATH TEST OK: explicit paths accept clean bundles and reject leaks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
