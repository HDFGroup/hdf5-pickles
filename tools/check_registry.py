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

from finding_registry import RegistryError, load_findings

coverage = yaml.safe_load(open("registry/validation-coverage.yml"))
try:
    findings = load_findings()
except RegistryError as exc:
    sys.exit(f"finding-registry: {exc}")
BACKLOG_PATH = "registry/finding-backlog.yml"
backlog_doc = yaml.safe_load(open(BACKLOG_PATH))
finding_backlog = backlog_doc["findings"]
records = {r["record"]: r for r in coverage["records"]}
missing = []
errors = 0

# Production finding codes are string literals in the pickle validators and in
# the h5policy shell wrapper's synthetic timeout report.  Include codes passed
# through checked-range helpers as well as direct h5policy_emit_* calls, and the
# collector's H5_POLICY_FINDINGS_TRUNCATED replacement.  Namespace filtering
# excludes HDF5 format-signature/profile constants that are not findings.
FINDING_CODE_RE = re.compile(
    r'"(H5_(?:CORRUPT|RESOURCE|POLICY|ADVISORY|UNSUPPORTED|INTERNAL)_[A-Z0-9_]+)"')
EMIT_SOURCES = sorted(glob.glob("h5policy/pickles/*.pk")) + [
    "h5policy/tools/h5policy",
]
emitted_by = {}
for path in EMIT_SOURCES:
    with open(path) as source:
        for code in set(FINDING_CODE_RE.findall(source.read())):
            emitted_by.setdefault(code, set()).add(path)

# The finding loader rejects duplicate keys within or across catalog shards.
# Keep the lightweight source scan for the separate backlog document, where a
# repeated code would otherwise be silently dropped by YAML (last one wins).
for path in (BACKLOG_PATH,):
    seen_codes = set()
    for line in open(path):
        m = re.match(r"^  (H5_[A-Z0-9_]+):(?:\s|$)", line)
        if not m:
            continue
        if m.group(1) in seen_codes:
            print(f"DUPLICATE_KEY file={path} finding={m.group(1)} "
                  f"(YAML keeps only the last; use a route shard for extra roles)")
            errors += 1
        seen_codes.add(m.group(1))

# registry/findings/catalog is the reviewed semantic catalog;
# finding-backlog.yml is an
# explicit inventory of codes whose family/invariant mapping is still pending.
# A production code must be in exactly one.  Backlog source attribution is an
# exact inventory; a catalog entry may intentionally name only its canonical
# emitter while route shards describe other roles, but every claimed source must
# really carry the code.  This reverses the old
# one-way check (coverage -> catalog), which could stay green while h5policy
# gained uncatalogued outputs.
catalog_codes = set(findings)
backlog_codes = set(finding_backlog)
for code in sorted(catalog_codes & backlog_codes):
    print(f"CATALOG_BACKLOG_OVERLAP finding={code}")
    errors += 1

tracked_codes = catalog_codes | backlog_codes
emitted_codes = set(emitted_by)
for code in sorted(emitted_codes - tracked_codes):
    print(f"UNTRACKED_EMIT finding={code} emitted_in={sorted(emitted_by[code])}")
    errors += 1
for code in sorted(tracked_codes - emitted_codes):
    print(f"STALE_TRACKED_FINDING finding={code}")
    errors += 1

def check_emitted_in(kind, code, claimed):
    global errors
    if not isinstance(claimed, list) or not claimed:
        print(f"INVALID_EMITTED_IN kind={kind} finding={code}")
        errors += 1
        return
    actual = emitted_by.get(code, set())
    wanted = set(claimed)
    source_drift = wanted != actual if kind == "backlog" else not wanted <= actual
    if source_drift:
        print(f"EMITTED_IN_DRIFT kind={kind} finding={code} "
              f"registry={sorted(wanted)} source={sorted(actual)}")
        errors += 1

for code, entry in findings.items():
    check_emitted_in("catalog", code, entry.get("emitted_in"))
for code, sources in finding_backlog.items():
    check_emitted_in("backlog", code, sources)

