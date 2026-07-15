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
# h5explain regression runner.
#
#   1. (re)generates the navigation fixtures with make_fixtures.py,
#   2. drives h5explain in batch mode over them and asserts on its output.
#
# Exit status is 0 only if every check passes.
set -euo pipefail

tests_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_dir="$(cd -- "$tests_dir/../.." && pwd)"

echo "== generating fixtures =="
python3 "$tests_dir/make_fixtures.py" "$tests_dir/fixtures"

# The check cases need a file h5policy rejects.  Rather than hand-corrupt one
# here, reuse the h5policy generator: those fixtures already have known-bad
# bytes at known offsets, and their expected verdicts are specified upstream.
#
# Generate into our own tree, not h5policy/tests.  Writing there would have this
# suite mutating another suite's fixtures underneath it, which races as soon as
# the two run concurrently.  A private copy costs ~0.3s and ~1MB.
echo "== generating h5policy corpus (for check cases) =="
"$repo_dir/h5policy/tools/h5policy-gencorpus" "$tests_dir/corpus"

echo "== h5explain cases =="
python3 "$tests_dir/test_h5explain.py"
