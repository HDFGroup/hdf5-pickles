#!/usr/bin/env python3
"""Validate the checked h5policy -> SSP control-evidence contract."""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import sys

import yaml

from finding_registry import RegistryError, load_findings


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "registry/ssp-control-evidence.yml"
COVERAGE = ROOT / "registry/validation-coverage.yml"
MEASUREMENT = ROOT / "registry/libhdf5-evidence.yml"
EXPECTATIONS = ROOT / "h5policy/tests/expected"
H5CVE = ROOT / "tools/h5cve"

# The SSP SIG consumer contract, when that repository is checked out beside this
# one. Located by env override first, then a sibling-directory convention -- no
# host path is recorded, matching AGENTS.md portable-provenance.
CONSUMER_REL = "audit/registry/h5policy-control-evidence.json"
CONSUMER_ENV = "HDF5_SSP_SIG_DIR"
CONSUMER_SIBLINGS = ("hdf5-ssp-sig",)


def fail(message: str) -> None:
    print(f"SSP EVIDENCE CHECK FAILED: {message}", file=sys.stderr)
    raise SystemExit(1)


def locate_consumer() -> Path | None:
    """The SSP consumer contract if the sibling repo is available, else None."""
    bases = []
    env = os.environ.get(CONSUMER_ENV)
    if env:
        bases.append(Path(env))
    bases.extend(ROOT.parent / name for name in CONSUMER_SIBLINGS)
    for base in bases:
        candidate = base / CONSUMER_REL
        if candidate.is_file():
            return candidate
    return None


def check_cross_seam(producer_ids: set[str]) -> None:
    """The two sides of the seam must import the same control set.

    Each repository's own checker validates its side; nothing else compares the
    two lists, so a control added to one contract alone would pass both checks
    while silently drifting. This closes that gap when both repos are present,
    and skips with a notice (never a failure) when the sibling is absent, so a
    lone checkout still gates.
    """
    consumer_path = locate_consumer()
    if consumer_path is None:
        print(f"SSP CROSS-SEAM CHECK SKIPPED: {CONSUMER_REL} not found "
              f"(set {CONSUMER_ENV} or check out the SSP SIG repo beside this one)")
        return
    try:
        consumer = json.loads(consumer_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"cannot read consumer contract {consumer_path.name}: {exc}")
    consumer_ids = consumer.get("controls")
    if not isinstance(consumer_ids, list):
        fail("consumer contract controls must be a list")
    consumer_set = set(consumer_ids)
    if len(consumer_ids) != len(consumer_set):
        fail("consumer contract controls must be unique")
    only_producer = sorted(producer_ids - consumer_set)
    only_consumer = sorted(consumer_set - producer_ids)
    if only_producer or only_consumer:
        detail = []
        if only_producer:
            detail.append(f"only in producer: {', '.join(only_producer)}")
        if only_consumer:
            detail.append(f"only in consumer: {', '.join(only_consumer)}")
        fail("producer and SSP consumer control sets disagree (" + "; ".join(detail) + ")")
    print(f"SSP CROSS-SEAM CHECK OK: {len(consumer_set)} controls match the SSP consumer")


def read_yaml(path: Path) -> dict:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        fail(f"cannot read {path.relative_to(ROOT)}: {exc}")
    if not isinstance(data, dict):
        fail(f"{path.relative_to(ROOT)} must contain a mapping")
    return data


def canary_by_record() -> dict[str, str]:
    tree = ast.parse(H5CVE.read_text(encoding="utf-8"), filename=str(H5CVE))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "CANARY_BY_RECORD"
            for target in node.targets
        ):
            continue
        result = ast.literal_eval(node.value)
        if isinstance(result, dict) and all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in result.items()
        ):
            return result
    fail("tools/h5cve must define CANARY_BY_RECORD as a string mapping")


def finding_for_invariant(record: dict, invariant: str, finding: str) -> bool:
    for item in record.get("invariants", []):
        if not isinstance(item, dict) or item.get("id") != invariant:
            continue
        values = item.get("finding")
        if isinstance(values, str):
            values = [values]
        if isinstance(values, list) and finding in values:
            return True
    return False


