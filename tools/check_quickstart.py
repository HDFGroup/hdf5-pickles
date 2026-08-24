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

"""Check the first-ten-minutes guide and canary/glossary documentation."""

from __future__ import annotations

import ast
import json
from pathlib import Path
import re
import subprocess
import sys

import yaml


ROOT = Path(__file__).resolve().parents[1]
GUIDE = ROOT / "docs/FIRST_10_MINUTES.md"
TOOLS_GUIDE = ROOT / "docs/TOOLS.md"
GLOSSARY = ROOT / "docs/GLOSSARY.md"
H5CVE = ROOT / "tools/h5cve"
COVERAGE = ROOT / "registry/validation-coverage.yml"
H5POLICY = ROOT / "tools/h5policy"
H5EXPLAIN = ROOT / "tools/h5explain"
SAMPLE = ROOT / "examples/file.h5"


def fail(message: str) -> None:
    print(f"QUICKSTART CHECK FAILED: {message}", file=sys.stderr)
    raise SystemExit(1)


def canary_mapping() -> dict[str, str]:
    tree = ast.parse(H5CVE.read_text(), filename=str(H5CVE))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name)
            and target.id == "CANARY_BY_RECORD"
            for target in node.targets
        ):
            continue
        value = ast.literal_eval(node.value)
        if not isinstance(value, dict) or not all(
            isinstance(record, str) and isinstance(exercise, str)
            for record, exercise in value.items()
        ):
            fail("CANARY_BY_RECORD must be a string-to-string dictionary")
        return value
    fail("tools/h5cve does not define CANARY_BY_RECORD")


def coverage_records() -> set[str]:
    data = yaml.safe_load(COVERAGE.read_text())
    records = data.get("records") if isinstance(data, dict) else None
    if not isinstance(records, list):
        fail("validation coverage manifest has no records list")
    names = {
        record.get("record")
        for record in records
        if isinstance(record, dict) and isinstance(record.get("record"), str)
    }
    if len(names) != len(records):
        fail("validation coverage records must have unique string names")
    return names


def check_canary_inventory() -> tuple[int, int]:
    canary_by_record = canary_mapping()
    canaries = set(canary_by_record)
    records = coverage_records()
    missing = sorted(records - canaries)
    unknown = sorted(canaries - records)
    if missing or unknown:
        details = []
        if missing:
            details.append(f"missing canaries for {', '.join(missing)}")
        if unknown:
            details.append(f"unknown canary records {', '.join(unknown)}")
        fail("; ".join(details))

    text = TOOLS_GUIDE.read_text()
    marker = re.findall(
        r"<!-- canary-family-inventory: ([0-9]+)/([0-9]+) -->", text
    )
    if len(marker) != 1:
        fail("docs/TOOLS.md needs exactly one canary-family-inventory marker")
    documented = tuple(int(value) for value in marker[0])
    actual = (len(canaries), len(records))
    if documented != actual:
        fail(
            "documented canary inventory "
            f"{documented[0]}/{documented[1]} != actual {actual[0]}/{actual[1]}"
        )
    sentence = (
        f"All **{actual[0]} of {actual[1]}** record families have a canary"
    )
    if sentence not in text:
        fail(f"docs/TOOLS.md must state: {sentence}")
    check_glossary(canary_by_record)
    return actual


