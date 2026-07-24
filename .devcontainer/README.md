# Codespaces and development container

The repository's default development container is an analysis-ready Arch Linux
environment for GitHub Codespaces and VS Code Dev Containers. Open the
repository in a Codespace, or use **Dev Containers: Reopen in Container**
locally. The image build installs the complete toolchain; creating the
container does not perform a rolling system upgrade.

The image includes:

- GNU poke and the repository's reusable pickle load path;
- GCC/G++, CMake, CTest, `h5cc`, and the complete HDF5 command suite;
- Python with h5py, NumPy, PyYAML, and pip;
- Emacs 30+ for the inspector front end and its ERT tests;
- GDB and ptrace permissions for crash-fuzzer backtraces;
- Git, GitHub CLI, OpenSSH, ripgrep, jq, and ShellCheck; and
- VS Code support for CMake, C/C++, Python, YAML, and HDF5 viewing.

Image creation also makes a full-history clone of the official
[`HDFGroup/hdf5`](https://github.com/HDFGroup/hdf5) repository. The writable
checkout is available at `/opt/hdf5`, also exposed as `$HDF5_SOURCE_DIR`. This
location is outside Codespaces' persistent `/workspaces` mount, so the
image-layer clone remains visible when the development container starts. It
follows the HDF5 remote's default branch at the time the Docker layer is built:

```sh
cd "$HDF5_SOURCE_DIR"
git status
git log -1 --oneline
```

The Arch `hdf5` package remains the installed library used by the H5Lens smoke
checks. The source checkout is kept separate so an analysis can configure,
instrument, or bisect an upstream build without changing the system package.
It persists across stops and starts but is restored from the image when the
container is rebuilt; commit or export analysis changes before rebuilding.
Rebuilding may reuse Docker's cached clone layer, so run `git fetch` in the
checkout when an analysis specifically requires newer upstream commits.

## AddressSanitizer build of HDF5

The image has GCC's AddressSanitizer compiler and runtime support, plus the zlib
and libaec/SZIP development files. The startup check compiles, links, and runs a
small ASan executable so a missing sanitizer runtime is detected before an
analysis begins.

Use a dedicated build tree and install into `/opt/hdf5-asan`, exposed as
`$HDF5_ASAN_PREFIX`. This keeps the instrumented libraries and tools separate
from Arch's HDF5 installation under `/usr`:

```sh
cd "$HDF5_SOURCE_DIR"

cmake -S . -B build-asan \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo \
  -DCMAKE_C_FLAGS_RELWITHDEBINFO="-fsanitize=address -fno-omit-frame-pointer -g -O1" \
  -DCMAKE_EXE_LINKER_FLAGS="-fsanitize=address" \
  -DCMAKE_SHARED_LINKER_FLAGS="-fsanitize=address" \
  -DCMAKE_MODULE_LINKER_FLAGS="-fsanitize=address" \
  -DCMAKE_INSTALL_PREFIX="$HDF5_ASAN_PREFIX" \
  -DHDF5_ENABLE_ZLIB_SUPPORT=ON \
  -DHDF5_ENABLE_SZIP_SUPPORT=ON

cmake --build build-asan --parallel
ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 \
  ctest --test-dir build-asan --output-on-failure -j"$(nproc)"
cmake --install build-asan
```

This recipe covers the default serial C library, high-level library, tools,
examples, and tests, with zlib and SZIP filters enabled. MPI, Fortran, Java,
and C++ bindings remain disabled to keep the build focused. The existing
toolchain can also build the optional C++ bindings; MPI, Fortran, and Java
require additional packages. To run an installed ASan tool against the
instrumented shared libraries:

```sh
LD_LIBRARY_PATH="$HDF5_ASAN_PREFIX/lib" \
  "$HDF5_ASAN_PREFIX/bin/h5dump" -pBH suspect.h5
```

## Creation check

[`post-create.sh`](post-create.sh) validates every required command and Python
module, confirms that the image-provided HDF5 checkout has the canonical
origin, full history, and writable source files, configures a Debug CMake build,
builds `h5markers`, and smoke-tests `h5policy`, `h5markers`, `h5dump`, and the
exact-build activation probe against the sample file. Codespaces waits for
these checks before attaching the editor. A successful creation ends with:

```text
[H5Lens Codespace] Ready: Debug build and analysis smoke checks passed.
```

`h5policy` uses nonzero exit codes for valid policy verdicts as well as for
tool failures. In particular, the repository sample currently returns
`accept_with_warnings` with exit code 1 because it declares deflate. The
creation check validates the JSON decision against the documented exit-code
mapping (0–5); it does not mistake a warning or rejection verdict for a broken
Codespace. Exit 70, an unrecognized exit, malformed JSON, or a disagreement
between the decision and exit code still fails creation.

Each setup stage is prefixed with `[H5Lens Codespace]`. If creation fails, use
the last prefixed stage and the reported script line to locate the failing
dependency or smoke check in the Codespaces creation log.

The smoke test is deliberately smaller than the regression suite. Run the full
suite after opening the Codespace:

```sh
ctest --test-dir build --output-on-failure -j"$(nproc)"
```

Other useful entry points are:

```sh
cmake --build build --target docs-check
cmake --build build --target emacs-check
./tools/h5policy --profile forensic --json suspect.h5
./tools/h5explain suspect.h5
./build/h5markers suspect.h5
```

## Maintaining the image

The static contract checker keeps the Dockerfile, devcontainer configuration,
startup script, editor extensions, and this guide connected:

```sh
python3 .devcontainer/check.py
```

Inside the container, add `--runtime` to check installed commands, Python
modules, and minimum CMake/Emacs versions. When adding a repository dependency,
update the Dockerfile and the checker together, then rebuild the container.

The base image is Arch's rolling `base-devel` image so GNU poke and current
HDF5 packages come from the distribution rather than an untracked source build.
Rebuild the container periodically to receive package updates.
