#!/usr/bin/env python3
"""Validate the H5Lens devcontainer contract, and optionally its runtime."""

from __future__ import annotations

import argparse
import importlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
DEVCONTAINER = ROOT / ".devcontainer"
DOCKERFILE = DEVCONTAINER / "Dockerfile"
CONFIG = DEVCONTAINER / "devcontainer.json"
POST_CREATE = DEVCONTAINER / "post-create.sh"
README = DEVCONTAINER / "README.md"
H5POLICY = ROOT / "tools" / "h5policy"

HDF5_REPOSITORY = "https://github.com/HDFGroup/hdf5.git"
HDF5_SOURCE_DIR = Path("/opt/hdf5")
HDF5_ASAN_PREFIX = Path("/opt/hdf5-asan")
MINIMUM_HDF5_CMAKE = (3, 26)

REQUIRED_ASAN_HEADERS = (
    Path("/usr/include/szlib.h"),
    Path("/usr/include/zlib.h"),
)

POLICY_EXIT_CODES = {
    "accept": 0,
    "accept_with_warnings": 1,
    "reject_corrupt": 2,
    "reject_policy": 3,
    "reject_resource": 4,
    "unsupported_coverage_gap": 5,
}

REQUIRED_PACKAGES = {
    "bash-completion",
    "ca-certificates",
    "cmake",
    "curl",
    "emacs-nox",
    "gdb",
    "git",
    "github-cli",
    "hdf5",
    "jq",
    "libaec",
    "libasan",
    "openssh",
    "poke",
    "procps-ng",
    "python",
    "python-h5py",
    "python-numpy",
    "python-pip",
    "python-yaml",
    "ripgrep",
    "rsync",
    "shellcheck",
    "sudo",
    "time",
    "zlib",
}

REQUIRED_COMMANDS = (
    "bash",
    "cc",
    "c++",
    "cmake",
    "ctest",
    "emacs",
    "gdb",
    "git",
    "gh",
    "h5cc",
    "h5copy",
    "h5debug",
    "h5dump",
    "h5ls",
    "h5repack",
    "h5stat",
    "jq",
    "poke",
    "python3",
    "rg",
    "shellcheck",
    "time",
)

REQUIRED_MODULES = ("h5py", "numpy", "yaml")

REQUIRED_EXTENSIONS = {
    "h5web.vscode-h5web",
    "ms-python.python",
    "ms-vscode.cmake-tools",
    "ms-vscode.cpptools",
    "redhat.vscode-yaml",
}


def fail(message: str) -> None:
    print(f"DEVCONTAINER CHECK FAILED: {message}", file=sys.stderr)
    raise SystemExit(1)


def docker_packages(text: str) -> set[str]:
    match = re.search(
        r"RUN pacman -Syu --noconfirm --needed \\\n"
        r"(?P<body>.*?)"
        r"\n\s*&& pacman -Scc --noconfirm",
        text,
        re.DOTALL,
    )
    if match is None:
        fail("Dockerfile lacks the expected install-and-cleanup transaction")
    return {
        line.strip().removesuffix("\\").strip()
        for line in match.group("body").splitlines()
        if line.strip()
    }


