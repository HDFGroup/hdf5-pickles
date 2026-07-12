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
import tempfile

import yaml

TESTS_DIR = os.environ.get("TESTS_DIR", os.path.dirname(os.path.abspath(__file__)))
TOOL = os.environ["TOOL"]

# Exit codes h5policy is allowed to return; anything else is a crash.
KNOWN_EXITS = {0, 1, 2, 3, 4, 5, 70}
TIMEOUT_S = 30

PROFILE_NAMES = {
    "legacy": "legacy",
    "trusted-fast": "trusted_fast",
    "trusted_fast": "trusted_fast",
    "untrusted-strict": "untrusted_strict",
    "untrusted_strict": "untrusted_strict",
    "forensic": "forensic",
}

PROFILE_OVERRIDE_FIELDS = {
    "resources": {
        "max_accounted_metadata_bytes": "UL",
        "max_logical_dataset_bytes": "UL",
        "max_single_value_bytes": "UL",
        "max_object_count": "UL",
        "max_attribute_count": "UL",
        "max_object_header_chunks": "UL",
        "max_btree_depth": "UL",
        "max_link_traversal_depth": "UL",
        "max_datatype_recursion_depth": "UL",
        "max_filter_parameter_recursion_depth": "UL",
        "max_chunk_count": "UL",
        "max_filter_count": "UL",
        "max_rank": "UL",
        "max_walk_operations": "UL",
        "max_walk_seconds": "UL",
    },
    "heuristics": {
        "min_logical_chunk_bytes": "UL",
        "max_chunks_below_min_logical_bytes": "UL",
        "metadata_ratio_warn_percent": "UL",
        "metadata_ratio_warn_min_bytes": "UL",
        "metadata_ratio_reject_percent": "UL",
        "metadata_ratio_reject_min_bytes": "UL",
    },
    "features": {
        "allow_external_links": "UB",
        "allow_external_storage": "UB",
        "allow_vds": "UB",
        "allow_dynamic_filters": "UB",
        "allow_unknown_messages": "UB",
        "allow_legacy_dangerous_messages": "UB",
    },
    "analysis_defaults": {
        "nonstrict_mapping": "UB",
        "continue_after_corruption": "UB",
        "sweep_unreachable_metadata": "UB",
    },
}


def _poke_string(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _profile_override_commands(overrides):
    if not isinstance(overrides, dict):
        raise ValueError("profile_overrides must be a mapping")

    commands = []
    for group, fields in overrides.items():
        allowed = PROFILE_OVERRIDE_FIELDS.get(group)
        if allowed is None:
            raise ValueError(f"unknown profile override group {group!r}")
        if not isinstance(fields, dict):
            raise ValueError(f"profile override group {group!r} must be a mapping")
        for field, value in fields.items():
            suffix = allowed.get(field)
            if suffix is None:
                raise ValueError(f"unknown profile override {group}.{field}")
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"profile override {group}.{field} must be an integer")
            maximum = 0xff if suffix == "UB" else 0xffffffffffffffff
            if value < 0 or value > maximum:
                raise ValueError(
                    f"profile override {group}.{field} is outside uint{8 if suffix == 'UB' else 64}")
            commands.append(
                f"h5policy_profile_override.{group}.{field} = {value}{suffix}")
    return commands


def _run_with_profile_overrides(path, profile, overrides):
    """Run the ordinary pickle entry point with a cloned, typed test profile."""
    internal_profile = PROFILE_NAMES.get(profile)
    if internal_profile is None:
        raise ValueError(f"unsupported base profile {profile!r}")

    commands = [
        "load h5_policy",
        f'h5policy_profile_name = "{internal_profile}"',
        "h5policy_profile_override = h5policy_clone_profile(h5policy_profile)",
    ]
    commands.extend(_profile_override_commands(overrides))
    commands.extend([
        "h5policy_profile_override_enabled = 1",
        f'h5policy_file_name = "{_poke_string(path)}"',
        'h5policy_mapping_arg = ""',
        'h5policy_continue_arg = ""',
        "h5policy_run",
        ".exit 0",
    ])

    cmd_path = None
    try:
        with tempfile.NamedTemporaryFile(
                mode="w", prefix="h5policy-test-", suffix=".pk",
                delete=False) as command_file:
            command_file.write("\n".join(commands) + "\n")
            cmd_path = command_file.name

        overlay_dir = os.path.dirname(TESTS_DIR)
        repo_dir = os.path.dirname(overlay_dir)
        env = os.environ.copy()
        load_path = [os.path.join(overlay_dir, "pickles"),
                     os.path.join(repo_dir, "pickles")]
        if env.get("POKE_LOAD_PATH"):
            load_path.append(env["POKE_LOAD_PATH"])
        env["POKE_LOAD_PATH"] = os.pathsep.join(load_path)

        poke = subprocess.run(
            ["poke", "--quiet", "-s", cmd_path],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, timeout=TIMEOUT_S, env=env)
    finally:
        if cmd_path is not None:
            os.unlink(cmd_path)

    logical_exit = None
    report_lines = []
    for line in poke.stdout.splitlines():
        if line.startswith("__H5POLICY_EXIT_CODE="):
            logical_exit = int(line.split("=", 1)[1])
        else:
            report_lines.append(line)

    output = "\n".join(report_lines) + "\n"
    if logical_exit is None:
        return subprocess.CompletedProcess(
            poke.args, poke.returncode or 70, output, output)
    return subprocess.CompletedProcess(poke.args, logical_exit, output, "")


def run_case(spec):
    path = os.path.join(TESTS_DIR, spec["file"])
    profile = spec.get("profile", "untrusted-strict")
    problems = []

    if not os.path.exists(path) and not spec.get("allow_missing_file", False):
        return [f"fixture missing: {spec['file']}"]

    try:
        if "profile_overrides" in spec:
            proc = _run_with_profile_overrides(
                path, profile, spec["profile_overrides"])
        else:
            proc = subprocess.run(
                [TOOL, "--profile", profile, "--json", path],
                capture_output=True, text=True, timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return ["timeout"]
    except (OSError, ValueError) as exc:
        return [f"invalid test configuration: {exc}"]

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
    for forbidden_code in spec.get("forbidden_findings", []):
        if forbidden_code in codes:
            problems.append(f"forbidden finding present {forbidden_code}")

    if "expected_mapping_mode" in spec:
        got = report.get("mapping_mode")
        if got != spec["expected_mapping_mode"]:
            problems.append(
                f"mapping mode {got!r} != {spec['expected_mapping_mode']!r}")

    metrics = report.get("metrics", {})
    for metric, want in spec.get("expected_metrics", {}).items():
        got = metrics.get(metric)
        if got != want:
            problems.append(f"metric {metric}={got!r} != {want!r}")

    features = report.get("features", {})
    for feature, want in spec.get("expected_features", {}).items():
        got = features.get(feature)
        if got != want:
            problems.append(f"feature {feature}={got!r} != {want!r}")

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
