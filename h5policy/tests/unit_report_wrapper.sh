#!/usr/bin/env bash
# Exercise the JSON report that the shell wrapper emits when its hard timeout
# kills poke.  A PATH-local timeout stub makes the case deterministic and fast.

set -uo pipefail

tests_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
tool="$tests_dir/../tools/h5policy"
case_dir=$(mktemp -d "${TMPDIR:-/tmp}/h5policy-timeout-test.XXXXXX")
fake_timeout="$case_dir/timeout"
input_file="$case_dir/input.h5"

cleanup() {
    rm -f -- "$fake_timeout" "$input_file"
    rmdir -- "$case_dir"
}
trap cleanup EXIT

{
    printf '%s\n' '#!/usr/bin/env bash'
    printf '%s\n' 'exit 124'
} >"$fake_timeout"
chmod +x "$fake_timeout"
printf 'abc' >"$input_file"

report=$(PATH="$case_dir:$PATH" \
    "$tool" --profile untrusted-strict --non-strict \
    --continue-after-rejection --max-walk-seconds 45 "$input_file")
tool_status=$?

if [[ $tool_status -ne 5 ]]; then
    printf 'FAIL wrapper_timeout_exit (got %s, expected 5)\n' "$tool_status"
    exit 1
fi

REPORT_JSON=$report python3 - <<'PY'
import json
import os
import sys

report = json.loads(os.environ["REPORT_JSON"])
problems = []

if report.get("schema_version") != 1:
    problems.append("schema_version")
if report.get("decision") != "unsupported_coverage_gap":
    problems.append("decision")
if report.get("mapping_mode") != "non_strict":
    problems.append("mapping_mode")

geometry = report.get("geometry", {})
if geometry != {
        "physical_bytes": 3,
        "declared_eoa": None,
        "effective_ceiling": None,
        "trailing_bytes": None,
}:
    problems.append("geometry")

analysis = report.get("analysis", {})
if (analysis.get("complete") is not False
        or analysis.get("stop_reason") != "wall_timeout"
        or analysis.get("continue_after_rejection") is not True):
    problems.append("analysis")

boundary = report.get("boundary", {})
if not boundary or any(boundary.values()):
    problems.append("boundary")

findings = report.get("findings", [])
if (len(findings) != 1
        or findings[0].get("code") != "H5_UNSUPPORTED_WALK_TIMEOUT"
        or findings[0].get("has_location") is not False
        or "75s wall-clock limit" not in findings[0].get("message", "")):
    problems.append("findings")

if problems:
    print("FAIL wrapper_timeout_report (" + ", ".join(problems) + ")")
    sys.exit(1)
print("PASS wrapper_timeout_report")
PY

if "$tool" --max-walk-seconds 0 "$input_file" >/dev/null 2>&1; then
    printf 'FAIL max_walk_seconds_rejects_zero\n'
    exit 1
fi
if "$tool" --max-walk-seconds nope "$input_file" >/dev/null 2>&1; then
    printf 'FAIL max_walk_seconds_rejects_text\n'
    exit 1
fi
if "$tool" --max-walk-seconds 99999999999999999999 "$input_file" >/dev/null 2>&1; then
    printf 'FAIL max_walk_seconds_rejects_overflow\n'
    exit 1
fi
printf 'PASS max_walk_seconds_argument_validation\n'

alias_output=$("$tool" --continue-after-corruption "$input_file" 2>&1 >/dev/null)
alias_status=$?
if [[ $alias_status -ne 2 \
      || "$alias_output" != *"h5policy: unknown option: --continue-after-corruption"* ]]; then
    printf 'FAIL continue_after_corruption_alias_removed\n'
    exit 1
fi
printf 'PASS continue_after_corruption_alias_removed\n'
