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

## Creation check

[`post-create.sh`](post-create.sh) validates every required command and Python
module, configures a Debug CMake build, builds `h5markers`, and smoke-tests
`h5policy`, `h5markers`, `h5dump`, and the exact-build activation probe against
the sample file. Codespaces waits for these checks before attaching the editor.
A successful creation ends with:

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