# A code only belongs in the catalog once it has a complete semantic mapping.
# Keep this structural gate here so an entry cannot be removed from the backlog
# by replacing its source inventory with a name-only catalog placeholder.
CATALOG_REQUIRED_FIELDS = (
    "severity", "scope", "invariant", "record", "versions", "shared",
    "edge_type", "emitted_in", "message",
)
for code, entry in findings.items():
    absent = [field for field in CATALOG_REQUIRED_FIELDS if field not in entry]
    if absent:
        print(f"INCOMPLETE_CATALOG finding={code} fields={','.join(absent)}")
        errors += 1
    if entry.get("scope") not in SCOPES:
        print(f"CATALOG_UNKNOWN_SCOPE finding={code} scope={entry.get('scope')}")
        errors += 1
    if entry.get("record") not in records:
        print(f"CATALOG_UNKNOWN_RECORD finding={code} record={entry.get('record')}")
        errors += 1
    if not isinstance(entry.get("invariant"), str) or not entry.get("invariant"):
        print(f"CATALOG_INVALID_INVARIANT finding={code}")
        errors += 1
    if not isinstance(entry.get("versions"), list) or not entry.get("versions"):
        print(f"CATALOG_INVALID_VERSIONS finding={code}")
        errors += 1
    if not isinstance(entry.get("shared"), bool):
        print(f"CATALOG_INVALID_SHARED finding={code}")
        errors += 1

invariant_findings = {}
for record in coverage["records"]:
    for inv in record.get("invariants", []):
        code = inv.get("finding")
        codes = code if isinstance(code, list) else [code]
        invariant_findings[(record["record"], inv["id"])] = {
            c for c in codes if c
        }
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
    elif record and inv and code not in invariant_findings.get((record, inv), set()):
        print(f"MAPPING_DRIFT finding={code} record={record} invariant={inv}")
        errors += 1

# Flattened route contexts disambiguate a code emitted by more than one walker.
# Each rule
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
        elif inv and code not in invariant_findings.get((rec, inv), set()):
            print(f"CONTEXT_MAPPING_DRIFT finding={code} record={rec} invariant={inv}")
            errors += 1
        scope = ctx.get("scope")
        if scope and scope not in SCOPES:
            print(f"CONTEXT_UNKNOWN_SCOPE finding={code} scope={scope}")
            errors += 1

# The manifest's `validators.hdf5` is a hand-maintained CLAIM;
# libhdf5-evidence.yml is what `h5cve evidence` actually measured. A claim that
# has drifted from the measurement is the failure mode this gate exists for --
# either the build changed and evidence needs regenerating, or someone asserted
# a verdict nothing observed.
EVIDENCE_PATH = "registry/libhdf5-evidence.yml"
if os.path.exists(EVIDENCE_PATH):
    evidence = (yaml.safe_load(open(EVIDENCE_PATH)) or {}).get("records", {})
    for record in coverage["records"]:
        name = record["record"]
        claimed = (record.get("validators") or {}).get("hdf5")
        measured = evidence.get(name, {}).get("verdict", "unmeasured")
        if claimed != measured:
            print(f"EVIDENCE_DRIFT record={name} manifest={claimed} "
                  f"measured={measured} (regenerate with `h5cve evidence`)")
            errors += 1
    for name in evidence:
        if name not in records:
            print(f"EVIDENCE_UNKNOWN_RECORD record={name}")
            errors += 1
else:
    print(f"NOTE {EVIDENCE_PATH} absent; libhdf5 verdicts unverified "
          f"(run `h5cve evidence`)")

# The §12 verification report must cover exactly the manifest's records, with
# every requirement present. Its CONTENT is a distance measure, not a pass/fail:
# most requirements are `absent` or `not_assessed` today and gating on that would
# be permanently red and therefore ignored. Only the structure is enforced, so a
# new record family cannot quietly escape the report.
VERIFICATION_PATH = "registry/verification-coverage.yml"
if os.path.exists(VERIFICATION_PATH):
    vdoc = yaml.safe_load(open(VERIFICATION_PATH)) or {}
    vrecords = vdoc.get("records", {})
    reqs = set(vdoc.get("requirements", []))
    for name in records:
        if name not in vrecords:
            print(f"VERIFICATION_MISSING_RECORD record={name} "
                  f"(regenerate with `h5cve verification`)")
            errors += 1
            continue
        got = set(vrecords[name])
        if got != reqs:
            print(f"VERIFICATION_INCOMPLETE record={name} "
                  f"missing={sorted(reqs - got)}")
            errors += 1
    for name in vrecords:
        if name not in records:
            print(f"VERIFICATION_UNKNOWN_RECORD record={name}")
            errors += 1
