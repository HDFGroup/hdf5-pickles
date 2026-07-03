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

"""Compare h5policy output against tests/expected/*.yml.

For each spec: run the tool on the fixture and assert the decision, exit code,
required findings (subset), and forbidden outcomes.  Invoked by run.sh, which
sets TESTS_DIR and TOOL in the environment.
"""
import glob
import json
import os
import subprocess
import sys

import yaml

TESTS_DIR = os.environ.get("TESTS_DIR", os.path.dirname(os.path.abspath(__file__)))
TOOL = os.environ["TOOL"]

# Exit codes h5policy is allowed to return; anything else is a crash.
KNOWN_EXITS = {0, 1, 2, 3, 4, 5, 70}
TIMEOUT_S = 30


def run_case(spec):
    path = os.path.join(TESTS_DIR, spec["file"])
    profile = spec.get("profile", "untrusted-strict")
    problems = []

    if not os.path.exists(path):
        return [f"fixture missing: {spec['file']}"]

    try:
        proc = subprocess.run(
            [TOOL, "--profile", profile, "--json", path],
            capture_output=True, text=True, timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return ["timeout"]

    forbidden = set(spec.get("forbidden", []))

    # crash: unknown exit code, or unparseable report.
    if proc.returncode not in KNOWN_EXITS:
        problems.append(f"crash: exit {proc.returncode}: {proc.stderr.strip()[:200]}")
        return problems
    try:
        report = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        problems.append(f"crash: invalid JSON report ({exc})")
        return problems

    if proc.returncode != spec["expected_exit"]:
        problems.append(f"exit {proc.returncode} != {spec['expected_exit']}")
    if report.get("decision") != spec["expected_decision"]:
        problems.append(
            f"decision {report.get('decision')!r} != {spec['expected_decision']!r}")

    codes = {f["code"] for f in report.get("findings", [])}
    for want in spec.get("required_findings", []):
        if want not in codes:
            problems.append(f"missing required finding {want}")

    # Boundary invariants: the oracle must never touch these.  Map the report's
    # boundary flags to the forbidden outcome names.
    boundary = report.get("boundary", {})
    boundary_forbidden = {
        "external_open": "external_file_opens",
        "plugin_load": "plugins",
        "write": "writes",
    }
    for outcome, flag in boundary_forbidden.items():
        if outcome in forbidden and boundary.get(flag, False):
            problems.append(f"forbidden outcome occurred: {outcome}")

    return problems


def main():
    specs = sorted(glob.glob(os.path.join(TESTS_DIR, "expected", "*.yml")))
    if not specs:
        print("no expected specs found", file=sys.stderr)
        return 1

    failures = 0
    for spec_path in specs:
        with open(spec_path) as fh:
            spec = yaml.safe_load(fh)
        name = os.path.splitext(os.path.basename(spec_path))[0]
        problems = run_case(spec)
        if problems:
            failures += 1
            print(f"FAIL {name}")
            for p in problems:
                print(f"     - {p}")
        else:
            print(f"PASS {name}  ({spec['expected_decision']})")

    total = len(specs)
    print(f"\ncorpus: {total - failures}/{total} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
