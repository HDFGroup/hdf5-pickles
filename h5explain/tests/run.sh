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

echo "== generating fixtures =="
python3 "$tests_dir/make_fixtures.py" "$tests_dir/fixtures"

echo "== h5explain cases =="
python3 "$tests_dir/test_h5explain.py"
