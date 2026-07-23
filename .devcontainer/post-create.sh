#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_dir="$(cd -- "${script_dir}/.." && pwd)"
build_dir="${repo_dir}/build"

python3 "${script_dir}/check.py" --runtime

cmake \
    -S "${repo_dir}" \
    -B "${build_dir}" \
    -DCMAKE_BUILD_TYPE=Debug \
    -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
cmake --build "${build_dir}" --parallel

policy_report="$(mktemp /tmp/h5lens-policy.XXXXXX)"
markers_report="$(mktemp /tmp/h5lens-markers.XXXXXX)"
probe_report="$(mktemp /tmp/h5lens-probe.XXXXXX)"
trap 'rm -f "${policy_report}" "${markers_report}" "${probe_report}"' EXIT

"${repo_dir}/tools/h5policy" \
    --profile forensic \
    --json \
    "${repo_dir}/file.h5" \
    >"${policy_report}"
"${build_dir}/h5markers" "${repo_dir}/file.h5" >"${markers_report}"
h5dump -pBH "${repo_dir}/file.h5" >/dev/null
"${repo_dir}/tools/h5policy-probe" \
    --json \
    "${repo_dir}/file.h5" \
    >"${probe_report}"

printf '%s\n' "H5Lens Codespace ready: Debug build and analysis smoke checks passed."
printf '%s\n' "Run ctest --test-dir build --output-on-failure -j\$(nproc) for the full suite."