def check_configuration() -> None:
    dockerfile = DOCKERFILE.read_text()
    if not dockerfile.startswith("FROM archlinux:base-devel\n"):
        fail("Dockerfile must use the Arch base-devel image")

    packages = docker_packages(dockerfile)
    missing_packages = sorted(REQUIRED_PACKAGES - packages)
    if missing_packages:
        fail("Dockerfile lacks package(s): " + ", ".join(missing_packages))

    if "USER ${USERNAME}" not in dockerfile:
        fail("Dockerfile does not select the non-root development user")
    if "NOPASSWD:ALL" not in dockerfile:
        fail("Dockerfile does not configure development-user sudo")

    if f"ARG HDF5_REPOSITORY={HDF5_REPOSITORY}" not in dockerfile:
        fail("Dockerfile does not declare the canonical HDF5 repository")
    if f"ENV HDF5_SOURCE_DIR={HDF5_SOURCE_DIR}" not in dockerfile:
        fail("Dockerfile does not expose the HDF5 checkout location")
    if f"HDF5_ASAN_PREFIX={HDF5_ASAN_PREFIX}" not in dockerfile:
        fail("Dockerfile does not expose the HDF5 ASan install prefix")
    if f"\n        {HDF5_ASAN_PREFIX} \\\n" not in dockerfile:
        fail("Dockerfile does not create the HDF5 ASan install prefix")

    clone_match = re.search(
        r'RUN git clone \\\n'
        r'\s+"\$\{HDF5_REPOSITORY\}" \\\n'
        r'\s+"\$\{HDF5_SOURCE_DIR\}"',
        dockerfile,
    )
    if clone_match is None:
        fail("Dockerfile does not clone the HDF5 repository during image creation")
    if dockerfile.index("USER ${USERNAME}") > clone_match.start():
        fail("Dockerfile must clone HDF5 as the non-root development user")
    if "--depth" in clone_match.group(0) or "--filter" in clone_match.group(0):
        fail("Dockerfile must retain the complete HDF5 Git history")

    h5policy = H5POLICY.read_text()
    for decision, exit_code in POLICY_EXIT_CODES.items():
        if f"\n  {exit_code}  {decision}\n" not in h5policy:
            fail(
                "devcontainer h5policy exit mapping is stale for "
                f"{decision!r}"
            )

    try:
        config = json.loads(CONFIG.read_text())
    except json.JSONDecodeError as exc:
        fail(f"devcontainer.json is invalid JSON: {exc}")

    if config.get("name") != "H5Lens analysis":
        fail("devcontainer name is stale or missing")
    if config.get("remoteUser") != "vscode":
        fail("remoteUser must be the non-root vscode user")
    if config.get("updateRemoteUserUID") is not True:
        fail("updateRemoteUserUID must remain enabled")
    if config.get("postCreateCommand") != "bash .devcontainer/post-create.sh":
        fail("postCreateCommand does not invoke the checked setup script")
    if config.get("waitFor") != "postCreateCommand":
        fail("Codespaces may attach before the post-create smoke checks finish")
    if config.get("build", {}).get("args", {}).get(
        "HDF5_REPOSITORY"
    ) != HDF5_REPOSITORY:
        fail("devcontainer build does not select the canonical HDF5 repository")

    run_args = set(config.get("runArgs", []))
    for argument in ("--cap-add=SYS_PTRACE", "--security-opt=seccomp=unconfined"):
        if argument not in run_args:
            fail(f"native debugger run argument is missing: {argument}")

    extensions = set(
        config.get("customizations", {})
        .get("vscode", {})
        .get("extensions", [])
    )
    missing_extensions = sorted(REQUIRED_EXTENSIONS - extensions)
    if missing_extensions:
        fail("VS Code extension(s) missing: " + ", ".join(missing_extensions))

    if not POST_CREATE.is_file():
        fail(".devcontainer/post-create.sh is missing")
    post_create = POST_CREATE.read_text()
    for argument in ("--policy-report", "--policy-exit"):
        if argument not in post_create:
            fail(f"post-create policy verdict validation is missing {argument}")
    for path in (HDF5_SOURCE_DIR, HDF5_ASAN_PREFIX):
        if str(path) not in post_create:
            fail(f"post-create does not account for ownership of {path}")
    if not README.is_file():
        fail(".devcontainer/README.md is missing")
    readme = README.read_text()
    for fragment in (
        "HDFGroup/hdf5",
        f"`{HDF5_SOURCE_DIR}`",
        "`$HDF5_SOURCE_DIR`",
        "full-history",
        f"`{HDF5_ASAN_PREFIX}`",
        "`$HDF5_ASAN_PREFIX`",
        "-fsanitize=address",
    ):
        if fragment not in readme:
            fail(f"devcontainer guide does not document HDF5 checkout: {fragment}")
    if ".devcontainer/README.md" not in (ROOT / "README.md").read_text():
        fail("root README does not link the development-environment guide")


