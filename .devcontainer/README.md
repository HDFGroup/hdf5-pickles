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
- Codex CLI (installed as `codex`), Claude Code (installed as `claude`), Git,
  GitHub CLI, OpenSSH, ripgrep, jq, and ShellCheck; and
- VS Code support for CMake, C/C++, Python, YAML, and HDF5 viewing.

Codex and Claude Code are installed globally while the image builds, so they
are immediately available in every Codespaces terminal:

```sh
codex --version
codex
claude --version
claude
```

Arch's npm allowlists installation scripts. The image permits only Claude
Code's required native-binary installer with
`--allow-scripts=@anthropic-ai/claude-code`; it does not enable lifecycle
scripts globally.

Sign in to each tool with the account or API-key flow appropriate for your
organization; authentication is not stored in the image or repository.

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

## HDF5 variant builds

[`build-hdf5.sh`](build-hdf5.sh) configures, builds, tests, and installs the
HDF5 variants used for analysis. It uses separate build trees inside
`$HDF5_SOURCE_DIR` and installs to writable prefixes outside the system HDF5
package:

- `release`: a `RelWithDebInfo` build with zlib and SZIP filters, installed to
  `/opt/hdf5-release` (`$HDF5_RELEASE_PREFIX`);
- `asan`: a `RelWithDebInfo` AddressSanitizer build with zlib and SZIP filters,
  installed to `/opt/hdf5-asan` (`$HDF5_ASAN_PREFIX`); and
- `32`: a `RelWithDebInfo`, `-m32` build without external filters, installed to
  `/opt/hdf5-32` (`$HDF5_32_PREFIX`).

The 32-bit build supports analyses that must reproduce 32-bit integer sizes or
address-space limits. The image includes `gcc-multilib` and `lib32-gcc-libs` by
default. zlib and SZIP are deliberately disabled for that variant because the
image does not include matching 32-bit filter libraries. The script verifies
the installed `h5dump` is `ELF32`.

Run all variants, or name one or more variants to limit the work:

```sh
.devcontainer/build-hdf5.sh
.devcontainer/build-hdf5.sh release asan
.devcontainer/build-hdf5.sh 32
```

Run an installed ASan or 32-bit tool against the matching libraries:

```sh
LD_LIBRARY_PATH="$HDF5_ASAN_PREFIX/lib" \
  "$HDF5_ASAN_PREFIX/bin/h5dump" -pBH suspect.h5
LD_LIBRARY_PATH="$HDF5_32_PREFIX/lib" \
  "$HDF5_32_PREFIX/bin/h5dump" -pBH suspect.h5
```

## Creation check

[`post-create.sh`](post-create.sh) validates every required command and Python
module, confirms that the image-provided HDF5 checkout has the canonical
origin, full history, and writable source files, smoke-tests the 32-bit
compiler, linker, and runtime, configures a Debug CMake build, builds
`h5markers`, and smoke-tests `h5policy`, `h5markers`, `h5dump`, and the
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
