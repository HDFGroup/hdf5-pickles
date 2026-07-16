#!/usr/bin/env bash
# Run Emacs byte-compilation and ERT tests from CTest or emacs-check.
set -euo pipefail

tests_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_dir="$(cd -- "$tests_dir/../.." && pwd)"
work_dir=${1:?usage: run.sh WORK_DIR}
emacs=${EMACS:-emacs}
python=${PYTHON:-python3}
compile_dir="$work_dir/emacs-byte-compile"
fixture_dir="$work_dir/fixtures"

mkdir -p "$compile_dir" "$fixture_dir"

dest_expr="(setq byte-compile-dest-file-function (lambda (file) (expand-file-name (concat (file-name-nondirectory file) \"c\") \"$compile_dir\")))"

"$emacs" -Q --batch -L "$repo_dir/emacs" \
    --eval "$dest_expr" -f batch-byte-compile \
    "$repo_dir/emacs/hdf5-poke-core.el" \
    "$repo_dir/emacs/hdf5-poke-ui.el" \
    "$repo_dir/emacs/hdf5-poke.el"
"$python" "$tests_dir/fixtures/make_hdf5_fixtures.py" "$fixture_dir"
"$emacs" -Q --batch -l "$tests_dir/hdf5-poke-test.el" \
    -f ert-run-tests-batch-and-exit
HDF5_POKE_TEST_FIXTURES="$fixture_dir" \
    "$emacs" -Q --batch -l "$tests_dir/hdf5-poke-process-test.el" \
    -f ert-run-tests-batch-and-exit
