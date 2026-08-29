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

"""Check tracked files for advisory identifiers, host paths, and references
into the gitignored cases/ tree (AGENTS.md)."""

from __future__ import annotations

import argparse
import importlib.machinery
import importlib.util
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

# CASE_BUNDLE bans references to bundles that a clone cannot resolve. A file
# that CREATES its own scratch directory under cases/ at run time is not making
# such a reference -- the directory does not have to pre-exist, and the script
# removes it again -- so the test harness's mutation-family scratch is exempt
# from that one rule.
CREATES_CASE_SCRATCH = {"h5policy/tests/run.sh"}

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

# A tracked reference INTO cases/ names something no clone can resolve: that
# tree is gitignored working scratch. Promote the specimen's sha256, a tracked
# fixture, or an explicit n/a instead (AGENTS.md, "Write and promotion
# boundary"). Two spellings are not references and stay allowed: the
# `cases/<id>/` placeholder that documentation and tool help have to quote --
# including the HTML-escaped form the Mermaid diagram needs -- and
# `registry/cases/`, which is tracked. The rule does not apply to files inside
# cases/ themselves; a bundle naming its own artifacts is correct, and gating it
# would fail on state no commit can fix, the same reason the tracked-set scan
# stops at that boundary.
CASE_BUNDLE = re.compile(
    r"(?<!registry/)\bcases/(?!<id>|&lt;id&gt;)[A-Za-z0-9_][A-Za-z0-9_.-]*")

# (pattern, what it is, whether it still applies where the case rule is exempt)
RULES = (
    (ADVISORY, "advisory identifier", True),
    (HOST_PATH, "host path", True),
    (CASE_BUNDLE, "case-bundle reference", False),
)


def fail(message: str) -> None:
    print(f"HYGIENE CHECK FAILED: {message}", file=sys.stderr)
    raise SystemExit(1)


# The generator-side half of the host-path rule. The scan below catches a leak
# after it lands in a file; this catches the emitter that would put it there
# again on the next run, which is what AGENTS.md ("If a generator emits a host
# path, fix the generator") actually asks for. h5policy-probe is checked because
# it is the only emitter whose output embeds paths it does not choose -- the
# symbolized frames of an AddressSanitizer report name the source tree the
# instrumented libhdf5 was compiled from.
PROBE = ROOT / "h5policy/tools/h5policy-probe"

# Deliberately a real host-shaped path: this file is exempt from HOST_PATH (see
# ALLOWED) precisely so the rule and its test can spell out what they match.
_ASAN_SAMPLE = {
    "error": "heap-buffer-overflow",
    "access": "READ of size 1 at 0x504000002dce thread T0",
    "top_frames": [
        "#0 0x1 in H5Z__filter_fletcher32 /home/someone/hdf5/src/H5Zfletcher32.c:75",
        "#1 0x2  (/home/someone/install/lib/libhdf5.so.1000.0.0+0x1234)",
    ],
}


def check_probe_emitter() -> None:
    """h5policy-probe must strip host paths from an ASan summary at emission."""
    if not PROBE.is_file():
        return
    loader = importlib.machinery.SourceFileLoader("h5policy_probe", str(PROBE))
    spec = importlib.util.spec_from_loader("h5policy_probe", loader)
    module = importlib.util.module_from_spec(spec)
    try:
        loader.exec_module(module)
    except Exception as exc:  # pragma: no cover - import failure is the finding
        fail(f"cannot load {PROBE.relative_to(ROOT)} to check its emitter: {exc}")
    portable_asan = getattr(module, "portable_asan", None)
    if portable_asan is None:
        fail("h5policy-probe no longer defines portable_asan(); an ASan report "
             "would carry the instrumented build's source-tree paths into every "
             "case bundle and registry record")
    emitted = portable_asan(_ASAN_SAMPLE)
    leaked = [line for line in emitted["top_frames"] + [emitted["access"]]
              if HOST_PATH.search(line)]
    if leaked:
        fail("h5policy-probe's portable_asan() left a host path in "
             f"{leaked[0]!r}")
    # Stripping the path must not strip what identifies the frame.
    if "H5Zfletcher32.c:75" not in emitted["top_frames"][0]:
        fail("h5policy-probe's portable_asan() dropped the source location; "
             "the frame no longer says which line faulted")
    if "libhdf5.so.1000.0.0+0x1234" not in emitted["top_frames"][1]:
        fail("h5policy-probe's portable_asan() dropped the soname or the module "
             "offset from an unsymbolized frame")


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
        exempt_from_case_rule = (rel.startswith("cases/")
                                 or rel in CREATES_CASE_SCRATCH)
        for pattern, what, applies_everywhere in RULES:
            if exempt_from_case_rule and not applies_everywhere:
                continue
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

    check_probe_emitter()
    scanned, violations = scan(files, exempt_policy_files)

    if violations:
        for v in violations[:40]:
            print(f"  {v}", file=sys.stderr)
        if len(violations) > 40:
            print(f"  ... and {len(violations) - 40} more", file=sys.stderr)
        fail(f"{len(violations)} violation(s) of the AGENTS.md hygiene rules; "
             "see Portable provenance and Write and promotion boundary for the "
             "substitutions to use")

    scope = "tracked" if not args.paths else "requested"
    print(f"HYGIENE CHECK OK: {scanned} {scope} text files carry no advisory "
          "identifiers, host paths, or case-bundle references")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
