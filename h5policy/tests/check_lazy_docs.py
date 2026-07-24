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

"""Tie the lazy-validation narrative to its tracked and live measurements."""

from __future__ import annotations

import ast
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

import yaml


ROOT = Path(__file__).resolve().parents[2]
ARTIFACT = ROOT / "registry/lazy-validation.json"
TOOLS_DOC = ROOT / "TOOLS.md"
LAZY_TOOL = ROOT / "h5policy/tools/h5policy-lazy"
VERIFICATION = ROOT / "registry/verification-coverage.yml"

DETERMINISTIC_FIELDS = (
    "point",
    "physical_bytes",
    "metadata_bytes_seen",
    "walk_operations",
    "chunk_index_refs",
)


def fail(message: str) -> None:
    print(f"LAZY DOC CHECK FAILED: {message}", file=sys.stderr)
    raise SystemExit(1)


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


def normalized(text: str) -> str:
    return " ".join(text.split())


def ladder(report: dict, name: str) -> list[dict]:
    rows = report.get("ladders", {}).get(name)
    if not isinstance(rows, list) or len(rows) < 2:
        fail(f"tracked artifact lacks a usable {name!r} ladder")
    for index, row in enumerate(rows):
        for field in DETERMINISTIC_FIELDS:
            value = row.get(field)
            if isinstance(value, bool) or not isinstance(value, int):
                fail(f"{name}[{index}].{field} is not an integer")
    return rows


def growth(rows: list[dict]) -> float:
    first = rows[0]["physical_bytes"]
    last = rows[-1]["physical_bytes"]
    if first <= 0 or last <= first:
        fail(f"invalid physical byte endpoints: {first}, {last}")
    return last / first


def comma(value: int) -> str:
    return f"{value:,}"


def deterministic(report: dict) -> dict:
    return {
        name: [
            {field: row[field] for field in DETERMINISTIC_FIELDS}
            for row in rows
        ]
        for name, rows in report["ladders"].items()
    }


def check_narrative(report: dict) -> None:
    data = ladder(report, "data")
    filtered = ladder(report, "filtered")
    chunks = ladder(report, "chunks")

    data_growth = round(growth(data))
    filtered_growth = round(growth(filtered))
    data_points = round(data[-1]["point"] / data[0]["point"])
    chunk_points = round(chunks[-1]["point"] / chunks[0]["point"])
    if [row["point"] for row in filtered] != [row["point"] for row in data]:
        fail("filtered and unfiltered element-count ladders differ")

    narrative = normalized(
        section(TOOLS_DOC, "## Lazy-Validation Measurement")
    )
    requirements = (
        f"{comma(data[0]['point'])} → {comma(data[-1]['point'])} elements "
        f"({comma(data_points)}×)",
        f"physical file {comma(data[0]['physical_bytes'])} → "
        f"{comma(data[-1]['physical_bytes'])} bytes "
        f"({comma(data_growth)}×)",
        f"physical file {comma(filtered[0]['physical_bytes'])} → "
        f"{comma(filtered[-1]['physical_bytes'])} bytes "
        f"({comma(filtered_growth)}×)",
        f"chunk count {comma(chunks[0]['point'])} → "
        f"{comma(chunks[-1]['point'])} ({comma(chunk_points)}×)",
        f"exactly {data[0]['metadata_bytes_seen']}/"
        f"{data[0]['walk_operations']}",
        f"{filtered[0]['walk_operations']} → "
        f"{filtered[-1]['walk_operations']}",
        " → ".join(comma(row["walk_operations"]) for row in chunks),
        "[`registry/lazy-validation.json`](registry/lazy-validation.json)",
    )
    missing = [item for item in requirements if item not in narrative]
    if missing:
        fail(
            "TOOLS.md lazy section lacks "
            + ", ".join(repr(item) for item in missing)
        )

    tool_tree = ast.parse(LAZY_TOOL.read_text(), str(LAZY_TOOL))
    tool_help = normalized(ast.get_docstring(tool_tree) or "")
    help_requirements = (
        f"element count growing {comma(data_points)}x",
        f"physical files grow {comma(data_growth)}x",
        f"physical files grow {comma(filtered_growth)}x",
    )
    missing = [item for item in help_requirements if item not in tool_help]
    if missing:
        fail(
            "h5policy-lazy help lacks "
            + ", ".join(repr(item) for item in missing)
        )

    for label, text in (("TOOLS.md", narrative), ("h5policy-lazy help", tool_help)):
        if re.search(r"~?1,?000x", text, re.IGNORECASE):
            fail(f"{label} still contains the stale approximate magnitude")

    verification = yaml.safe_load(VERIFICATION.read_text()) or {}
    expected_ratio = f"{data_growth}x"
    records = verification.get("records", {})
    if not records:
        fail("verification coverage has no records")
    for record, values in records.items():
        entry = values.get("lazy_validation_performance", {})
        if entry.get("status") != "partial":
            fail(f"{record}: lazy validation status is not partial")
        if expected_ratio not in entry.get("note", ""):
            fail(f"{record}: lazy validation note lacks {expected_ratio}")


def check_live_measurement(tracked: dict) -> None:
    try:
        import h5py  # noqa: F401
        import numpy  # noqa: F401
    except ImportError:
        print("LAZY DOC CHECK SKIP: narrative passed; h5py/numpy unavailable")
        return
    if shutil.which("poke") is None:
        print("LAZY DOC CHECK SKIP: narrative passed; GNU poke unavailable")
        return

    with tempfile.TemporaryDirectory(prefix="h5policy-lazy-doc-") as tmp:
        output = Path(tmp) / "lazy.json"
        try:
            result = subprocess.run(
                [str(LAZY_TOOL), "--repeats", "1", "--output", str(output)],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=60,
                check=False,
            )
        except subprocess.TimeoutExpired:
            fail("live h5policy-lazy measurement exceeded 60 seconds")
        if result.returncode:
            fail(
                f"live h5policy-lazy exited {result.returncode}\n"
                f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )
        live = json.loads(output.read_text())

    if live.get("total_violations") != 0:
        fail(f"live measurement has {live.get('total_violations')} violation(s)")
    if deterministic(live) != deterministic(tracked):
        fail("live deterministic ladder fields differ from the tracked artifact")


def main() -> int:
    tracked = json.loads(ARTIFACT.read_text())
    if tracked.get("schema_version") != 1:
        fail(f"unsupported lazy artifact schema {tracked.get('schema_version')!r}")
    if tracked.get("total_violations") != 0 or tracked.get("violations") != []:
        fail("tracked lazy-validation artifact contains violations")

    check_narrative(tracked)
    check_live_measurement(tracked)
    data = ladder(tracked, "data")
    print(
        "LAZY DOC CHECK OK: narrative and live measurement agree at "
        f"{growth(data):.2f}x ({round(growth(data))}x rounded)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