def check_glossary(canary_by_record: dict[str, str]) -> None:
    text = GLOSSARY.read_text()
    start = "<!-- validation-family-inventory:start -->"
    end = "<!-- validation-family-inventory:end -->"
    if text.count(start) != 1 or text.count(end) != 1:
        fail("docs/GLOSSARY.md needs exactly one validation-family inventory")
    inventory = text.split(start, 1)[1].split(end, 1)[0]
    rows = re.findall(
        r"^\| `([a-z][a-z0-9_]*)` \|[^\n]*\| `([a-z][a-z0-9_]*)` \|$",
        inventory,
        re.MULTILINE,
    )
    documented = dict(rows)
    if len(documented) != len(rows):
        fail("docs/GLOSSARY.md lists a validation family more than once")
    if documented != canary_by_record:
        missing = sorted(set(canary_by_record) - set(documented))
        unknown = sorted(set(documented) - set(canary_by_record))
        wrong_exercise = sorted(
            record
            for record in set(documented) & set(canary_by_record)
            if documented[record] != canary_by_record[record]
        )
        details = []
        if missing:
            details.append(f"missing families {', '.join(missing)}")
        if unknown:
            details.append(f"unknown families {', '.join(unknown)}")
        if wrong_exercise:
            details.append(
                "wrong canary exercises for " + ", ".join(wrong_exercise)
            )
        fail("docs/GLOSSARY.md validation-family inventory: " + "; ".join(details))

    definitions = re.findall(
        r"^\*\*([^\n]+)\*\*\n: (.*?)(?=^\*\*|^## |\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    if not definitions:
        fail("docs/GLOSSARY.md has no glossary definitions")
    unsupported = [
        term
        for term, explanation in definitions
        if not re.search(r"\[[^\]]+\]\([^)]+\)", explanation)
        and not re.search(r"\b(?:for example|example:)\b", explanation, re.IGNORECASE)
    ]
    if unsupported:
        fail(
            "docs/GLOSSARY.md definitions need an example or artifact link: "
            + ", ".join(unsupported)
        )


def run(command: list[str], label: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired:
        fail(f"{label} exceeded the 30-second timeout")


def check_guide() -> None:
    text = GUIDE.read_text()
    required = (
        "## 1. Get a working toolchain",
        "./tools/h5explain examples/file.h5",
        "./tools/h5policy --profile untrusted-strict examples/file.h5",
        "H5_ADVISORY_DECODE_FILTER",
        "[H5Lens tutorial](TUTORIAL.md)",
        "[`h5policy` guide](../h5policy/README.md)",
        "[HDF5 format reference](generated/README.md)",
        "[tool guide](TOOLS.md)",
    )
    for fragment in required:
        if fragment not in text:
            fail(f"first-ten-minutes guide lacks {fragment!r}")

    policy = run(
        [str(H5POLICY), "--profile", "untrusted-strict", str(SAMPLE)],
        "h5policy first-ten-minutes command",
    )
    if policy.returncode != 1:
        fail(f"h5policy returned {policy.returncode}, expected 1: {policy.stderr}")
    try:
        report = json.loads(policy.stdout)
    except json.JSONDecodeError as exc:
        fail(f"h5policy did not produce JSON: {exc}")
    if report.get("decision") != "accept_with_warnings":
        fail(f"unexpected sample decision: {report.get('decision')!r}")
    if not report.get("analysis", {}).get("walk_completed"):
        fail("sample policy walk did not complete")
    codes = {
        finding.get("code")
        for finding in report.get("findings", [])
        if isinstance(finding, dict)
    }
    if "H5_ADVISORY_DECODE_FILTER" not in codes:
        fail("sample policy report lacks H5_ADVISORY_DECODE_FILTER")

    inspect = run(
        [str(H5EXPLAIN), "-c", "root", "-c", "ls", str(SAMPLE)],
        "h5explain first-ten-minutes command",
    )
    if inspect.returncode:
        fail(f"h5explain returned {inspect.returncode}: {inspect.stderr}")
    if "DirectChunkData -> 195UL#B" not in inspect.stdout:
        fail("h5explain did not identify DirectChunkData")


def main() -> int:
    canary_count, family_count = check_canary_inventory()
    if not GUIDE.is_file():
        fail("docs/FIRST_10_MINUTES.md is missing")
    check_guide()
    print(
        "QUICKSTART CHECK OK: "
        f"guide commands passed; {canary_count}/{family_count} record families have canaries"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
