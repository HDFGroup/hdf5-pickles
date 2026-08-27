#!/usr/bin/env python3
# Copyright (C) 2026 The HDF Group.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Keep the documented marker names, groups, and descriptions executable."""

from __future__ import annotations

from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]


def fail(message: str) -> None:
    print(f"MARKER DOCS CHECK FAILED: {message}", file=sys.stderr)
    raise SystemExit(1)


def source_markers() -> dict[str, tuple[str, str]]:
    source = (ROOT / "src/h5markers.cpp").read_text()
    entries = re.findall(
        r'\{"([^"]+)",\s*"([^"]+)",\s*"(HDF5|Onion)",', source)
    if not entries:
        fail("could not parse src/h5markers.cpp marker table")
    return {name: (description, group) for name, description, group in entries}


def documented_markers() -> dict[str, tuple[str, str]]:
    result: dict[str, tuple[str, str]] = {}
    group = ""
    for line in (ROOT / "docs/MARKERS.md").read_text().splitlines():
        if line == "## HDF5 file format markers":
            group = "HDF5"
            continue
        if line == "## Onion revision-history markers":
            group = "Onion"
            continue
        match = re.match(r"^- `([^`]+)`(?: = `[^`]+`)? - (.+)$", line)
        if match and group:
            name, description = match.groups()
            result[name] = (description, group)
    if not result:
        fail("could not parse docs/MARKERS.md inventory")
    return result


def main() -> int:
    source = source_markers()
    documented = documented_markers()
    def agrees(name: str) -> bool:
        source_description, source_group = source[name]
        doc_description, doc_group = documented[name]
        return (source_group == doc_group
                and (doc_description == source_description
                     or doc_description.startswith(source_description + " (")))

    if source.keys() != documented.keys() or not all(agrees(n) for n in source):
        missing = sorted(source.keys() - documented.keys())
        extra = sorted(documented.keys() - source.keys())
        changed = sorted(
            name for name in source.keys() & documented.keys()
            if not agrees(name))
        fail(f"inventory drift: missing={missing} extra={extra} changed={changed}")
    print(f"MARKER DOCS CHECK OK: {len(source)} markers match the scanner")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
