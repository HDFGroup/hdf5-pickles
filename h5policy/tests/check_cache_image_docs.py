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

"""Keep the documented metadata cache-image boundary tied to live reports."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "h5policy/tests/valid/cache_image.h5"
H5POLICY = ROOT / "tools/h5policy"
HEADING = "### Metadata cache-image hard boundary"

DOC_REQUIREMENTS = {
    ROOT / "h5policy/README.md": (
        "cached entry bodies",
        "shadowed",
        "unshadowed",
        "exit `5`",
        "`unsupported_coverage_gap`",
        "`H5_UNSUPPORTED_PICKLE_COVERAGE_GAP`",
        "`analysis.complete`",
        "`analysis.walk_completed`",
        '`analysis.stop_reason: "rejection"`',
        '`analysis.stop_reason: "cache_image_coverage_gap"`',
        "`--continue-after-rejection`",
    ),
    ROOT / "h5policy/docs/H5PolicyProfile.md": (
        "cached entry bodies",
        "shadowed",
        "unshadowed",
        "exit `5`",
        "`unsupported_coverage_gap`",
        "`H5_UNSUPPORTED_PICKLE_COVERAGE_GAP`",
        "`analysis.complete`",
        "`analysis.walk_completed`",
        '`analysis.stop_reason` is `"rejection"`',
        '`analysis.stop_reason` is `"cache_image_coverage_gap"`',
        "`--continue-after-rejection`",
    ),
    ROOT / "h5policy/docs/README.md": (
        "cached entry bodies",
        "shadowed",
        "unshadowed",
        "exit `5`",
        "`unsupported_coverage_gap`",
        "`H5_UNSUPPORTED_PICKLE_COVERAGE_GAP`",
        "`analysis.complete`",
        "`analysis.walk_completed`",
        '`analysis.stop_reason: "cache_image_coverage_gap"`',
        '`"rejection"`',
        "`--continue-after-rejection`",
    ),
}


def fail(message: str) -> None:
    print(f"CACHE-IMAGE DOC CHECK FAILED: {message}", file=sys.stderr)
    raise SystemExit(1)


def section_text(path: Path) -> str:
    lines = path.read_text().splitlines()
    starts = [index for index, line in enumerate(lines) if line == HEADING]
    if len(starts) != 1:
        fail(f"{path.relative_to(ROOT)} has {len(starts)} {HEADING!r} headings")

    start = starts[0]
    level = len(HEADING) - len(HEADING.lstrip("#"))
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


def check_documentation() -> None:
    for path, required in DOC_REQUIREMENTS.items():
        section = section_text(path)
        missing = [token for token in required if token not in section]
        if missing:
            fail(
                f"{path.relative_to(ROOT)} boundary section lacks "
                + ", ".join(repr(token) for token in missing)
            )


def run_h5policy(profile: str, continue_after_rejection: bool = False) -> dict:
    command = [str(H5POLICY), "--profile", profile]
    if continue_after_rejection:
        command.append("--continue-after-rejection")
    command.append(str(FIXTURE))

    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired:
        fail(f"{profile} cache-image run exceeded 30 seconds")

    if result.returncode != 5:
        fail(
            f"{profile} cache-image run exited {result.returncode}, expected 5\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        fail(f"{profile} cache-image run did not emit JSON: {error}")


def check_report(
    report: dict,
    label: str,
    expected_continue: bool,
    expected_stop_reason: str,
) -> None:
    if report.get("decision") != "unsupported_coverage_gap":
        fail(f"{label}: decision={report.get('decision')!r}")

    analysis = report.get("analysis", {})
    expected_analysis = {
        "complete": False,
        "walk_started": True,
        "walk_completed": False,
        "stop_reason": expected_stop_reason,
        "continue_after_rejection": expected_continue,
        "findings_truncated": False,
    }
    for field, expected in expected_analysis.items():
        if analysis.get(field) != expected:
            fail(
                f"{label}: analysis.{field}={analysis.get(field)!r}, "
                f"expected {expected!r}"
            )

    findings = report.get("findings", [])
    matches = [
        finding
        for finding in findings
        if finding.get("code") == "H5_UNSUPPORTED_PICKLE_COVERAGE_GAP"
        and finding.get("message")
        == "metadata cache image contents are not decoded by Phase 2"
    ]
    if len(matches) != 1:
        fail(f"{label}: expected one canonical cache-image coverage finding")


def main() -> int:
    check_documentation()

    if shutil.which("poke") is None:
        print("CACHE-IMAGE DOC CHECK SKIP: docs passed; GNU poke is unavailable")
        return 0

    for profile in ("legacy", "trusted-fast", "untrusted-strict", "forensic"):
        continued = profile == "forensic"
        stop_reason = "cache_image_coverage_gap" if continued else "rejection"
        report = run_h5policy(profile)
        check_report(report, profile, continued, stop_reason)

    report = run_h5policy("untrusted-strict", continue_after_rejection=True)
    check_report(
        report,
        "untrusted-strict with continuation",
        expected_continue=True,
        expected_stop_reason="cache_image_coverage_gap",
    )

    print("CACHE-IMAGE DOC CHECK OK: docs match all profile reports")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
