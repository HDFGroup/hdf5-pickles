#!/usr/bin/env python3
"""Validate the H5Lens devcontainer contract, and optionally its runtime."""

from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
DEVCONTAINER = ROOT / ".devcontainer"
DOCKERFILE = DEVCONTAINER / "Dockerfile"
CONFIG = DEVCONTAINER / "devcontainer.json"
POST_CREATE = DEVCONTAINER / "post-create.sh"
README = DEVCONTAINER / "README.md"

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
    if not README.is_file():
        fail(".devcontainer/README.md is missing")
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
    if cmake_match is None or tuple(map(int, cmake_match.groups())) < (3, 19):
        fail("CMake is older than the repository's 3.19 minimum")

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

    print(
        "DEVCONTAINER RUNTIME OK: "
        f"{len(REQUIRED_COMMANDS)} commands and "
        f"{len(REQUIRED_MODULES)} Python modules available"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--runtime",
        action="store_true",
        help="also verify commands, Python modules, and minimum versions",
    )
    args = parser.parse_args()

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
