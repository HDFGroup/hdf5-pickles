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

"""Re-measure the WRITE-path consequence of the local-heap free-list defects.

registry/cases/local-heap-free-list-bound-wraps.yml and
registry/cases/local-heap-failed-load-retains-image.yml both record a memory
error, and until this check existed neither had anything asserting it.  The
reason is structural rather than an oversight: the corpus runner, the
exact-build probe and the differential harness are all READ-ONLY by design, and
the consequence here appears only under H5F_ACC_RDWR.  A read-only traversal
never acts on the admitted free-list node.  So a libhdf5 regression -- or a
libhdf5 FIX -- was invisible to every phase of this suite.

WHAT IT MEASURES.  malformed/heap_free_list_size_wrap.h5 carries a free-list
node whose declared size wraps the additive bound at src/H5HLcache.c:258 and is
therefore published into heap->freelist.  One H5Gcreate2 then allocates from
that node, and the heap image is indexed past its allocation:

    H5HL_insert          src/H5HL.c:690    memcpy of the link NAME past the end
    H5HL__fl_serialize   src/H5HLcache.c:308-:310   the free-list encode, at flush

THE NAME LENGTH IS PART OF THE MEASUREMENT, not an incidental parameter.  The
overflow needs the residual node to start past the end of the segment, so it
depends on `offset + need` against dblk_size -- 88 for this fixture.  Measured:
a 40-character name completes cleanly and a 56-character one faults.  Both are
checked here, because a fixture that stopped faulting for a reason unrelated to
libhdf5 (a regenerated corpus with a larger heap, say) would otherwise report a
silent pass.

THREE OUTCOMES, and only one is a pass:

  the long name faults      -> the recorded state.  PASS.
  the long name completes   -> either libhdf5 bounds the node now -- a real fix,
                               and the thing this check exists to notice -- or
                               the fixture's geometry drifted and the length no
                               longer crosses the bound.  FAIL, and say both.
  a CONTROL misbehaves      -> the measurement is not about the defect at all.
                               FAIL as inconclusive rather than pass vacuously.

The controls are a valid old-style group (same operation, same name length, must
complete) and the same malformed fixture with the short name (must complete).
Together they pin the fault to the length crossing the bound on a file whose
heap is otherwise usable.

Every run works on a COPY: the operation writes, and a fixture the suite
regenerates must not be mutated underneath the other phases.
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

TESTS = Path(__file__).resolve().parent
MALFORMED = TESTS / "malformed" / "heap_free_list_size_wrap.h5"
VALID = TESTS / "valid" / "old_style_group.h5"

SHORT_NAME = 40      # measured: completes on this fixture
LONG_NAME = 56       # measured: faults on this fixture

PROBE_C = r"""
/* Open for writing and create one group.  The name length is the parameter that
 * decides whether the admitted free-list node overflows its allocation. */
#include <hdf5.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(int argc, char **argv)
{
    if (argc != 3) return 2;
    long n = atol(argv[2]);
    char *name = malloc((size_t)n + 2);
    if (name == NULL) return 2;
    name[0] = '/';
    memset(name + 1, 'g', (size_t)n);
    name[n + 1] = '\0';

    H5Eset_auto2(H5E_DEFAULT, NULL, NULL);   /* a refusal is a result, not noise */

    hid_t f = H5Fopen(argv[1], H5F_ACC_RDWR, H5P_DEFAULT);
    if (f < 0) { printf("open-refused\n"); return 0; }
    hid_t g = H5Gcreate2(f, name, H5P_DEFAULT, H5P_DEFAULT, H5P_DEFAULT);
    if (g >= 0) H5Gclose(g);
    /* The free-list encode happens in the flush, so the close is part of the
     * measurement and the verdict must not be printed before it. */
    H5Fclose(f);
    printf("%s\n", g >= 0 ? "created" : "create-refused");
    free(name);
    return 0;
}
"""


def skip(reason: str) -> int:
    print(f"  skipped: {reason}")
    return 0


def fail(message: str) -> int:
    print(f"  FAIL: {message}")
    return 1


def run(binary: Path, fixture: Path, name_len: int, tmp: Path):
    """Run the probe on a COPY.  Returns (verdict, returncode)."""
    work = tmp / f"{fixture.stem}-{name_len}.h5"
    shutil.copy(fixture, work)
    done = subprocess.run([str(binary), str(work), str(name_len)],
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                          timeout=300, check=False)
    out = done.stdout.decode(errors="replace").strip().splitlines()
    return (out[-1] if out else ""), done.returncode


def main() -> int:
    print("== local-heap write path (RDWR consequence of the free-list defects) ==")
    h5cc = shutil.which("h5cc")
    if h5cc is None:
        return skip("h5cc unavailable")
    for fixture in (MALFORMED, VALID):
        if not fixture.is_file():
            return skip(f"{fixture.name} not in the corpus")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        src = tmp / "heap_write.c"
        src.write_text(PROBE_C)
        binary = tmp / "heap_write"
        build = subprocess.run([h5cc, "-O1", "-o", str(binary), str(src)],
                               capture_output=True, text=True, timeout=300,
                               check=False)
        if build.returncode or not binary.exists():
            return skip(f"probe build failed: {build.stderr.strip()[:160]}")

        # CONTROL 1: the same operation on a valid old-style group.  If this
        # faults, the machine or the harness is at fault and nothing below is
        # about the defect.
        verdict, rc = run(binary, VALID, LONG_NAME, tmp)
        if rc < 0 or verdict != "created":
            return fail(f"the VALID control did not complete: {VALID.name} "
                        f"returned rc={rc} verdict={verdict!r}.  The write path "
                        f"itself is broken here, so this check cannot speak to "
                        f"the defect.")

        # CONTROL 2: the malformed fixture with a name too short to cross the
        # bound.  Proves the file opens and its heap is usable, so a fault at
        # the longer name is about the length and not about the file.
        verdict, rc = run(binary, MALFORMED, SHORT_NAME, tmp)
        if rc < 0 or verdict != "created":
            return fail(f"the SHORT-NAME control did not complete: "
                        f"{MALFORMED.name} at {SHORT_NAME} characters returned "
                        f"rc={rc} verdict={verdict!r}.  Expected a clean create; "
                        f"the fixture's geometry may have changed.")

        # THE MEASUREMENT.
        verdict, rc = run(binary, MALFORMED, LONG_NAME, tmp)
        if rc < 0:
            print(f"  PASS libhdf5 still writes past the heap allocation "
                  f"({MALFORMED.name}, {LONG_NAME}-character name, signal {-rc})")
            return 0
        return fail(
            f"{MALFORMED.name} at {LONG_NAME} characters completed cleanly "
            f"(rc={rc} verdict={verdict!r}).\n"
            f"        Two readings, and they need telling apart before this is "
            f"treated as a harness bug:\n"
            f"          * libhdf5 now bounds the free-list node -- a real fix, "
            f"and the outcome this check exists to notice.  Re-measure "
            f"src/H5HLcache.c:258 and update "
            f"registry/cases/local-heap-free-list-bound-wraps.yml.\n"
            f"          * the fixture's heap geometry drifted, so "
            f"{LONG_NAME} characters no longer crosses the segment bound and "
            f"the check has stopped testing anything.  Compare dblk_size "
            f"against the generator.")


if __name__ == "__main__":
    sys.exit(main())
