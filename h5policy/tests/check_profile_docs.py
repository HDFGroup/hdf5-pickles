#!/usr/bin/env python3
# Copyright (C) 2026 The HDF Group.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Compare H5PolicyProfile's documented preset tables with the pickle."""

from __future__ import annotations

import ast
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "h5policy/pickles/h5_profiles.pk"
DOC = ROOT / "h5policy/docs/H5PolicyProfile.md"
PROFILES = (
    ("H5_UNTRUSTED_STRICT", "untrusted-strict"),
    ("H5_FORENSIC", "forensic"),
    ("H5_TRUSTED_FAST", "trusted-fast"),
    ("H5_LEGACY", "legacy"),
)
UINT64_MAX = (1 << 64) - 1


def fail(message: str) -> None:
    print(f"PROFILE DOCS CHECK FAILED: {message}", file=sys.stderr)
    raise SystemExit(1)


def eval_product(expression: str) -> int:
    cleaned = re.sub(r"(?<=\w)(?:UL|UB)\b", "", expression.strip())
    tree = ast.parse(cleaned, mode="eval")

    def visit(node: ast.AST) -> int:
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, int):
            return node.value
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult):
            return visit(node.left) * visit(node.right)
        raise ValueError(f"unsupported preset expression {expression!r}")

    return visit(tree)


def source_profiles() -> dict[str, dict[str, int]]:
    text = re.sub(r"/\*.*?\*/", "", SOURCE.read_text(), flags=re.DOTALL)
    positions = []
    for symbol, profile in PROFILES:
        match = re.search(rf"\bvar\s+{symbol}\s*=", text)
        if match is None:
            fail(f"missing pickle preset {symbol}")
        positions.append((match.start(), profile))
    positions.append((len(text), ""))

    result: dict[str, dict[str, int]] = {}
    for index, (_, profile) in enumerate(positions[:-1]):
        block = " ".join(
            text[positions[index][0]:positions[index + 1][0]].split())
        assignments = re.findall(
            r"\b([a-z][a-z0-9_]*)\s*=\s*([^,{}]+)(?=,|\s*})", block)
        result[profile] = {
            field: eval_product(value) for field, value in assignments
        }
    return result


def doc_value(value: str) -> int:
    value = value.strip().replace(",", "").replace("`", "")
    if value == "disabled":
        return 0
    if value == "UINT64_MAX":
        return UINT64_MAX
    sized = re.fullmatch(r"(\d+) (KiB|MiB|GiB|TiB)", value)
    if sized:
        powers = {"KiB": 1, "MiB": 2, "GiB": 3, "TiB": 4}
        return int(sized.group(1)) * 1024 ** powers[sized.group(2)]
    if value.isdigit():
        return int(value)
    raise ValueError(f"unsupported documented preset {value!r}")


def documented_profiles(fields: set[str]) -> dict[str, dict[str, int]]:
    result = {profile: {} for _, profile in PROFILES}
    row = re.compile(
        r"^\| `([^`]+)` \| ([^|]+) \| ([^|]+) \| ([^|]+) \| ([^|]+) \|$")
    for line in DOC.read_text().splitlines():
        match = row.match(line)
        if match is None or match.group(1) not in fields:
            continue
        field = match.group(1)
        for (_, profile), value in zip(PROFILES, match.groups()[1:]):
            result[profile][field] = doc_value(value)
    return result


def main() -> int:
    source = source_profiles()
    fields = set(source["untrusted-strict"])
    if any(set(values) != fields for values in source.values()):
        fail("pickle presets do not initialize the same fields")
    documented = documented_profiles(fields)
    for profile in documented:
        missing = sorted(fields - documented[profile].keys())
        if missing:
            fail(f"{profile} table lacks fields: {', '.join(missing)}")
        changed = sorted(
            field for field in fields
            if source[profile][field] != documented[profile][field])
        if changed:
            details = ", ".join(
                f"{field}={documented[profile][field]} "
                f"(pickle {source[profile][field]})" for field in changed)
            fail(f"{profile} preset drift: {details}")
    print(
        f"PROFILE DOCS CHECK OK: {len(PROFILES)} profiles and "
        f"{len(fields)} fields match the pickle")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
