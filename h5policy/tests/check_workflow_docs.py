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

"""Keep the operator workflow tied to the h5policy command-line contract."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import re
import subprocess
import sys

import yaml


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / "docs/H5POLICY_WORKFLOW.md"
DOC_INDEX = ROOT / "docs/README.md"
POLICY_GUIDE = ROOT / "h5policy/README.md"
H5POLICY = ROOT / "tools/h5policy"
FINDING_REGISTRY = ROOT / "tools/finding_registry.py"
MESSAGE_ROUTING = ROOT / "tools/message_routing.py"
FINDING_BACKLOG = ROOT / "registry/finding-backlog.yml"
VALIDATION_COVERAGE = ROOT / "registry/validation-coverage.yml"
VERIFICATION_COVERAGE = ROOT / "registry/verification-coverage.yml"
LIBHDF5_EVIDENCE = ROOT / "registry/libhdf5-evidence.yml"


def fail(message: str) -> None:
    print(f"H5POLICY WORKFLOW DOC CHECK FAILED: {message}", file=sys.stderr)
    raise SystemExit(1)


def command_contract() -> tuple[set[str], dict[int, str]]:
    result = subprocess.run(
        [str(H5POLICY), "--help"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
        check=False,
    )
    if result.returncode:
        fail(f"h5policy --help exited {result.returncode}: {result.stderr}")

    profile_block = result.stdout.split("Profiles", 1)[-1].split(
        "Mode flags", 1
    )[0]
    profiles = set(
        re.findall(r"^  ([a-z][a-z-]+)\s+", profile_block, re.MULTILINE)
    )

    exit_block = result.stdout.split("Exit codes", 1)[-1]
    decisions = {
        int(code): decision
        for code, decision in re.findall(
            r"^\s+(\d+)\s+([a-z_]+)\s*$", exit_block, re.MULTILINE
        )
    }
    if not profiles or not decisions:
        fail("could not parse profiles or exit codes from h5policy --help")
    return profiles, decisions


def documented_contract(text: str) -> tuple[set[str], dict[int, str]]:
    profile_section = text.split("### 1. Select the profile", 1)[-1].split(
        "### 2. Run the bounded, read-only preflight", 1
    )[0]
    profiles = set(
        re.findall(
            r"^\| `([a-z][a-z-]+)` \|", profile_section, re.MULTILINE
        )
    )
    decisions = {
        int(code): decision
        for code, decision in re.findall(
            r"^\| `(\d+)` \| `([a-z_]+)` \|", text, re.MULTILINE
        )
    }
    return profiles, decisions


def run_tool(command: list[str], label: str) -> str:
    result = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    if result.returncode:
        fail(f"{label} exited {result.returncode}: {result.stderr}")
    return result.stdout


def evidence_contract() -> dict[str, int | str]:
    coverage = yaml.safe_load(VALIDATION_COVERAGE.read_text())
    records = coverage["records"]
    coverage_statuses = Counter(record["coverage_status"] for record in records)
    oracle_statuses = Counter(
        record["validators"]["h5policy"] for record in records
    )

    verification = yaml.safe_load(VERIFICATION_COVERAGE.read_text())
    verification_statuses: Counter[str] = Counter()
    for record in verification["records"].values():
        verification_statuses.update(
            result["status"] for result in record.values()
        )

    native = yaml.safe_load(LIBHDF5_EVIDENCE.read_text())
    native_statuses = Counter(
        record["verdict"] for record in native["records"].values()
    )

    backlog = yaml.safe_load(FINDING_BACKLOG.read_text())["findings"]

    finding_stats = run_tool(
        [sys.executable, str(FINDING_REGISTRY), "stats"],
        "finding registry stats",
    )
    finding_match = re.search(r"^findings: (\d+)$", finding_stats, re.MULTILINE)
    if not finding_match:
        fail("could not parse the finding count")

    routing_stats = run_tool(
        [sys.executable, str(MESSAGE_ROUTING)],
        "message routing stats",
    )
    routing_match = re.search(
        r"^(\d+) messages, \d+ codes, (\d+) unrouted across \d+ codes, "
        r"(\d+) unanalyzable$",
        routing_stats,
        re.MULTILINE,
    )
    if not routing_match:
        fail("could not parse the message-routing counts")

    return {
        "records": len(records),
        "invariants": sum(len(record["invariants"]) for record in records),
        "covered": coverage_statuses["covered"],
        "partial": coverage_statuses["partial"],
        "coverage_gap": coverage_statuses["coverage_gap"],
        "oracle_enforced": oracle_statuses["enforced"],
        "oracle_partial": oracle_statuses["partial"],
        "verification_total": sum(verification_statuses.values()),
        "verification_met": verification_statuses["met"],
        "verification_partial": verification_statuses["partial"],
        "verification_not_assessed": verification_statuses["not_assessed"],
        "verification_absent": verification_statuses["absent"],
        "native_version": native["libhdf5_version"],
        "native_enforced": native_statuses["enforced"],
        "native_partial": native_statuses["partial"],
        "native_diverges": native_statuses["diverges"],
        "native_unmeasured": native_statuses["unmeasured"],
        "findings": int(finding_match.group(1)),
        "backlog": len(backlog),
        "messages": int(routing_match.group(1)),
        "unrouted": int(routing_match.group(2)),
        "unanalyzable": int(routing_match.group(3)),
    }


def main() -> int:
    if not WORKFLOW.is_file():
        fail("docs/H5POLICY_WORKFLOW.md is missing")

    text = WORKFLOW.read_text()
    required = (
        "## Assessment boundary",
        "## Workflow at a glance",
        "### 1. Select the profile",
        "### 7. Interpret the report before acting",
        "## Evidence base and finding provenance",
        "### From bytes to a classified finding",
        "### How the class is justified",
        "## How complete is invariant coverage?",
        "## Acting on the decision",
        "valid JSON",
        "`analysis.complete`",
        "`analysis.extent_overlap_truncated`",
        "--continue-after-rejection",
        "metadata cache image is validated in two passes",
        "[exact-build probe](../h5policy/tools/probe/README.md)",
    )
    missing = [fragment for fragment in required if fragment not in text]
    if missing:
        fail("workflow lacks " + ", ".join(repr(item) for item in missing))

    live_profiles, live_decisions = command_contract()
    doc_profiles, doc_decisions = documented_contract(text)
    if doc_profiles != live_profiles:
        fail(
            f"documented profiles {sorted(doc_profiles)!r} != "
            f"CLI profiles {sorted(live_profiles)!r}"
        )
    if doc_decisions != live_decisions:
        fail(
            f"documented decisions {doc_decisions!r} != "
            f"CLI decisions {live_decisions!r}"
        )

    evidence = evidence_contract()
    evidence_fragments = (
        f"**{evidence['findings']} finding codes**",
        f"**{evidence['backlog']} semantic-\nbacklog entries**",
        f"**{evidence['messages']} in-pickle message\nvariants**",
        f"**{evidence['unrouted']} unrouted**",
        f"**{evidence['unanalyzable']} unanalyzable**",
        f"**{evidence['invariants']} named invariants across "
        f"{evidence['records']}\nselected record families**",
        f"**{evidence['covered']} families are marked `covered`, "
        f"{evidence['partial']} `partial`, and "
        f"{evidence['coverage_gap']} `coverage_gap`.**",
        f"`enforced` for {evidence['oracle_enforced']} families and\n"
        f"`partial` for {evidence['oracle_partial']}",
        f"Of **{evidence['verification_total']} assurance slots**, "
        f"**{evidence['verification_met']}\nare `met`, "
        f"{evidence['verification_partial']} `partial`, "
        f"{evidence['verification_not_assessed']} `not_assessed`, and "
        f"{evidence['verification_absent']} `absent`**",
        f"`libhdf5` {evidence['native_version']}",
        f"**{evidence['native_enforced']} families are measured `enforced`, "
        f"{evidence['native_partial']}\n`partial`, "
        f"{evidence['native_diverges']} `diverges`, and "
        f"{evidence['native_unmeasured']} `unmeasured`**",
    )
    normalized_text = " ".join(text.split())
    missing_evidence = [
        fragment
        for fragment in evidence_fragments
        if " ".join(fragment.split()) not in normalized_text
    ]
    if missing_evidence:
        fail(
            "workflow evidence summary lacks "
            + ", ".join(repr(item) for item in missing_evidence)
        )

    index_link = "[HDF5 file assessment workflow](H5POLICY_WORKFLOW.md)"
    if index_link not in DOC_INDEX.read_text():
        fail("docs/README.md does not link the workflow")
    guide_link = (
        "[Assessing an HDF5 File with `h5policy`]"
        "(../docs/H5POLICY_WORKFLOW.md)"
    )
    if guide_link not in POLICY_GUIDE.read_text():
        fail("h5policy/README.md does not link the workflow")

    print(
        "H5POLICY WORKFLOW DOC CHECK OK: "
        f"{len(doc_profiles)} profiles, {len(doc_decisions)} decisions, "
        f"{evidence['invariants']} invariants, and "
        f"{evidence['verification_total']} assurance slots match"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
