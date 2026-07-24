#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_dir="$(cd -- "${script_dir}/.." && pwd)"
build_dir="${repo_dir}/build"

log() {
    printf '[H5Lens Codespace] %s\n' "$*"
}

die() {
    printf '[H5Lens Codespace] ERROR: %s\n' "$*" >&2
    exit 1
}

on_error() {
    local status=$?
    local line=$1
    printf \
        '[H5Lens Codespace] ERROR: post-create failed at line %s (exit %s)\n' \
        "${line}" \
        "${status}" \
        >&2
    exit "${status}"
}
trap 'on_error "${LINENO}"' ERR

readonly hdf5_source_dir="/opt/hdf5"
readonly hdf5_asan_prefix="/opt/hdf5-asan"
log "Checking the image-provided HDF5 source checkout"
for writable_dir in "${hdf5_source_dir}" "${hdf5_asan_prefix}"; do
    if [[ -d "${writable_dir}" && ! -w "${writable_dir}" ]]; then
        sudo chown -R -- "$(id -u):$(id -g)" "${writable_dir}"
    fi
done

log "Checking installed analysis tools and Python modules"
python3 "${script_dir}/check.py" --runtime

log "Configuring the Debug build"
cmake \
    -S "${repo_dir}" \
    -B "${build_dir}" \
    -DCMAKE_BUILD_TYPE=Debug \
    -DCMAKE_EXPORT_COMPILE_COMMANDS=ON

log "Building repository binaries"
cmake --build "${build_dir}" --parallel

policy_report="$(mktemp /tmp/h5lens-policy.XXXXXX)"
markers_report="$(mktemp /tmp/h5lens-markers.XXXXXX)"
probe_report="$(mktemp /tmp/h5lens-probe.XXXXXX)"
cleanup() {
    rm -f "${policy_report}" "${markers_report}" "${probe_report}"
}
trap cleanup EXIT

log "Smoke-testing h5policy"
policy_status=0
"${repo_dir}/tools/h5policy" \
    --profile forensic \
    --json \
    "${repo_dir}/file.h5" \
    >"${policy_report}" || policy_status=$?
python3 "${script_dir}/check.py" \
    --policy-report "${policy_report}" \
    --policy-exit "${policy_status}"

log "Smoke-testing h5markers"
"${build_dir}/h5markers" "${repo_dir}/file.h5" >"${markers_report}"

log "Smoke-testing the installed HDF5 command suite"
h5dump -pBH "${repo_dir}/file.h5" >/dev/null

log "Smoke-testing exact-build activation tracing"
probe_status=0
"${repo_dir}/tools/h5policy-probe" \
    --json \
    "${repo_dir}/file.h5" \
    >"${probe_report}" || probe_status=$?
if ((probe_status != 0)); then
    if [[ -s "${probe_report}" ]]; then
        printf '%s\n' "h5policy-probe report:" >&2
        sed -n '1,160p' "${probe_report}" >&2
    fi
    die "h5policy-probe smoke test returned exit ${probe_status}"
fi

log "Ready: Debug build and analysis smoke checks passed."
printf '%s\n' "Run ctest --test-dir build --output-on-failure -j\$(nproc) for the full suite."
