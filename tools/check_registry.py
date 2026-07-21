#!/usr/bin/env python3
"""Report validation-coverage/findings registry consistency gaps."""
# Validation scopes from strategy §3/§11.2, as documented in registry/README.md.
SCOPES = {"local_decode", "record_local", "aggregate_object",
          "reference_graph", "resource", "policy"}
import re
import os
import glob
import sys
import yaml

coverage = yaml.safe_load(open("registry/validation-coverage.yml"))
findings = yaml.safe_load(open("registry/findings.yml"))["findings"]
records = {r["record"]: r for r in coverage["records"]}
missing = []
errors = 0

# A repeated code is silently dropped by YAML (last one wins), so a whole
# definition can go dead unnoticed -- H5_CORRUPT_OFFSET_OUT_OF_FILE did exactly
# that.  A code with more than one role belongs in `contexts`, not a second key.
seen_codes = set()
for path in ("registry/findings.yml",):
    for line in open(path):
        m = re.match(r"^  (H5_[A-Z0-9_]+):\s*$", line)
        if not m:
            continue
        if m.group(1) in seen_codes:
            print(f"DUPLICATE_KEY file={path} finding={m.group(1)} "
                  f"(YAML keeps only the last; use `contexts` for extra roles)")
            errors += 1
        seen_codes.add(m.group(1))
for record in coverage["records"]:
    for inv in record.get("invariants", []):
        code = inv.get("finding")
        codes = code if isinstance(code, list) else [code]
        for c in codes:
            if c and c not in findings:
                missing.append((record["record"], inv["id"], c))

for record, invariant, code in missing:
    print(f"MISSING finding={code} record={record} invariant={invariant}")
    errors += 1

for code, entry in findings.items():
    record = entry.get("record")
    inv = entry.get("invariant")
    known = records.get(record, {}).get("invariants", [])
    ids = {i.get("id") for i in known}
    if record and inv and inv not in ids:
        print(f"UNREFERENCED finding={code} record={record} invariant={inv}")
        errors += 1

# `contexts` disambiguate a code emitted by more than one walker.  Each rule
# must name a real record, and any invariant it names must belong to THAT
# record -- a rule pointing at the wrong family is the bug this data prevents.
for code, entry in findings.items():
    contexts = entry.get("contexts") or []
    if contexts and not entry.get("ambiguous"):
        print(f"CONTEXTS_WITHOUT_AMBIGUOUS finding={code}")
        errors += 1
    seen_matches = set()
    for ctx in contexts:
        match, rec = ctx.get("match"), ctx.get("record")
        if not match:
            print(f"CONTEXT_NO_MATCH finding={code}")
            errors += 1
            continue
        if match in seen_matches:
            print(f"CONTEXT_DUPLICATE finding={code} match={match!r}")
            errors += 1
        seen_matches.add(match)
        if rec not in records:
            print(f"CONTEXT_UNKNOWN_RECORD finding={code} record={rec} match={match!r}")
            errors += 1
            continue
        inv = ctx.get("invariant")
        if inv and inv not in {i.get("id") for i in records[rec].get("invariants", [])}:
            print(f"CONTEXT_UNKNOWN_INVARIANT finding={code} record={rec} invariant={inv}")
            errors += 1
        scope = ctx.get("scope")
        if scope and scope not in SCOPES:
            print(f"CONTEXT_UNKNOWN_SCOPE finding={code} scope={scope}")
            errors += 1

for record in coverage["records"]:
    status = record.get("coverage_status")
    if status == "covered":
        missing_fields = [k for k in ("validators", "tests") if not record.get(k)]
        if missing_fields:
            print(f"INCOMPLETE covered record={record['record']} fields={','.join(missing_fields)}")
            errors += 1
    backlog = record.get("backlog")
    if backlog:
        for key in ("validator", "stable_findings", "fixtures", "entry_point_driver", "ci_checks"):
            if not backlog.get(key):
                print(f"INCOMPLETE backlog record={record['record']} field={key}")
                errors += 1
        for fixture in backlog.get("fixtures", []):
            if isinstance(fixture, str) and fixture.startswith("h5policy/") and not os.path.exists(fixture):
                print(f"MISSING fixture record={record['record']} path={fixture}")
                errors += 1

# Every generated/curated expectation must point at a catalogued finding and
# every generated specimen must be owned by at least one expectation.
expected_files = set()
for path in glob.glob("h5policy/tests/expected/*.yml"):
    try:
        expected = yaml.safe_load(open(path)) or {}
    except yaml.YAMLError:
        continue
    required = expected.get("required_findings", []) or []
    fixture = expected.get("file")
    if fixture:
        expected_files.add(fixture)
        fixture_path = os.path.join("h5policy/tests", fixture)
        if not expected.get("allow_missing_file") and not os.path.isfile(fixture_path):
            print(f"MISSING expected_fixture={path} file={fixture}")
            errors += 1
    for code in required:
        if code not in findings:
            print(f"UNCATALOGUED fixture={path} finding={code}")
            errors += 1
        elif findings[code].get("record") not in records:
            print(f"UNREGISTERED fixture={path} finding={code} record={findings[code].get('record')}")
            errors += 1

for specimen in glob.glob("h5policy/tests/**/*.h5", recursive=True):
    rel = os.path.relpath(specimen, "h5policy/tests")
    if rel not in expected_files:
        print(f"UNOWNED generated_fixture={specimen}")
        errors += 1

print(f"records={len(records)} findings={len(findings)} missing={len(missing)} errors={errors}")
sys.exit(1 if errors else 0)
