#!/usr/bin/env python3
# Copyright (C) 2026 The HDF Group.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Check drift-prone command help and the h5policy tool-guide inventory."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]


def fail(message: str) -> None:
    print(f"CLI DOCS CHECK FAILED: {message}", file=sys.stderr)
    raise SystemExit(1)


def help_text(command: list[str], cwd: Path) -> str:
    result = subprocess.run(
        command, cwd=cwd, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, timeout=20, check=False)
    if result.returncode != 0:
        fail(f"{' '.join(command)} exited {result.returncode}:\n{result.stdout}")
    if "usage:" not in result.stdout.lower():
        fail(f"{' '.join(command)} did not print a usage line")
    return result.stdout


def require(text: str, fragments: tuple[str, ...], surface: str) -> None:
    for fragment in fragments:
        if fragment not in text:
            fail(f"{surface} lacks {fragment!r}")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="h5lens-cli-docs-") as tmp:
        scratch = Path(tmp)

        h5cve = help_text([str(ROOT / "tools/h5cve"), "--help"], scratch)
        require(h5cve, ("variants", "typed, self-validating variants"),
                "h5cve --help")
        if "variants <case>           [deferred" in h5cve:
            fail("h5cve --help still describes variants as deferred")

        mutate = help_text(
            [str(ROOT / "h5policy/tools/h5mutate"), "--help"], scratch)
        require(mutate, ("object-header continuation", "fractal-heap"),
                "h5mutate --help")
        family = help_text(
            [str(ROOT / "h5policy/tools/h5mutate"), "family", "--help"],
            scratch)
        require(family, ("--family FAMILY", "--verify"),
                "h5mutate family --help")

        corpus = help_text(
            [str(ROOT / "h5policy/tools/h5policy-gencorpus"), "--help"],
            scratch)
        require(corpus, ("[TARGET_DIR]", "h5policy/tests"),
                "h5policy-gencorpus --help")
        if any(scratch.iterdir()):
            fail("h5policy-gencorpus --help wrote files in its working directory")

    guide = (ROOT / "h5policy/docs/README.md").read_text()
    require(
        guide,
        (
            "h5policy-probe", "h5policy-truncate", "h5policy-lazy",
            "h5policy-seamcheck", "h5mutate", "ACCEPT_VS_OLD_REF",
            "`struct_deep`",
        ),
        "h5policy/docs/README.md",
    )

    print("CLI DOCS CHECK OK: help surfaces and tool-guide inventory agree")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
