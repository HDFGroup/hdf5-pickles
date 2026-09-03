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

"""Re-measure the H5Tdecode half of the uncapped datatype-recursion defect.

registry/cases/datatype-nesting-depth-uncapped.yml records two halves.  The
object-header half is covered by cve/dtype_unbounded_recursion.h5, whose depth is
capped at 8187 by the two-byte object-header message size -- which is why it
cannot crash a default stack and why its expectation permits only `unexercised`
and `verified`.

THIS CHECK COVERS THE OTHER HALF, which no fixture can: H5Tdecode takes a buffer
from the APPLICATION, so no object header and no message-size field bounds the
nesting.  There is nothing to put in the corpus -- the input is memory, not a
file -- so it lives here as a unit-style probe instead.

WHAT IT IS FOR, and it is not "assert the crash forever".  The recorded state is
that libhdf5 has no depth cap, so a deep type either decodes or dies.  This check
distinguishes three outcomes and fails on the two that mean the record is stale:

  crashed          -> the recorded state.  PASS.
  cleanly rejected -> libhdf5 GAINED A DEPTH CAP.  FAIL, loudly: the defect is
                      fixed and the record needs updating.  This is the outcome
                      worth catching, and no corpus fixture can catch it.
  decoded fine     -> the depth/stack margin no longer holds on this machine, so
                      the measurement has quietly stopped testing anything.
                      FAIL as inconclusive rather than pass vacuously.

Robustness: the check sets the child's stack itself rather than inheriting the
machine's, and picks depths with a very wide margin around the ~448 bytes/frame
measured for this shape -- the shallow case needs roughly 1/10th of the stack and
the deep case roughly 45x it.  A shallow-case crash means the stack is too small
for libhdf5 at all, which is reported as such instead of being blamed on depth.
"""

from __future__ import annotations

import os
from pathlib import Path
import resource
import shutil
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]

# Measured for the single-child VLen shape on x86-64; see the record's
# `measured.stack_cost`.  Only used to choose margins, never asserted.
BYTES_PER_FRAME = 448
STACK_KIB = 1024
SHALLOW_DEPTH = 200                      # ~90 KiB of stack: ~1/10th of the limit
DEEP_DEPTH = 100_000                     # ~45 MiB of stack: ~45x the limit

PROBE_C = r"""
/* Decode an encoded datatype of a given nesting depth via the bounded, modern
 * entry point, called correctly with the true buffer length. */
#include <hdf5.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(int argc, char **argv)
{
    if (argc != 2) return 2;
    long depth = atol(argv[1]);
    /* H5O_DTYPE_ID, H5T_ENCODE_VERSION, then `depth` VLen wrappers and an
     * 8-bit-integer leaf.  Byte layout documented in the registry case record. */
    static const unsigned char WRAP[8] = {0x19, 0, 0, 0, 0x10, 0, 0, 0};
    static const unsigned char LEAF[12] = {0x10, 0, 0, 0, 1, 0, 0, 0, 0, 0, 8, 0};
    size_t n = 2 + (size_t)depth * sizeof WRAP + sizeof LEAF;
    unsigned char *buf = malloc(n);
    if (buf == NULL) return 2;
    buf[0] = 0x03;
    buf[1] = 0x00;
    for (long i = 0; i < depth; i++)
        memcpy(buf + 2 + (size_t)i * sizeof WRAP, WRAP, sizeof WRAP);
    memcpy(buf + 2 + (size_t)depth * sizeof WRAP, LEAF, sizeof LEAF);

    hid_t t = H5Tdecode2(buf, n);
    /* Print the verdict before closing, so a crash in teardown is still
     * attributable to the decode having succeeded. */
    printf("%s\n", t >= 0 ? "decoded" : "rejected");
    fflush(stdout);
    if (t >= 0) H5Tclose(t);
    free(buf);
    return 0;
}
"""


def skip(reason: str) -> int:
    print(f"  skipped: {reason}")
    return 0


def fail(message: str) -> int:
    print(f"  FAIL: {message}")
    return 1


def run_at_depth(binary: Path, depth: int) -> tuple[str, int]:
    """Run the probe with a fixed stack.  Returns (verdict, returncode)."""
    limit = STACK_KIB * 1024

    def shrink_stack() -> None:
        resource.setrlimit(resource.RLIMIT_STACK, (limit, limit))

    try:
        done = subprocess.run(
            [str(binary), str(depth)],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            preexec_fn=shrink_stack, timeout=300, check=False)
    except (OSError, ValueError) as exc:      # host refuses RLIMIT_STACK
        return f"unsettable:{exc}", -1
    verdict = done.stdout.decode(errors="replace").strip().splitlines()
    return (verdict[-1] if verdict else ""), done.returncode


def main() -> int:
    h5cc = shutil.which("h5cc")
    if h5cc is None:
        return skip("h5cc unavailable")

    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "tdecode_depth.c"
        src.write_text(PROBE_C)
        binary = Path(tmp) / "tdecode_depth"
        build = subprocess.run(
            [h5cc, "-O1", "-o", str(binary), str(src)],
            capture_output=True, text=True, timeout=300, check=False)
        if build.returncode or not binary.exists():
            return skip(f"probe build failed: {build.stderr.strip()[:160]}")

        # 1. Shallow control.  This proves the buffer construction is decodable
        #    and that libhdf5 itself fits the chosen stack, so a deep-case crash
        #    can be attributed to the depth rather than to the stack being tiny.
        verdict, rc = run_at_depth(binary, SHALLOW_DEPTH)
        if verdict.startswith("unsettable"):
            return skip(f"host refuses RLIMIT_STACK ({verdict.split(':', 1)[1][:80]})")
        if rc != 0 or verdict != "decoded":
            return fail(
                f"shallow control failed: depth {SHALLOW_DEPTH} at {STACK_KIB} KiB "
                f"gave verdict={verdict!r} rc={rc}.  Expected a clean decode -- "
                f"either the encoded-buffer layout is wrong or {STACK_KIB} KiB is "
                f"too small for libhdf5 itself, and neither is a statement about "
                f"nesting depth")

        # 2. The measurement.  ~45x the stack the chosen depth needs.
        verdict, rc = run_at_depth(binary, DEEP_DEPTH)
        needed_mib = DEEP_DEPTH * BYTES_PER_FRAME / (1024 * 1024)
        if verdict == "rejected":
            return fail(
                f"libhdf5 REJECTED a {DEEP_DEPTH}-deep datatype instead of "
                f"exhausting the stack, so it has gained a nesting-depth limit.  "
                f"That is a FIX, not a regression: re-measure and update "
                f"registry/cases/datatype-nesting-depth-uncapped.yml, and revisit "
                f"the expectation for cve/dtype_unbounded_recursion.h5")
        if verdict == "decoded":
            return fail(
                f"libhdf5 decoded a {DEEP_DEPTH}-deep datatype at a {STACK_KIB} KiB "
                f"stack, which needs about {needed_mib:.0f} MiB at the measured "
                f"~{BYTES_PER_FRAME} bytes/frame.  The margin no longer holds, so "
                f"this check has stopped measuring anything -- raise DEEP_DEPTH or "
                f"re-measure BYTES_PER_FRAME rather than leaving it passing")
        if rc >= 0:
            return fail(f"unexpected probe outcome: verdict={verdict!r} rc={rc}")

    print(f"PASS H5Tdecode2 has no nesting-depth limit: depth {SHALLOW_DEPTH} "
          f"decodes and depth {DEEP_DEPTH} exhausts a {STACK_KIB} KiB stack "
          f"(signal {-rc})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
