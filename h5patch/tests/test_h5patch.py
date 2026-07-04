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

import json
import os
import shutil
import subprocess
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
H5PATCH = os.path.join(REPO, "h5patch", "tools", "h5patch")
H5POLICY = os.path.join(REPO, "h5policy", "tools", "h5policy")


def run(args, **kwargs):
    proc = subprocess.run(args, capture_output=True, text=True, **kwargs)
    if proc.returncode != 0:
        raise AssertionError(
            f"{args} failed with {proc.returncode}\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )
    return proc


def assert_accept(path):
    proc = run([H5POLICY, "--profile", "untrusted-strict", "--json", path])
    report = json.loads(proc.stdout)
    assert report["decision"] in ("accept", "accept_with_warnings"), report


def corrupt_first_ohdr_checksum(path):
    raw = bytearray(open(path, "rb").read())
    off = raw.find(b"OHDR")
    if off < 0 or raw[off + 4] != 2:
        raise AssertionError("fixture lacks a v2 object header")
    flags = raw[off + 5]
    cursor = off + 6
    if flags & (1 << 5):
        cursor += 16
    if flags & (1 << 4):
        cursor += 4
    size_width = 1 << (flags & 3)
    chunk_size = int.from_bytes(raw[cursor:cursor + size_width], "little")
    chksum_off = cursor + size_width + chunk_size
    raw[chksum_off] ^= 0x80
    with open(path, "wb") as fh:
        fh.write(raw)


def test_signature_repair(tmp):
    src = os.path.join(REPO, "h5policy", "tests", "valid", "empty.h5")
    damaged = os.path.join(tmp, "bad_signature.h5")
    repaired = os.path.join(tmp, "signature_repaired.h5")
    plan = os.path.join(tmp, "signature.plan.json")
    log = os.path.join(tmp, "signature.log.jsonl")
    shutil.copyfile(src, damaged)
    raw = bytearray(open(damaged, "rb").read())
    raw[0] ^= 0xFF
    open(damaged, "wb").write(raw)

    run([H5PATCH, "plan", damaged, "-o", plan])
    spec = json.load(open(plan))
    assert [a["kind"] for a in spec["actions"]] == ["replace_bytes"]

    run([H5PATCH, "apply", damaged, plan, "--output", repaired, "--log", log])
    assert_accept(repaired)
    assert os.path.getsize(log) > 0


def test_object_header_checksum_repair(tmp):
    src = os.path.join(REPO, "h5policy", "tests", "valid", "chunk_ext_array.h5")
    damaged = os.path.join(tmp, "bad_ohdr_checksum.h5")
    repaired = os.path.join(tmp, "ohdr_repaired.h5")
    plan = os.path.join(tmp, "ohdr.plan.json")
    shutil.copyfile(src, damaged)
    corrupt_first_ohdr_checksum(damaged)

    run([H5PATCH, "plan", damaged, "-o", plan])
    spec = json.load(open(plan))
    assert any(a["target"]["structure"] == "object_header_v2" for a in spec["actions"])

    run([H5PATCH, "apply", damaged, plan, "--output", repaired])
    assert_accept(repaired)


def main():
    with tempfile.TemporaryDirectory(prefix="h5patch-test-") as tmp:
        test_signature_repair(tmp)
        test_object_header_checksum_repair(tmp)
    print("h5patch tests passed")


if __name__ == "__main__":
    main()
