#!/usr/bin/env python3
"""Exercise byte-path encoding through the complete h5policy JSON stream."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
from urllib.parse import unquote_to_bytes

import h5py


ROOT = Path(__file__).resolve().parents[2]
H5POLICY = os.fsencode(ROOT / "h5policy/tools/h5policy")
PATH_ENCODING = "utf-8-percent-v1"


def check_case(
    directory: bytes,
    file_basename: bytes,
    object_name: bytes,
    expected_object: str,
) -> list[str]:
    problems: list[str] = []
    path = directory + b"/" + file_basename
    with h5py.File(path, "w", libver="earliest") as handle:
        handle.create_dataset(
            object_name, data=list(range(8)), compression="gzip"
        )

    result = subprocess.run(
        [H5POLICY, b"--profile", b"untrusted-strict", b"--json", path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    try:
        text = result.stdout.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        return [f"{file_basename!r}: report is not UTF-8 ({error})"]

    try:
        report = json.loads(text)
    except json.JSONDecodeError as error:
        return [f"{file_basename!r}: report is not JSON ({error})"]

    if result.returncode != 1:
        problems.append(
            f"{file_basename!r}: exit {result.returncode} != 1; "
            f"stderr={result.stderr[:160]!r}"
        )
    if report.get("path_encoding") != PATH_ENCODING:
        problems.append(f"{file_basename!r}: missing path encoding contract")

    encoded_file = report.get("file")
    if not isinstance(encoded_file, str) or unquote_to_bytes(encoded_file) != path:
        problems.append(f"{file_basename!r}: file path does not round-trip")

    findings = report.get("findings", [])
    objects = [
        finding.get("object")
        for finding in findings
        if finding.get("code") == "H5_ADVISORY_DECODE_FILTER"
    ]
    if objects != [expected_object]:
        problems.append(
            f"{file_basename!r}: objects {objects!r} != {[expected_object]!r}"
        )
    elif unquote_to_bytes(objects[0]) != b"/" + object_name:
        problems.append(f"{file_basename!r}: object path does not round-trip")

    return problems


def main() -> int:
    cases = (
        (
            b"input%-caf\xc3\xa9-\x89.h5",
            b"ArrayO\x89Stru\x80tures",
            "/ArrayO%89Stru%80tures",
        ),
        (b"percent.h5", b"Rate%89", "/Rate%2589"),
        (b"utf8.h5", b"caf\xc3\xa9", "/café"),
    )
    problems: list[str] = []
    with tempfile.TemporaryDirectory(prefix="h5policy-path-test-") as temp:
        directory = os.fsencode(temp)
        for file_basename, object_name, expected_object in cases:
            problems.extend(
                check_case(directory, file_basename, object_name, expected_object)
            )

    if problems:
        for problem in problems:
            print(f"FAIL {problem}")
        return 1
    print("PASS report paths are strict UTF-8 JSON and byte-reversible")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