def version(command: list[str]) -> str:
    result = subprocess.run(
        command,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=30,
    )
    return result.stdout.strip().splitlines()[0]


def hdf5_git_output(*arguments: str) -> str:
    try:
        return version(["git", "-C", str(HDF5_SOURCE_DIR), *arguments])
    except (OSError, subprocess.SubprocessError) as exc:
        fail(f"cannot inspect the image-provided HDF5 checkout: {exc}")


def check_hdf5_checkout() -> None:
    configured_dir = os.environ.get("HDF5_SOURCE_DIR")
    if configured_dir != str(HDF5_SOURCE_DIR):
        fail(
            "HDF5_SOURCE_DIR must identify the image checkout at "
            f"{HDF5_SOURCE_DIR}, found {configured_dir!r}"
        )
    if not (HDF5_SOURCE_DIR / ".git").is_dir():
        fail(f"HDF5 Git checkout is missing at {HDF5_SOURCE_DIR}")
    if not (HDF5_SOURCE_DIR / "src" / "H5F.c").is_file():
        fail(f"HDF5 checkout at {HDF5_SOURCE_DIR} lacks src/H5F.c")
    if not os.access(HDF5_SOURCE_DIR, os.W_OK):
        fail(f"HDF5 checkout at {HDF5_SOURCE_DIR} is not writable")

    origin = hdf5_git_output("remote", "get-url", "origin")
    if origin != HDF5_REPOSITORY:
        fail(f"HDF5 origin is {origin!r}, expected {HDF5_REPOSITORY!r}")

    shallow = hdf5_git_output("rev-parse", "--is-shallow-repository")
    if shallow != "false":
        fail("HDF5 checkout is shallow; full history is required for analysis")

    revision = hdf5_git_output("rev-parse", "--short=12", "HEAD")
    print(
        "DEVCONTAINER HDF5 CHECKOUT OK: "
        f"{HDF5_SOURCE_DIR} at {revision} with full history"
    )


