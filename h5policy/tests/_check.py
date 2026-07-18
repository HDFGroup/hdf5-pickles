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

For each spec: run the tool on the fixture and assert the report schema,
geometry invariants, decision, exit code, required findings (subset), and
forbidden outcomes.  Invoked by run.sh, which sets TESTS_DIR and TOOL in the
environment.
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


def _location_matches(location, expected, fixture_bytes):
    """Match a location subset and, optionally, its little-endian bytes."""
    for key, value in expected.items():
        if key == "little_endian_value":
            continue
        if location.get(key) != value:
            return False
    if "little_endian_value" not in expected:
        return True
    offset = location.get("offset")
    length = location.get("length")
    if (fixture_bytes is None or isinstance(offset, bool)
            or not isinstance(offset, int) or isinstance(length, bool)
            or not isinstance(length, int) or offset < 0 or length <= 0
            or offset + length > len(fixture_bytes)):
        return False
    encoded = int.from_bytes(fixture_bytes[offset:offset + length], "little")
    return encoded == expected["little_endian_value"]


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
            if spec.get("mode_flags"):
                raise ValueError(
                    "mode_flags cannot be combined with profile_overrides")
            proc = _run_with_profile_overrides(
                path, profile, spec["profile_overrides"])
        else:
            mode_flags = spec.get("mode_flags", [])
            if (not isinstance(mode_flags, list)
                    or not all(isinstance(flag, str) for flag in mode_flags)):
                raise ValueError("mode_flags must be a list of strings")
            proc = subprocess.run(
                [TOOL, "--profile", profile, "--json", *mode_flags, path],
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

    schema_version = report.get("schema_version")
    if (isinstance(schema_version, bool)
            or not isinstance(schema_version, int)
            or schema_version != 1):
        problems.append(f"schema_version {schema_version!r} != 1")

    geometry = report.get("geometry")
    if not isinstance(geometry, dict):
        problems.append("missing file geometry")
        geometry = {}
    geometry_fields = (
        "physical_bytes", "declared_eoa", "effective_ceiling",
        "trailing_bytes",
    )
    for field in geometry_fields:
        if field not in geometry:
            problems.append(f"geometry.{field} is missing")
            continue
        value = geometry[field]
        if (value is not None
                and (isinstance(value, bool) or not isinstance(value, int)
                     or value < 0)):
            problems.append(
                f"geometry.{field} is not a non-negative integer or null")

    physical = geometry.get("physical_bytes")
    declared = geometry.get("declared_eoa")
    ceiling = geometry.get("effective_ceiling")
    trailing = geometry.get("trailing_bytes")
    if isinstance(physical, int) and not isinstance(physical, bool):
        if declared is None:
            if ceiling != physical:
                problems.append(
                    f"geometry.effective_ceiling={ceiling!r} != physical_bytes {physical}")
            if trailing is not None:
                problems.append(
                    "geometry.trailing_bytes must be null without declared_eoa")
        elif isinstance(declared, int) and not isinstance(declared, bool):
            want_ceiling = min(physical, declared)
            want_trailing = max(physical - declared, 0)
            if ceiling != want_ceiling:
                problems.append(
                    f"geometry.effective_ceiling={ceiling!r} != {want_ceiling}")
            if trailing != want_trailing:
                problems.append(
                    f"geometry.trailing_bytes={trailing!r} != {want_trailing}")
    elif physical is None:
        for field in ("declared_eoa", "effective_ceiling", "trailing_bytes"):
            if geometry.get(field) is not None:
                problems.append(
                    f"geometry.{field} must be null without physical_bytes")

    for field, want in spec.get("expected_geometry", {}).items():
        got = geometry.get(field)
        if got != want:
            problems.append(f"geometry {field}={got!r} != {want!r}")

    analysis = report.get("analysis")
    if not isinstance(analysis, dict):
        problems.append("missing analysis completion state")
        analysis = {}
    else:
        bool_fields = (
            "complete", "walk_started", "walk_completed",
            "continue_after_rejection", "findings_truncated",
        )
        for field in bool_fields:
            if not isinstance(analysis.get(field), bool):
                problems.append(f"analysis.{field} is not a boolean")
        if not isinstance(analysis.get("stop_reason"), str):
            problems.append("analysis.stop_reason is not a string")

    for field, want in spec.get("expected_analysis", {}).items():
        got = analysis.get(field)
        if got != want:
            problems.append(f"analysis {field}={got!r} != {want!r}")

    codes = {f["code"] for f in report.get("findings", [])}
    for want in spec.get("required_findings", []):
        if want not in codes:
            problems.append(f"missing required finding {want}")
    for forbidden_code in spec.get("forbidden_findings", []):
        if forbidden_code in codes:
            problems.append(f"forbidden finding present {forbidden_code}")

    for finding in report.get("findings", []):
        evidence = finding.get("evidence")
        if not isinstance(evidence, dict):
            continue
        locations = evidence.get("locations")
        if not isinstance(locations, list) or not locations:
            problems.append(
                f"finding {finding.get('code')} evidence has no byte locations")
            continue
        for index, location in enumerate(locations):
            if not isinstance(location, dict):
                problems.append(
                    f"finding {finding.get('code')} evidence location {index} is not an object")
                continue
            role = location.get("role")
            offset = location.get("offset")
            length = location.get("length")
            if role not in {"actual", "expected", "actual_source",
                            "expected_source"}:
                problems.append(
                    f"finding {finding.get('code')} evidence location {index} has invalid role {role!r}")
            if (isinstance(offset, bool) or not isinstance(offset, int)
                    or offset < 0):
                problems.append(
                    f"finding {finding.get('code')} evidence location {index} has invalid offset")
            if (isinstance(length, bool) or not isinstance(length, int)
                    or length <= 0):
                problems.append(
                    f"finding {finding.get('code')} evidence location {index} has invalid length")
            if (isinstance(physical, int) and not isinstance(physical, bool)
                    and isinstance(offset, int) and not isinstance(offset, bool)
                    and isinstance(length, int) and not isinstance(length, bool)
                    and length > 0 and offset + length > physical):
                problems.append(
                    f"finding {finding.get('code')} evidence location {index} exceeds physical file size")

    for code, expected in spec.get("expected_finding_evidence", {}).items():
        matching = [
            finding.get("evidence")
            for finding in report.get("findings", [])
            if finding.get("code") == code
            and isinstance(finding.get("evidence"), dict)
        ]
        if not matching:
            problems.append(f"finding {code} has no structured evidence")
            continue
        if not any(all(evidence.get(key) == value
                       for key, value in expected.items())
                   for evidence in matching):
            problems.append(
                f"finding {code} evidence does not include {expected!r}")

    expected_location_sets = spec.get(
        "expected_finding_evidence_locations", {})
    fixture_bytes = None
    if expected_location_sets and os.path.exists(path):
        with open(path, "rb") as fixture_file:
            fixture_bytes = fixture_file.read()
    for code, expected_locations in expected_location_sets.items():
        candidates = [
            finding.get("evidence")
            for finding in report.get("findings", [])
            if finding.get("code") == code
            and isinstance(finding.get("evidence"), dict)
        ]
        matched = False
        for evidence in candidates:
            locations = evidence.get("locations", [])
            used = set()
            all_matched = True
            for expected_location in expected_locations:
                found_index = None
                for index, location in enumerate(locations):
                    if (index not in used and isinstance(location, dict)
                            and _location_matches(location, expected_location,
                                                  fixture_bytes)):
                        found_index = index
                        break
                if found_index is None:
                    all_matched = False
                    break
                used.add(found_index)
            if all_matched:
                matched = True
                break
        if not matched:
            problems.append(
                f"finding {code} evidence locations do not include {expected_locations!r}")

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
