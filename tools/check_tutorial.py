#!/usr/bin/env python3
# Copyright (C) 2026 The HDF Group.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Execute the commands in the H5Lens and advanced GNU poke tutorials.

The primary tutorial is one h5explain session. The low-level tutorial is a
read-only poke session, while the construction tutorial contains an isolated
write-through session and an in-memory file-construction session. Extracting
the documented command fences keeps all three guides tied to live behavior.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
TUTORIAL = ROOT / "docs/TUTORIAL.md"
POKE_TUTORIAL = ROOT / "docs/POKE_TUTORIAL.md"
POKE_CONSTRUCTION = ROOT / "docs/POKE_CONSTRUCTION.md"
H5EXPLAIN = ROOT / "tools/h5explain"
SAMPLE = ROOT / "examples/file.h5"


def fail(message: str) -> None:
    print(f"TUTORIAL CHECK FAILED: {message}", file=sys.stderr)
    raise SystemExit(1)


def extract_numbered_poke_blocks(
    path: Path,
    expected_sections: tuple[int, ...],
) -> dict[int, list[str]]:
    """Return poke fences grouped by numbered section."""
    sections: dict[int, list[str]] = {}
    section = 0
    in_poke = False
    block: list[str] = []

    for line_number, line in enumerate(path.read_text().splitlines(), 1):
        heading = re.match(r"^## ([0-9]+)\.", line)
        if heading and not in_poke:
            section = int(heading.group(1))

        if line == "```poke":
            if in_poke:
                fail(
                    f"{path.relative_to(ROOT)} has a nested poke fence "
                    f"at line {line_number}"
                )
            in_poke = True
            block = []
            continue

        if in_poke and line == "```":
            sections.setdefault(section, []).append("\n".join(block))
            in_poke = False
            block = []
            continue

        if in_poke:
            block.append(line)

    if in_poke:
        fail(f"{path.relative_to(ROOT)} has an unterminated poke fence")

    missing = [
        section for section in expected_sections if not sections.get(section)
    ]
    if missing:
        fail(
            f"{path.relative_to(ROOT)} has no executable poke block in "
            f"section(s): {missing}"
        )

    return sections


def extract_h5explain_commands() -> list[str]:
    """Return interactive h5explain commands in documentation order."""
    commands: list[str] = []
    in_commands = False

    for line_number, line in enumerate(TUTORIAL.read_text().splitlines(), 1):
        if line == "```h5explain":
            if in_commands:
                fail(f"nested h5explain fence at line {line_number}")
            in_commands = True
            continue

        if in_commands and line == "```":
            in_commands = False
            continue

        if in_commands and line.strip():
            commands.append(line)

    if in_commands:
        fail("unterminated h5explain fence")
    if not commands:
        fail("primary tutorial has no executable h5explain commands")
    return commands


def escape_file_argument(path: Path) -> str:
    """Escape a path for poke's ``.file`` dot command."""
    return str(path).replace("\\", "\\\\").replace("#", "\\#").replace(" ", "\\ ")


