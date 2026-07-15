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

set -euo pipefail

tests_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_dir="$(cd -- "$tests_dir/../.." && pwd)"

# Generate into our own tree, not h5policy/tests.  Writing there would have this
# suite regenerating another suite's fixtures underneath it, which races as soon
# as the two run concurrently.  A private copy costs ~0.3s and ~1MB.
"$repo_dir/h5policy/tools/h5policy-gencorpus" "$tests_dir/corpus"
python3 "$tests_dir/test_h5patch.py"