def check_row(row: dict, records: dict[str, dict], findings: dict,
              evidence: dict[str, dict], canaries: dict[str, str]) -> None:
    required = {"id", "record", "invariant", "finding", "fixture", "canary",
                "oracle_decision", "native_measurement"}
    absent = sorted(required - set(row))
    if absent:
        fail(f"control entry is missing {', '.join(absent)}")
    control = row["id"]
    record_name = row["record"]
    if record_name not in records:
        fail(f"{control}: unknown record {record_name!r}")
    if row["finding"] not in findings:
        fail(f"{control}: unknown finding {row['finding']!r}")
    if not finding_for_invariant(records[record_name], row["invariant"], row["finding"]):
        fail(f"{control}: {row['finding']} is not mapped to {record_name}.{row['invariant']}")
    if canaries.get(record_name) != row["canary"]:
        fail(f"{control}: canary {row['canary']!r} does not match {record_name!r}")

    expected = read_yaml(EXPECTATIONS / row["fixture"])
    family = expected.get("h5cve", {}).get("family")
    if family != record_name:
        fail(f"{control}: fixture family {family!r} != {record_name!r}")
    if expected.get("expected_decision") != row["oracle_decision"]:
        fail(f"{control}: fixture decision does not match the contract")
    if row["finding"] not in expected.get("required_findings", []):
        fail(f"{control}: fixture does not require {row['finding']}")

    measurement = row["native_measurement"]
    if not isinstance(measurement, dict):
        fail(f"{control}: native_measurement must be a mapping")
    observed = evidence.get(record_name)
    if not isinstance(observed, dict):
        fail(f"{control}: no native measurement for {record_name}")
    if measurement.get("family_verdict") != observed.get("verdict"):
        fail(f"{control}: family verdict does not match libhdf5 evidence")
    outcome = measurement.get("fixture_outcome")
    # `crashes` lets a DoS/memory-safety fixture that makes libhdf5 abort (the
    # exact-build matrix records it under crashes_on, separate from the
    # rejection verdict) be first-class SSP evidence -- a divide-by-zero or an
    # amplification is precisely the hardening a control like TEST-05 or HARD-04
    # wants to show, and would otherwise be unrepresentable here.
    if outcome not in {"enforced", "diverges", "crashes", "not_applicable"}:
        fail(f"{control}: unsupported fixture outcome {outcome!r}")
    if outcome != "not_applicable" and row["fixture"] not in observed.get(f"{outcome}_on", []):
        fail(f"{control}: fixture is not measured as {outcome}")
    requested_events = measurement.get("activation_observed", [])
    actual_events = {
        event for entry in observed.get("activation_observed", [])
        if entry.get("fixture") == row["fixture"]
        for event in entry.get("events", [])
    }
    if not set(requested_events) <= actual_events:
        fail(f"{control}: activation evidence does not support {requested_events!r}")


def main() -> int:
    contract = read_yaml(CONTRACT)
    coverage = read_yaml(COVERAGE)
    measurement = read_yaml(MEASUREMENT)
    if contract.get("schema_version") != 1 or contract.get("producer") != "h5policy":
        fail("contract must be schema version 1 produced by h5policy")
    if contract.get("measurement", {}).get("libhdf5_version") != measurement.get("libhdf5_version"):
        fail("contract libhdf5 version must match generated measurement")
    rows = contract.get("controls")
    if not isinstance(rows, list) or not rows:
        fail("contract needs at least one control mapping")
    # A control is evidenced by MANY fixtures (TEST-05 covers "every fixed
    # vulnerability class"), so rows are keyed by the (control, fixture) pair,
    # not by control alone. The control-id SET is what the SSP consumer imports.
    pairs = [(row.get("id"), row.get("fixture")) for row in rows if isinstance(row, dict)]
    if len(pairs) != len(rows) or len(pairs) != len(set(pairs)):
        fail("control mappings need a unique (id, fixture) pair per row")
    if not all(isinstance(cid, str) and cid for cid, _ in pairs):
        fail("every control mapping needs a string id")
    records = {entry.get("record"): entry for entry in coverage.get("records", [])
               if isinstance(entry, dict) and isinstance(entry.get("record"), str)}
    try:
        findings = load_findings()
    except RegistryError as exc:
        fail(str(exc))
    canaries = canary_by_record()
    for row in rows:
        if not isinstance(row, dict):
            fail("each control mapping must be a mapping")
        check_row(row, records, findings, measurement.get("records", {}), canaries)
    control_ids = {cid for cid, _ in pairs}
    check_cross_seam(control_ids)
    print(f"SSP EVIDENCE CHECK OK: {len(rows)} rows over {len(control_ids)} controls; "
          f"libhdf5 {measurement['libhdf5_version']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
