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

"""Check tracked files for advisory identifiers and host paths (AGENTS.md)."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]

# A file that STATES a rule has to quote the pattern the rule bans, so the two
# files defining this policy are exempt from it: AGENTS.md, which writes the
# rules in prose, and this checker, whose HOST_PATH regex below necessarily
# contains a literal host prefix. Nothing else may be added here -- an exemption
# is how the next leak hides. (Encoding the patterns to dodge the check was the
# alternative and is worse: it would make the rule unreadable at the one place a
# reader looks to understand it.)
ALLOWED = {"AGENTS.md", "tools/check_hygiene.py"}

# Advisory identifiers are not authoritative here, in any spelling or position:
# record fields, prose, comments, file names, directory names. The lowercase
# underscored slug is the form that survived a full-id sweep and had to be
# removed separately, so it is matched explicitly rather than by luck.
ADVISORY = re.compile(r"[Gg][Hh][Ss][Aa]")

# Host paths pin a record to one workstation. A bare "~/" is deliberately NOT
# matched: "~/.pokerc" is a real instruction to a reader, and the A~ / A'~
# invariant notation would collide with it. Only home-rooted prefixes that have
# actually leaked are listed.
HOST_PATH = re.compile(r"/home/|/Users/|~/\.local|~/h5|~/projects|~/tmp")

RULES = (
    (ADVISORY, "advisory identifier"),
    (HOST_PATH, "host path"),
)


def fail(message: str) -> None:
    print(f"HYGIENE CHECK FAILED: {message}", file=sys.stderr)
    raise SystemExit(1)


def tracked_files() -> list[Path] | None:
    """Return tracked paths, or None when git cannot answer.

    The scan is deliberately limited to tracked files. cases/ is gitignored
    working scratch: it is regenerated constantly and differs per machine, so
    gating it here would fail on state no commit can fix. What keeps cases/
    clean instead is portable_path() in tools/h5cve and h5policy-probe, applied
    where those tools emit paths.
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "-z"],
            capture_output=True, timeout=60, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return [ROOT / p.decode() for p in out.split(b"\0") if p]


def requested_files(raw_paths: list[str]) -> list[Path]:
    """Return text-file candidates beneath explicitly named repository paths."""
    files: list[Path] = []
    for raw_path in raw_paths:
        path = Path(raw_path)
        candidate = path if path.is_absolute() else ROOT / path
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(ROOT)
        except (OSError, ValueError):
            fail(f"--paths entry must exist inside the repository: {raw_path}")

        if resolved.is_file():
            files.append(resolved)
        elif resolved.is_dir():
            for child in resolved.rglob("*"):
                if not child.is_file():
                    continue
                try:
                    child.resolve().relative_to(ROOT)
                except (OSError, ValueError):
                    fail(f"--paths entry contains a file outside the repository: {raw_path}")
                files.append(child)
        else:
            fail(f"--paths entry is neither a file nor a directory: {raw_path}")
    return sorted(set(files))


def is_text(path: Path) -> bool:
    try:
        return b"\0" not in path.open("rb").read(8192)
    except OSError:
        return False


def scan(files: list[Path], exempt_policy_files: bool) -> tuple[int, list[str]]:
    """Return the number of text files scanned and any rule violations."""
    violations: list[str] = []
    scanned = 0
    for path in files:
        try:
            rel = path.relative_to(ROOT).as_posix()
        except ValueError:
            fail(f"scan target is outside the repository: {path}")
        if ((exempt_policy_files and rel in ALLOWED)
                or not path.is_file() or not is_text(path)):
            continue
        scanned += 1
        for pattern, what in RULES:
            if pattern.search(rel):
                violations.append(f"{rel}: {what} in the file name")
            try:
                text = path.read_text(encoding="utf-8", errors="surrogateescape")
            except OSError:
                continue
            for n, line in enumerate(text.splitlines(), 1):
                m = pattern.search(line)
                if m:
                    violations.append(
                        f"{rel}:{n}: {what} {m.group(0)!r} in "
                        f"{line.strip()[:70]!r}")
    return scanned, violations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--paths", nargs="+", metavar="PATH",
        help="scan explicit repository-local files or directories instead of tracked files",
    )
    args = parser.parse_args()

    if args.paths:
        files = requested_files(args.paths)
        exempt_policy_files = False
    else:
        files = tracked_files()
        if files is None:
            print("HYGIENE CHECK SKIPPED: git ls-files unavailable; "
                  "cannot determine the tracked set", file=sys.stderr)
            return 0
        exempt_policy_files = True

    scanned, violations = scan(files, exempt_policy_files)

    if violations:
        for v in violations[:40]:
            print(f"  {v}", file=sys.stderr)
        if len(violations) > 40:
            print(f"  ... and {len(violations) - 40} more", file=sys.stderr)
        fail(f"{len(violations)} violation(s) of the AGENTS.md 'Never' rules; "
             "see the Portable provenance section for the substitutions to use")

    scope = "tracked" if not args.paths else "requested"
    print(f"HYGIENE CHECK OK: {scanned} {scope} text files carry no advisory "
          "identifiers or host paths")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
