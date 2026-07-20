#!/usr/bin/env bash
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

#
# h5policy regression runner.
#
#   1. (re)generates the corpus fixtures with h5policy-gencorpus,
#   2. runs synthetic datatype, assigned-message, file-space-info, and
#      profile-limit checks,
#   3. runs the reachability-record checks, including its walk-budget neutrality,
#   4. checks the stable, read-only API exposed to in-process consumers,
#   5. runs the h5policy_analyze seam checks that in-process consumers rely on,
#   6. checks the wrapper-generated wall-timeout report,
#   7. runs h5policy over every tests/expected/*.yml case and asserts the
#      decision, exit code, required findings, and forbidden outcomes.
#
# Exit status is 0 only if every check passes.
set -uo pipefail

tests_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
overlay_dir="$(cd -- "$tests_dir/.." && pwd)"
repo_dir="$(cd -- "$overlay_dir/.." && pwd)"
export POKE_LOAD_PATH="$overlay_dir/pickles:$repo_dir/pickles${POKE_LOAD_PATH:+:$POKE_LOAD_PATH}"

echo "== generating corpus =="
"$overlay_dir/tools/h5policy-gencorpus" "$tests_dir" || exit 1

echo "== datatype validator unit checks =="
poke --quiet -L "$tests_dir/unit_datatype.pk"
unit_status=$?

echo "== metadata message validator unit checks =="
poke --quiet -L "$tests_dir/unit_messages.pk"
message_status=$?

echo "== file-space-info validator unit checks =="
poke --quiet -L "$tests_dir/unit_fsinfo.pk"
fsinfo_status=$?

echo "== profile limit characterization checks =="
poke --quiet -L "$tests_dir/unit_limits.pk"
limits_status=$?

echo "== reachability record checks =="
poke --quiet -L "$tests_dir/unit_reached.pk"
reached_status=$?

echo "== consumer result API checks =="
poke --quiet -L "$tests_dir/unit_consumer.pk"
consumer_status=$?

# The seam cases open corpus fixtures, so they need the tests directory; -c is
# processed before -L, which is what puts the variable in scope for the load.
echo "== h5policy_analyze seam checks =="
poke --quiet -c "var seam_tests_dir = \"$tests_dir\";" -L "$tests_dir/unit_seam.pk"
seam_status=$?

echo "== wrapper timeout report checks =="
bash "$tests_dir/unit_report_wrapper.sh"
report_status=$?

echo "== corpus cases =="
TESTS_DIR="$tests_dir" TOOL="$overlay_dir/tools/h5policy" \
    python3 "$tests_dir/_check.py"
corpus_status=$?

echo "== differential vs libhdf5 (h5py / h5dump / h5debug) =="
"$overlay_dir/tools/h5policy-diff" --dir "$tests_dir" | \
    grep -E '\[(PASS|FAIL|WARN)\]|FAIL |differential:'
diff_status=${PIPESTATUS[0]}

# Exact-build probe smoke check (roadmap change #3, OS-level layer).  Needs a C
# toolchain and an h5cc; skipped (not failed) when either is absent, matching how
# the rest of the suite degrades without optional tooling.  A valid file must
# probe clean; the continuation self-overlap fixture must reject WITHOUT any
# forbidden activation (external open, plugin load, write, network) or crash.
echo "== exact-build libhdf5 probe (activation tracing) =="
probe_status=0
if command -v h5cc >/dev/null 2>&1 && command -v cc >/dev/null 2>&1; then
    forbid="external_open,plugin_load,write,network,crash"
    "$overlay_dir/tools/h5policy-probe" "$tests_dir/valid/continuation_chunks.h5" \
        --forbid "$forbid" || probe_status=1
    "$overlay_dir/tools/h5policy-probe" \
        "$tests_dir/malformed/continuation_overlaps_source.h5" \
        --forbid "$forbid" || probe_status=1
else
    echo "  skipped: h5cc or cc unavailable"
fi

# h5cve orchestrator smoke: init + triage must map the continuation fixture's
# primary finding to its registry invariant.  Exercises the tool <-> registry
# wiring without the exact-build toolchain (triage needs only h5policy + PyYAML).
echo "== h5cve orchestrator smoke =="
cve_status=0
cve_case="_smoke_$$"
if "$repo_dir/tools/h5cve" init "$cve_case" \
        --poc "$tests_dir/malformed/continuation_overlaps_source.h5" \
        --force >/dev/null 2>&1 \
   && "$repo_dir/tools/h5cve" triage "$cve_case" >/dev/null 2>&1; then
    cve_inv=$(python3 -c "import yaml; print(yaml.safe_load(open('$repo_dir/cases/$cve_case/case.yml')).get('violated_invariant',''))" 2>/dev/null)
    if [[ "$cve_inv" == "continuation.no_source_overlap" ]]; then
        echo "  triage mapped finding -> $cve_inv"
    else
        echo "  FAIL: expected continuation.no_source_overlap, got '$cve_inv'"
        cve_status=1
    fi
else
    echo "  FAIL: h5cve init/triage errored"
    cve_status=1
fi
rm -rf "$repo_dir/cases/$cve_case"

if [[ $unit_status -eq 0 && $message_status -eq 0 \
      && $fsinfo_status -eq 0 \
      && $limits_status -eq 0 && $reached_status -eq 0 \
      && $consumer_status -eq 0 \
      && $seam_status -eq 0 && $report_status -eq 0 \
      && $corpus_status -eq 0 && $diff_status -eq 0 \
      && $probe_status -eq 0 && $cve_status -eq 0 ]]; then
    echo "ALL TESTS PASSED"
    exit 0
fi
echo "TESTS FAILED (unit=$unit_status messages=$message_status fsinfo=$fsinfo_status limits=$limits_status reached=$reached_status consumer=$consumer_status seam=$seam_status report=$report_status corpus=$corpus_status diff=$diff_status probe=$probe_status cve=$cve_status)"
exit 1
