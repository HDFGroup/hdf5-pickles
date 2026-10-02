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

"""Regression check for h5cve's variants-seed provenance.

`h5cve variants` stores the seed path in two case.yml fields (`fuzz_seed` and
`variants.seed`).  They used to be written as absolute host paths, which made
every bundle fail `check_hygiene.py` (and leaked one workstation's directory
layout into a record meant to be portable).  The fix routes both through
`portable_path()` at emission and rehydrates the stored value back to an
absolute path on read.  This test pins both halves so the pair cannot silently
regress to absolute emission again.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import os
import subprocess as _subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def _load_h5cve():
    """Exec tools/h5cve as a module to reach its functions without __main__."""
    src = (ROOT / "tools" / "h5cve").read_text()
    ns = {"__name__": "h5cve_under_test",
          "__file__": str(ROOT / "tools" / "h5cve")}
    sys.path.insert(0, str(ROOT / "tools"))
    try:
        exec(compile(src, str(ROOT / "tools" / "h5cve"), "exec"), ns)
    finally:
        sys.path.pop(0)
    return ns


def fail(message: str) -> None:
    print(f"H5CVE PORTABLE-SEED TEST FAILED: {message}", file=sys.stderr)
    raise SystemExit(1)


class _FakeMutate:
    """Stand in for the h5mutate subprocess so the test needs no real tool.

    cmd_variants only reads returncode/stdout/stderr and then scans the output
    directory for *.recipe.yml; an empty success is enough to reach the seed
    emission, which is the behaviour under test.
    """

    @staticmethod
    def run(*_args, **_kwargs):
        return _subprocess.CompletedProcess(_args, 0, stdout="", stderr="")


def _drive_variants(ns, bundle, seed_arg):
    """Call the real cmd_variants with h5mutate stubbed; return the saved case."""
    real = ns["subprocess"]
    ns["subprocess"] = _FakeMutate
    try:
        ns["cmd_variants"](SimpleNamespace(case=str(bundle), seed=seed_arg))
    finally:
        ns["subprocess"] = real
    return ns["yaml"].safe_load((bundle / "case.yml").read_text())


def _assert_portable(value, label):
    if not isinstance(value, str) or not value:
        fail(f"{label} was not emitted as a path: {value!r}")
    if os.path.isabs(value):
        fail(f"{label} was emitted as an absolute host path: {value!r}")
    if value.startswith("..") or os.sep + "home" + os.sep in os.sep + value:
        fail(f"{label} leaked a host directory: {value!r}")


def main() -> int:
    ns = _load_h5cve()
    portable_path = ns["portable_path"]
    rehydrate = ns["_rehydrate_seed"]

    with tempfile.TemporaryDirectory() as tmp:
        bundle = Path(tmp) / "bundle"
        bundle.mkdir()
        (bundle / "input.h5").write_bytes(b"\x89HDF\r\n\x1a\n")  # content irrelevant
        (bundle / "case.yml").write_text("id: test\nfuzz_seed: null\n")

        # End-to-end: the real cmd_variants must emit BOTH seed fields portably.
        # This is the call site that regressed, not just the helper it should
        # use -- a helper-only test would pass even if cmd_variants stopped
        # calling it.
        case = _drive_variants(ns, bundle, seed_arg=None)
        _assert_portable(case.get("fuzz_seed"), "fuzz_seed (default seed)")
        _assert_portable(case.get("variants", {}).get("seed"),
                         "variants.seed (default seed)")

        # A foreign --seed (outside any repo) must collapse to a basename, never
        # the directory it came from.
        foreign = Path(tmp) / "external" / "specimen.h5"
        foreign.parent.mkdir()
        foreign.write_bytes(b"\x89HDF\r\n\x1a\n")
        case = _drive_variants(ns, bundle, seed_arg=str(foreign))
        for label in ("fuzz_seed", None):
            val = case["fuzz_seed"] if label else case["variants"]["seed"]
            _assert_portable(val, f"{label or 'variants.seed'} (foreign seed)")
        if "/" in case["fuzz_seed"]:
            fail(f"foreign seed kept a directory: {case['fuzz_seed']!r}")

    # The rehydrate half: a stored basename is recovered against the bundle dir,
    # and an unlocatable one yields None so the caller falls back to input.h5.
    with tempfile.TemporaryDirectory() as tmp:
        cdir = Path(tmp)
        (cdir / "input.h5").write_bytes(b"x")
        if os.path.realpath(rehydrate("input.h5", str(cdir))) != \
                os.path.realpath(cdir / "input.h5"):
            fail("basename did not rehydrate against the bundle directory")
        if rehydrate("not_a_real_seed_xyz.h5", str(cdir)) is not None:
            fail("missing seed should rehydrate to None")
        if rehydrate(None, str(cdir)) is not None:
            fail("absent seed should rehydrate to None")

    # A foreign absolute path collapses to a bare basename (unit guard on the
    # emitter the call site relies on).
    if portable_path("/some/external/store/specimen.h5") != "specimen.h5":
        fail("portable_path did not reduce a foreign path to its basename")

    print("H5CVE PORTABLE-SEED TEST OK: cmd_variants emits both seed fields "
          "portably and rehydrates a stored seed for re-runs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