def check_asan_runtime() -> None:
    configured_prefix = os.environ.get("HDF5_ASAN_PREFIX")
    if configured_prefix != str(HDF5_ASAN_PREFIX):
        fail(
            "HDF5_ASAN_PREFIX must identify the image install prefix at "
            f"{HDF5_ASAN_PREFIX}, found {configured_prefix!r}"
        )
    if not HDF5_ASAN_PREFIX.is_dir() or not os.access(HDF5_ASAN_PREFIX, os.W_OK):
        fail(f"HDF5 ASan install prefix {HDF5_ASAN_PREFIX} is not writable")
    missing_headers = [
        str(header) for header in REQUIRED_ASAN_HEADERS if not header.is_file()
    ]
    if missing_headers:
        fail(
            "HDF5 ASan filter dependency header(s) missing: "
            + ", ".join(missing_headers)
        )

    source = """
#include <stdlib.h>
int main(void) {
    char *value = malloc(1);
    if (value == NULL)
        return 1;
    value[0] = 0;
    free(value);
    return 0;
}
"""
    with tempfile.TemporaryDirectory(prefix="h5lens-asan-") as temp_dir:
        executable = Path(temp_dir) / "asan-smoke"
        compile_result = subprocess.run(
            [
                "cc",
                "-fsanitize=address",
                "-fno-omit-frame-pointer",
                "-g",
                "-O1",
                "-x",
                "c",
                "-",
                "-o",
                str(executable),
            ],
            input=source,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=30,
        )
        if compile_result.returncode != 0:
            fail(
                "cannot compile and link an AddressSanitizer executable:\n"
                + compile_result.stdout
            )

        run_result = subprocess.run(
            [str(executable)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=30,
            env={**os.environ, "ASAN_OPTIONS": "detect_leaks=0:halt_on_error=1"},
        )
        if run_result.returncode != 0:
            fail(
                "AddressSanitizer runtime smoke executable failed:\n"
                + run_result.stdout
            )

    print("DEVCONTAINER ASAN OK: compiler, linker, and runtime passed")


def check_runtime() -> None:
    missing_commands = [
        command for command in REQUIRED_COMMANDS if shutil.which(command) is None
    ]
    if missing_commands:
        fail("runtime command(s) missing: " + ", ".join(missing_commands))

    for module in REQUIRED_MODULES:
        try:
            importlib.import_module(module)
        except ImportError as exc:
            fail(f"Python module {module!r} is unavailable: {exc}")

    cmake_match = re.search(r"([0-9]+)\.([0-9]+)", version(["cmake", "--version"]))
    if (
        cmake_match is None
        or tuple(map(int, cmake_match.groups())) < MINIMUM_HDF5_CMAKE
    ):
        minimum = ".".join(map(str, MINIMUM_HDF5_CMAKE))
        fail(
            "CMake is older than the image-provided HDF5 checkout's "
            f"{minimum} minimum"
        )

    emacs_major = version(
        [
            "emacs",
            "--batch",
            "--quick",
            "--eval",
            "(princ emacs-major-version)",
        ]
    )
    if not emacs_major.isdigit() or int(emacs_major) < 30:
        fail(f"Emacs 30+ is required, found {emacs_major!r}")

    check_hdf5_checkout()
    check_asan_runtime()

    print(
        "DEVCONTAINER RUNTIME OK: "
        f"{len(REQUIRED_COMMANDS)} commands and "
        f"{len(REQUIRED_MODULES)} Python modules available"
    )


def check_policy_report(path: Path, exit_code: int) -> None:
    if exit_code not in POLICY_EXIT_CODES.values():
        fail(f"h5policy terminated with unexpected exit code {exit_code}")

    try:
        report = json.loads(path.read_text())
    except OSError as exc:
        fail(f"cannot read h5policy smoke report {path}: {exc}")
    except json.JSONDecodeError as exc:
        fail(f"h5policy smoke report is not valid JSON: {exc}")

    if report.get("schema_version") != 1:
        fail(
            "h5policy smoke report has unsupported schema version "
            f"{report.get('schema_version')!r}"
        )

    decision = report.get("decision")
    if decision not in POLICY_EXIT_CODES:
        fail(f"h5policy smoke report has unknown decision {decision!r}")

    expected_exit = POLICY_EXIT_CODES[decision]
    if exit_code != expected_exit:
        fail(
            f"h5policy decision {decision!r} requires exit {expected_exit}, "
            f"but the command returned {exit_code}"
        )

    print(
        "DEVCONTAINER POLICY SMOKE OK: "
        f"{decision} is a valid verdict (exit {exit_code})"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--runtime",
        action="store_true",
        help="also verify commands, Python modules, and minimum versions",
    )
    parser.add_argument(
        "--policy-report",
        type=Path,
        help="validate an h5policy JSON smoke report",
    )
    parser.add_argument(
        "--policy-exit",
        type=int,
        help="exit code returned while producing --policy-report",
    )
    args = parser.parse_args()

    if (args.policy_report is None) != (args.policy_exit is None):
        parser.error("--policy-report and --policy-exit must be used together")
    if args.policy_report is not None:
        check_policy_report(args.policy_report, args.policy_exit)
        return 0

    check_configuration()
    print(
        "DEVCONTAINER CONFIG OK: "
        f"{len(REQUIRED_PACKAGES)} packages and "
        f"{len(REQUIRED_EXTENSIONS)} editor extensions checked"
    )
    if args.runtime:
        check_runtime()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
