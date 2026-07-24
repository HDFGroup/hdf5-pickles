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

"""Check the Mermaid tool overview and its documentation entry points."""

from __future__ import annotations

from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
OVERVIEW = ROOT / "docs/tool-overview.md"

EXPECTED_NODES = {
    "shared": "pickles/",
    "policy_pk": "h5policy/pickles/",
    "explain_pk": "h5explain/pickles/",
    "patch_pk": "h5patch/pickles/",
    "emacs_pk": "hdf5_poke_emacs.pk",
    "markers": "h5markers",
    "policy": "h5policy",
    "explain": "h5explain",
    "patch": "h5patch",
    "emacs_ui": "hdf5-poke.el",
    "cve": "h5cve",
    "gencorpus": "h5policy-gencorpus",
    "diff": "h5policy-diff",
    "fuzzlib": "h5policy-fuzzlib",
    "fuzz": "h5policy-fuzz",
    "crashfuzz": "h5policy-crashfuzz",
    "mutate": "h5mutate",
    "probe": "h5policy-probe",
    "seam": "h5policy-seamcheck",
    "truncate": "h5policy-truncate",
    "lazy": "h5policy-lazy",
    "pkdoc": "pkdoc.py",
    "finding_registry": "finding_registry.py",
    "registry_checks": "check_registry.py",
    "doc_checks": "check_tutorial.py",
}

EXPECTED_EDGES = (
    "shared --> policy_pk",
    "shared --> explain_pk",
    "policy_pk --> patch_pk",
    "shared --> emacs_pk",
    "policy_pk --> policy",
    "explain_pk --> explain",
    "patch_pk --> patch",
    "emacs_pk --> emacs_ui",
    'explain -. "check / check_all" .-> policy',
    'patch -. "evidence and post-apply verification" .-> policy',
    'cve -. "triage" .-> policy',
    'cve -. "marker census" .-> markers',
    'cve -. "navigation transcript" .-> explain',
    'cve -. "typed variants" .-> mutate',
    'cve -. "exact-build verification" .-> probe',
    "gencorpus --> corpus",
    "fuzzlib --> fuzz",
    "fuzzlib --> crashfuzz",
    "diff --> policy",
    "diff --> libhdf5",
    "fuzz --> policy",
    "fuzz --> libhdf5",
    "crashfuzz --> policy",
    "crashfuzz --> libhdf5",
    "mutate --> policy",
    "probe --> libhdf5",
    "seam --> policy",
    "truncate --> policy",
    "lazy --> policy",
    "truncate --> registry",
    "lazy --> registry",
    "sidecars --> pkdoc",
    "shared --> pkdoc",
    "pkdoc --> generated",
)

DOC_LINKS = {
    ROOT / "README.md": "docs/tool-overview.md",
    ROOT / "TOOLS.md": "docs/tool-overview.md",
    ROOT / "docs/README.md": "tool-overview.md",
}


def fail(message: str) -> None:
    print(f"TOOL OVERVIEW CHECK FAILED: {message}", file=sys.stderr)
    raise SystemExit(1)


def mermaid_block(text: str) -> str:
    blocks = re.findall(r"^```mermaid\n(.*?)^```$", text, re.MULTILINE | re.DOTALL)
    if len(blocks) != 1:
        fail(f"expected one Mermaid block, found {len(blocks)}")
    return blocks[0]


def check_structure(diagram: str) -> None:
    lines = diagram.splitlines()
    first = next((line.strip() for line in lines if line.strip()), "")
    if first != "flowchart TB":
        fail(f"diagram must start with 'flowchart TB', got {first!r}")

    subgraphs = sum(line.lstrip().startswith("subgraph ") for line in lines)
    ends = sum(line.strip() == "end" for line in lines)
    if subgraphs != ends:
        fail(f"unbalanced subgraphs: {subgraphs} starts and {ends} ends")

    declarations: dict[str, str] = {}
    for line in lines:
        match = re.match(r'^\s*([a-z][a-z0-9_]*)\["([^"]*)"\]', line)
        if match is None:
            continue
        node_id, label = match.groups()
        if node_id in declarations:
            fail(f"duplicate node declaration: {node_id}")
        declarations[node_id] = label

    for node_id, label_fragment in EXPECTED_NODES.items():
        label = declarations.get(node_id)
        if label is None:
            fail(f"missing node declaration: {node_id}")
        if label_fragment not in label:
            fail(
                f"{node_id} label lacks {label_fragment!r}: "
                f"{label!r}"
            )

    for edge in EXPECTED_EDGES:
        if edge not in diagram:
            fail(f"missing relationship: {edge}")

    for class_name in (
        "format",
        "tool",
        "support",
        "automation",
        "artifact",
        "runtime",
    ):
        if f"classDef {class_name} " not in diagram:
            fail(f"missing Mermaid class: {class_name}")


def check_links() -> None:
    for path, target in DOC_LINKS.items():
        if target not in path.read_text():
            fail(
                f"{path.relative_to(ROOT)} does not link to "
                "docs/tool-overview.md"
            )


def main() -> int:
    if not OVERVIEW.is_file():
        fail("docs/tool-overview.md is missing")
    diagram = mermaid_block(OVERVIEW.read_text())
    check_structure(diagram)
    check_links()
    print(
        "TOOL OVERVIEW CHECK OK: "
        f"{len(EXPECTED_NODES)} tools/layers and "
        f"{len(EXPECTED_EDGES)} relationships checked"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