else:
    print(f"NOTE {VERIFICATION_PATH} absent; §12 status unknown "
          f"(run `h5cve verification`)")

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

# fuzz-findings/ is git-ignored scratch written by h5policy-fuzz, not corpus.
# Without this, running the fuzzer breaks the next suite run with UNOWNED errors.
SCRATCH_DIRS = ("fuzz-findings",)
for specimen in glob.glob("h5policy/tests/**/*.h5", recursive=True):
    rel = os.path.relpath(specimen, "h5policy/tests")
    if rel.split(os.sep)[0] in SCRATCH_DIRS:
        continue
    if rel not in expected_files:
        print(f"UNOWNED generated_fixture={specimen}")
        errors += 1

# Message routing.  A shared code's family is resolved from its finding MESSAGE
# via the grouped route rules, and for an `ambiguous` code a message matching no
# rule resolves to NO record at all -- so `h5cve verify` cannot pick a canary
# for it.  registry/message-routing.yml is the measured inventory of those gaps;
# this gate recomputes it and fails on drift either way, so a new unroutable
# message cannot be added silently and a fixed one cannot be left claimed.
sys.path.insert(0, "tools")
import message_routing                                          # noqa: E402
import importlib.machinery                                      # noqa: E402
import importlib.util                                           # noqa: E402

_loader = importlib.machinery.SourceFileLoader("h5cve_for_registry", "tools/h5cve")
_spec = importlib.util.spec_from_loader("h5cve_for_registry", _loader)
_h5cve = importlib.util.module_from_spec(_spec)
_loader.exec_module(_h5cve)

ROUTING_PATH = message_routing.ROUTING_PATH
emitted_messages, unanalyzable = message_routing.extract()

# An emit whose code or message expression is not understood is a hard error,
# not a skip: silently dropping one is how these gaps went unnoticed. Declare
# the new shape in message_routing.EMIT_SITES / COMPOSING_HELPERS.
for source, fn, expr in unanalyzable:
    print(f"MESSAGE_UNANALYZABLE source={source} fn={fn} expr={expr!r} "
          f"(declare it in tools/message_routing.py)")
    errors += 1

measured = message_routing.unrouted(emitted_messages, findings,
                                    _h5cve.resolve_finding)
if os.path.exists(ROUTING_PATH):
    declared = (yaml.safe_load(open(ROUTING_PATH)) or {}).get("unrouted") or {}
    for code in sorted(set(measured) | set(declared)):
        new = set(measured.get(code, [])) - set(declared.get(code, []))
        gone = set(declared.get(code, [])) - set(measured.get(code, []))
        for msg in sorted(new):
            print(f"ROUTING_GAP finding={code} message={msg!r} "
                  f"(add a route in registry/findings/routes/{code}.yml, "
                  f"or regenerate {ROUTING_PATH})")
            errors += 1
        for msg in sorted(gone):
            print(f"ROUTING_STALE finding={code} message={msg!r} now routes "
                  f"(regenerate with `python3 tools/message_routing.py --write`)")
            errors += 1
else:
    print(f"NOTE {ROUTING_PATH} absent; message routing unverified "
          f"(run `python3 tools/message_routing.py --write`)")

print(f"records={len(records)} findings={len(findings)} "
      f"backlog={len(finding_backlog)} emitted={len(emitted_by)} "
      f"messages={sum(len(v) for v in emitted_messages.values())} "
      f"unrouted={sum(len(v) for v in measured.values())} "
      f"missing={len(missing)} errors={errors}")
sys.exit(1 if errors else 0)
