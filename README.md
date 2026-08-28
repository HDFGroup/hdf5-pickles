# H5Lens: HDF5 Pickles and Policy Workbench

H5Lens describes HDF5 on-disk metadata with
[GNU poke](https://jemarch.net/poke) pickles. It combines reusable format
definitions with an interactive explorer, an independent preflight oracle for
untrusted files, a conservative repair planner, and a marker scanner.

## What's Here

| Area | Purpose |
| --- | --- |
| [`pickles/`](pickles/) | Reusable HDF5 format definitions for GNU poke. |
| [`h5policy/`](h5policy/) | Metadata preflight, security profiles, regression corpus, differential testing, and fuzzing. |
| [`h5patch/`](h5patch/) | Evidence-gated repair planning, application, and audit logging. |
| [`h5explain/`](h5explain/) | Interactive byte-level metadata navigation. |
| [`src/`](src/) | The `h5markers` scanner implementation. |
| [`tools/`](tools/) | Command entry points and repository helper scripts. |
| [`docs/`](docs/) | [First 10 minutes](docs/FIRST_10_MINUTES.md), the [tutorial](docs/TUTORIAL.md), [tool guide](docs/TOOLS.md), [glossary](docs/GLOSSARY.md), [marker reference](docs/MARKERS.md), generated format reference, and [tool map](docs/tool-overview.md). |
| [`examples/`](examples/) | Sample HDF5 files and GNU poke scripts. |
| [`emacs/`](emacs/) | An Emacs front end for inspecting HDF5 files. |
| [`.devcontainer/`](.devcontainer/README.md) | A ready-to-use Codespaces and VS Code Dev Containers environment. |

## Quick Start

The [development container](.devcontainer/README.md) provides the complete
toolchain. Run these commands from the repository root.

```sh
# Preflight an untrusted HDF5 file.
./tools/h5policy --profile untrusted-strict examples/file.h5

# Explore the sample's metadata interactively.
./tools/h5explain examples/file.h5

# Create and inspect a repair plan without modifying the input.
./tools/h5patch plan damaged.h5 -o repair.plan.json
./tools/h5patch explain repair.plan.json
```

Build the marker scanner, run the regression suite, and check the documentation:

```sh
cmake -S . -B build
cmake --build build --parallel
ctest --test-dir build --output-on-failure
cmake --build build --target docs-check
```

Continue with [H5Lens in 10 Minutes](docs/FIRST_10_MINUTES.md), the guided
[H5Lens tutorial](docs/TUTORIAL.md), or see the
[`h5policy`](h5policy/README.md), [`h5patch`](h5patch/README.md), and
[`h5explain`](h5explain/README.md) guides for complete command behavior.

## License

H5Lens is distributed under the GNU General Public License, version 3 or later.
See [`COPYING`](COPYING) for the full license text.

## Acknowledgments

> This material is based upon work supported by the U.S. National Science
> Foundation under Federal Award No. 2534078. Any opinions, findings, and
> conclusions or recommendations expressed in this material are those of the
> author(s) and do not necessarily reflect the views of the National Science
> Foundation.
