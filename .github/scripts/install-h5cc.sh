#!/usr/bin/env bash
set -euo pipefail

source_dir=${1:?pass the HDF5 source directory}
prefix=${2:?pass the installation prefix}
build_dir="${prefix}-build"

# Install the C library and its real compiler wrapper. Debian's h5repack and
# h5dump stay on PATH alongside the Python writer recorded in CORPUS-WRITER.txt.
cmake -S "$source_dir" -B "$build_dir" \
    -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$prefix" \
    -DBUILD_TESTING=OFF -DBUILD_STATIC_LIBS=OFF \
    -DHDF5_BUILD_EXAMPLES=OFF -DHDF5_BUILD_TOOLS=OFF \
    -DHDF5_BUILD_HL_LIB=OFF -DHDF5_ENABLE_ZLIB_SUPPORT=ON
cmake --build "$build_dir" --parallel "$(nproc)"
cmake --install "$build_dir"
test -x "$prefix/bin/h5cc"
