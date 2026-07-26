#!/usr/bin/env bash
# Build instrumented HDF5 variants from the image-provided source checkout.
set -euo pipefail

script_name="$(basename -- "$0")"
readonly hdf5_source_dir="${HDF5_SOURCE_DIR:-/opt/hdf5}"
readonly hdf5_release_prefix="${HDF5_RELEASE_PREFIX:-/opt/hdf5-release}"
readonly hdf5_asan_prefix="${HDF5_ASAN_PREFIX:-/opt/hdf5-asan}"
readonly hdf5_32_prefix="${HDF5_32_PREFIX:-/opt/hdf5-32}"

log() {
    printf '[H5Lens HDF5 build] %s\n' "$*"
}

die() {
    printf '[H5Lens HDF5 build] ERROR: %s\n' "$*" >&2
    exit 1
}

usage() {
    cat <<EOF
Usage: ${script_name} [release] [asan] [32]

Builds the requested HDF5 variants from ${hdf5_source_dir}. With no arguments,
builds all variants.

  release  RelWithDebInfo build with zlib and SZIP filters
  asan     RelWithDebInfo AddressSanitizer build with zlib and SZIP filters
  32       RelWithDebInfo 32-bit (-m32) build without external filters
EOF
}

build_variant() {
    local variant=$1
    local prefix=$2
    shift 2
    local build_dir="${hdf5_source_dir}/build-${variant}"

    [[ -w "${prefix}" ]] || die "install prefix is not writable: ${prefix}"
    log "Configuring ${variant} in ${build_dir}"
    cmake -S "${hdf5_source_dir}" -B "${build_dir}" "$@"
    log "Building ${variant}"
    cmake --build "${build_dir}" --parallel
    log "Testing ${variant}"
    if [[ "${variant}" == "asan" ]]; then
        ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 \
            ctest --test-dir "${build_dir}" --output-on-failure -j"$(nproc)"
    else
        ctest --test-dir "${build_dir}" --output-on-failure -j"$(nproc)"
    fi
    log "Installing ${variant} in ${prefix}"
    cmake --install "${build_dir}"
}

build_release() {
    build_variant release "${hdf5_release_prefix}" \
        -DCMAKE_BUILD_TYPE=RelWithDebInfo \
        -DCMAKE_INSTALL_PREFIX="${hdf5_release_prefix}" \
        -DHDF5_ENABLE_ZLIB_SUPPORT=ON \
        -DHDF5_ENABLE_SZIP_SUPPORT=ON
}

build_asan() {
    build_variant asan "${hdf5_asan_prefix}" \
        -DCMAKE_BUILD_TYPE=RelWithDebInfo \
        -DCMAKE_C_FLAGS_RELWITHDEBINFO="-fsanitize=address -fno-omit-frame-pointer -g -O1" \
        -DCMAKE_EXE_LINKER_FLAGS="-fsanitize=address" \
        -DCMAKE_SHARED_LINKER_FLAGS="-fsanitize=address" \
        -DCMAKE_MODULE_LINKER_FLAGS="-fsanitize=address" \
        -DCMAKE_INSTALL_PREFIX="${hdf5_asan_prefix}" \
        -DHDF5_ENABLE_ZLIB_SUPPORT=ON \
        -DHDF5_ENABLE_SZIP_SUPPORT=ON
}

build_32() {
    build_variant 32 "${hdf5_32_prefix}" \
        -DCMAKE_BUILD_TYPE=RelWithDebInfo \
        -DCMAKE_C_FLAGS="-m32" \
        -DCMAKE_CXX_FLAGS="-m32" \
        -DCMAKE_EXE_LINKER_FLAGS="-m32" \
        -DCMAKE_SHARED_LINKER_FLAGS="-m32" \
        -DCMAKE_MODULE_LINKER_FLAGS="-m32" \
        -DCMAKE_INSTALL_PREFIX="${hdf5_32_prefix}" \
        -DHDF5_ENABLE_ZLIB_SUPPORT=OFF \
        -DHDF5_ENABLE_SZIP_SUPPORT=OFF
    readelf -h "${hdf5_32_prefix}/bin/h5dump" | rg -q '^  Class:\s+ELF32$' \
        || die "32-bit h5dump is not an ELF32 executable"
}

[[ -d "${hdf5_source_dir}" ]] || die "HDF5 source checkout is missing: ${hdf5_source_dir}"
if (($# == 0)); then
    set -- release asan 32
fi

for variant in "$@"; do
    case "${variant}" in
        release) build_release ;;
        asan) build_asan ;;
        32) build_32 ;;
        -h|--help) usage; exit 0 ;;
        *) usage >&2; die "unknown variant: ${variant}" ;;
    esac
done
