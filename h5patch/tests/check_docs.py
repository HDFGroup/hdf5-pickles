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

"""Check the h5patch catalog and the root README entry points."""

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
ROOT_README = ROOT / "README.md"
H5PATCH_README = ROOT / "h5patch/README.md"

CATALOG_CLASSES = (
    "HDF5 file signature",
    "superblock base address",
    "superblock file-consistency flags",
    "superblock Jenkins checksums",
    "object-header Jenkins checksums",
    "stored element size",
    "scale-offset and atomic N-bit filter parameters",
    "free-space header serialized-section totals",
    "v1 object-header message counts",
    "symbol-table node (`SNOD`) symbol counts",
    "depth-0 v2 B-tree header total-record counts",
    "trailing Jenkins checksums",
)

ROOT_ENTRY_REQUIREMENTS = (
    "| [`h5patch/`](h5patch/) | Evidence-gated repair planning, application, "
    "and audit logging. |",
    "Create and inspect a repair plan without modifying the input.",
    "./tools/h5patch plan damaged.h5 -o repair.plan.json",
    "./tools/h5patch explain repair.plan.json",
    "[`h5patch`](h5patch/README.md)",
)


def fail(message: str) -> None:
    print(f"H5PATCH DOC CHECK FAILED: {message}", file=sys.stderr)
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


def catalog_bullets(catalog: str) -> list[str]:
    bullets: list[str] = []
    current: list[str] = []

    for line in catalog.splitlines():
        if line.startswith("- "):
            if current:
                bullets.append(normalized(" ".join(current)))
            current = [line[2:]]
        elif current and line.startswith("  "):
            current.append(line.strip())
        elif current:
            bullets.append(normalized(" ".join(current)))
            current = []

    if current:
        bullets.append(normalized(" ".join(current)))
    return bullets


def main() -> int:
    catalog = section(H5PATCH_README, "## Repair Catalog")
    if "authoritative and exhaustive list" not in catalog:
        fail("h5patch/README.md no longer identifies the canonical catalog")

    bullets = catalog_bullets(catalog)
    if len(bullets) != len(CATALOG_CLASSES):
        fail(
            f"canonical catalog has {len(bullets)} repair bullets; "
            f"the documentation contract expects {len(CATALOG_CLASSES)}"
        )

    for repair_class in CATALOG_CLASSES:
        matches = [bullet for bullet in bullets if repair_class in bullet]
        if len(matches) != 1:
            fail(
                f"canonical catalog contains {repair_class!r} "
                f"{len(matches)} time(s), expected once"
            )

    root_readme = normalized(ROOT_README.read_text())
    missing = [
        requirement
        for requirement in ROOT_ENTRY_REQUIREMENTS
        if requirement not in root_readme
    ]
    if missing:
        fail(
            "root README lacks "
            + ", ".join(repr(requirement) for requirement in missing)
        )

    if "## h5patch In Under A Minute" in ROOT_README.read_text():
        fail("root README still contains the retired h5patch summary")

    print(
        f"H5PATCH DOC CHECK OK: {len(bullets)} catalog classes and root entry "
        "points checked"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
