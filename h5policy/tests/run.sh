#!/usr/bin/env bash
#
# h5policy regression runner.
#
#   1. (re)generates the corpus fixtures with h5policy-gencorpus,
#   2. runs the synthetic datatype-validator unit checks under poke,
#   3. runs h5policy over every tests/expected/*.yml case and asserts the
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

echo "== corpus cases =="
TESTS_DIR="$tests_dir" TOOL="$overlay_dir/tools/h5policy" \
    python3 "$tests_dir/_check.py"
corpus_status=$?

echo "== differential vs libhdf5 (h5py / h5dump / h5debug) =="
"$overlay_dir/tools/h5policy-diff" --dir "$tests_dir" | \
    grep -E '\[(PASS|FAIL|WARN)\]|FAIL |differential:'
diff_status=${PIPESTATUS[0]}

if [[ $unit_status -eq 0 && $corpus_status -eq 0 && $diff_status -eq 0 ]]; then
    echo "ALL TESTS PASSED"
    exit 0
fi
echo "TESTS FAILED (unit=$unit_status corpus=$corpus_status diff=$diff_status)"
exit 1