def run_session(
    poke: str,
    name: str,
    blocks: list[str],
    directory: Path,
    initial_file: Path | None = None,
) -> str:
    commands: list[str] = []
    if initial_file is not None:
        commands.append(f".file {escape_file_argument(initial_file)}")
    commands.extend(blocks)
    commands.append(".exit")

    source = directory / f"{name}.pk"
    source.write_text("\n\n".join(commands) + "\n")

    env = os.environ.copy()
    load_path = str(ROOT / "pickles")
    if env.get("POKE_LOAD_PATH"):
        load_path += os.pathsep + env["POKE_LOAD_PATH"]
    env["POKE_LOAD_PATH"] = load_path

    try:
        result = subprocess.run(
            [poke, "--quiet", "--source", str(source)],
            cwd=directory,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired:
        fail(f"{name} exceeded the 30-second tutorial timeout")
    if result.returncode:
        fail(
            f"{name} exited {result.returncode}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    return result.stdout


def run_h5explain(commands: list[str]) -> str:
    """Run the primary tutorial as one h5explain batch session."""
    args = [str(H5EXPLAIN)]
    for command in commands:
        args.extend(("-c", command))
    args.append(str(SAMPLE))

    try:
        result = subprocess.run(
            args,
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired:
        fail("h5explain tutorial exceeded the 30-second timeout")
    if result.returncode:
        fail(
            f"h5explain tutorial exited {result.returncode}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    return result.stdout


def require(output: str, token: str, session: str, count: int = 1) -> None:
    actual = output.count(token)
    if actual < count:
        fail(
            f"{session} output contains {token!r} {actual} time(s), "
            f"expected at least {count}"
        )


def main() -> int:
    poke = shutil.which("poke")
    if poke is None:
        print("TUTORIAL CHECK SKIP: GNU poke is not installed")
        return 0

    h5explain = run_h5explain(extract_h5explain_commands())
    for token in (
        "HDF5 superblock at 0UL#B [superblock]",
        "Hard links:",
        "DirectChunkData -> 195UL#B",
        "Object-header message 4: Data layout",
        "chunk_index_addr=479UL#B",
        "H5_ADVISORY_DECODE_FILTER",
        "current: version 1 B-tree node at 479UL#B",
        "entries_used=4UH",
    ):
        require(h5explain, token, "h5explain")
    require(
        h5explain,
        "current: object header at 195UL#B [/DirectChunkData]",
        "h5explain",
        count=2,
    )

    poke_sections = extract_numbered_poke_blocks(
        POKE_TUTORIAL,
        tuple(range(6)),
    )
    construction_sections = extract_numbered_poke_blocks(
        POKE_CONSTRUCTION,
        (1, 2),
    )

    with tempfile.TemporaryDirectory(prefix="h5lens-tutorial-") as raw_tmp:
        tmp = Path(raw_tmp)

        explore_blocks = [
            block
            for section in range(6)
            for block in poke_sections[section]
        ]
        explore = run_session(
            poke, "explore", explore_blocks, tmp, SAMPLE
        )
        for token in (
            "oh_hdr {",
            "hdr_timestamps {",
            "oh_msg_linfo {",
            "oh_msg_link {",
            "oh_msg_sdspace {",
            "oh_msg_dtype {",
            "oh_msg_layout {",
            "bt1_hdr {",
            "Name:       oh_hdr",
        ):
            require(explore, token, "explore")
        require(explore, "4230038535U", "explore", count=2)

        editable = tmp / "file-edit.h5"
        shutil.copyfile(SAMPLE, editable)
        write = run_session(
            poke, "write", construction_sections[1], tmp, editable
        )
        require(write, "1773447782U", "write")
        require(write, "0U", "write")

        create = run_session(
            poke,
            "create",
            construction_sections[2],
            tmp,
        )
        for token in (
            "2UB",
            "48UL#B",
            "673867655U",
        ):
            require(create, token, "create")
        require(create, "2898835909U", "create", count=2)
        for token in ("oh_msg_linfo {", "oh_msg_ginfo {", "oh_msg_nil {"):
            require(create, token, "create")

        output_file = tmp / "empty.h5"
        if not output_file.is_file() or output_file.stat().st_size != 179:
            fail(
                "construction section 2 did not create the documented "
                "179-byte empty.h5"
            )

        h5dump = shutil.which("h5dump")
        if h5dump is not None:
            dumped = subprocess.run(
                [h5dump, "-pBH", str(output_file)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
                check=False,
            )
            if dumped.returncode:
                fail(
                    "h5dump rejected construction section 2's empty.h5\n"
                    f"{dumped.stderr}"
                )
            for token in ("SUPERBLOCK_VERSION 2", 'GROUP "/" {'):
                require(dumped.stdout, token, "h5dump")

    print(
        "TUTORIAL CHECK OK: h5explain, low-level poke, write-through, and "
        "construction sessions passed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
