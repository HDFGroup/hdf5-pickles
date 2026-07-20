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

"""pkdoc.py — generate or check specification Markdown from pickle prose sidecars.

Usage:
    python3 tools/pkdoc.py --doc docs/spec/superblock.yml
    python3 tools/pkdoc.py --doc docs/spec/superblock.yml --check
    python3 tools/pkdoc.py --doc docs/spec/superblock.yml --out /tmp/superblock.md
"""

import argparse
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML not installed.  Run: pip install pyyaml")


# ── Helpers ──────────────────────────────────────────────────────────────────

def strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)
    text = re.sub(r"//[^\n]*", "", text)
    return text


def find_matching_brace(text: str, start: int) -> int:
    """Return the index one past the closing brace that matches the opening
    brace assumed to be at position start-1 (depth already = 1 on entry)."""
    depth = 1
    i = start
    while i < len(text) and depth > 0:
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
        i += 1
    return i


# ── Poke type extractor (for --check) ────────────────────────────────────────

def pk_top_level_types(pk_text: str) -> set[str]:
    """Return the set of struct/union type names defined at file scope."""
    return set(re.findall(r"\btype\s+(\w+)\s*=\s*(?:struct|union)", pk_text))


def pk_type_span(pk_text: str, type_name: str) -> str | None:
    """Return the full source text of the named type definition, or None."""
    m = re.search(r"\btype\s+" + re.escape(type_name) + r"\s*=", pk_text)
    if not m:
        return None
    open_pos = pk_text.find("{", m.end())
    if open_pos < 0:
        return None
    close_pos = find_matching_brace(pk_text, open_pos + 1)
    return pk_text[m.start() : close_pos]


# ── YAML sidecar ─────────────────────────────────────────────────────────────

def load_sidecar(path: Path) -> dict:
    with path.open() as f:
        return yaml.safe_load(f)


def sidecar_names(type_info: dict) -> set[str]:
    """Recursively collect every field/variant name documented for one type."""
    names: set[str] = set()
    for fname in (type_info.get("fields") or {}):
        names.add(fname)
    for vname, vinfo in (type_info.get("variants") or {}).items():
        names.add(vname)
        if isinstance(vinfo, dict):
            names.update(sidecar_names(vinfo))
    return names


# ── Markdown renderer ─────────────────────────────────────────────────────────

def field_table(fields: dict) -> str:
    rows = ["| Field | Description |", "|-------|-------------|"]
    for name, info in fields.items():
        if isinstance(info, dict):
            desc = (info.get("desc") or "").strip()
            note = (info.get("note") or "").strip()
            if note:
                desc = f"{desc} _{note}_"
        else:
            desc = str(info).strip() if info else ""
        rows.append(f"| `{name}` | {desc} |")
    return "\n".join(rows)


def layout_table(layout: dict) -> str:
    """Render a four-byte-wide format diagram from a sidecar layout."""
    title = (layout.get("title") or "Layout").strip()
    rows = layout.get("rows") or []
    out = [f"**Layout: {title}**", "", '<table class="format-layout">',
           "  <thead><tr><th>byte</th><th>byte</th><th>byte</th><th>byte</th></tr></thead>",
           "  <tbody>"]

    for row_num, row in enumerate(rows, 1):
        cells = row if isinstance(row, list) else [row]
        used = 0
        rendered: list[str] = []
        for cell in cells:
            if isinstance(cell, dict):
                label = str(cell.get("label") or "")
                span = int(cell.get("span", 1))
                width = str(cell.get("width") or "").strip()
            else:
                label = str(cell)
                span = 1
                width = ""
            if span < 1 or used + span > 4:
                raise ValueError(
                    f"layout '{title}' row {row_num} exceeds four byte columns"
                )
            suffix = f"<sup>{width}</sup>" if width else ""
            colspan = f' colspan="{span}"' if span > 1 else ""
            rendered.append(f"<td{colspan}>{label}{suffix}</td>")
            used += span
        if used != 4:
            raise ValueError(
                f"layout '{title}' row {row_num} uses {used} byte columns, expected 4"
            )
        out.append("    <tr>" + "".join(rendered) + "</tr>")

    out.extend(["  </tbody>", "</table>", ""])
    note = (layout.get("note") or "").strip()
    if note:
        out.extend([note, ""])
    return "\n".join(out)


def render_type(name: str, type_yaml: dict, heading: str = "##") -> list[str]:
    out: list[str] = []
    out.append(f"{heading} `{name}`\n")
    desc = (type_yaml.get("desc") or "").strip()
    if desc:
        out.append(f"{desc}\n")
    for layout in (type_yaml.get("layouts") or []):
        out.append(layout_table(layout))
    fields = type_yaml.get("fields")
    if fields:
        out.append(field_table(fields))
        out.append("")
    for vname, vinfo in (type_yaml.get("variants") or {}).items():
        if not isinstance(vinfo, dict):
            vinfo = {"desc": str(vinfo) if vinfo else ""}
        out.extend(render_type(vname, vinfo, heading=heading + "#"))
    return out


def render(doc: dict, out_path: Path) -> None:
    lines: list[str] = []

    section = doc.get("section", "")
    if section:
        lines.append(f"# {section}\n")

    intro = (doc.get("intro") or "").strip()
    if intro:
        lines.append(intro)
        lines.append("")

    for layout in (doc.get("layouts") or []):
        lines.append(layout_table(layout))

    for type_name, type_info in (doc.get("types") or {}).items():
        lines.extend(render_type(type_name, type_info))
        lines.append("")

    note = (doc.get("note") or "").strip()
    if note:
        lines.append(f"> **Note:** {note}")
        lines.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines).rstrip() + "\n")
    print(f"Written: {out_path}")


# ── Checker ───────────────────────────────────────────────────────────────────

def check(doc: dict, pk_path: Path) -> bool:
    pk_text = strip_comments(pk_path.read_text())
    pk_types = pk_top_level_types(pk_text)
    yaml_types: dict = doc.get("types") or {}

    issues: list[str] = []
    warnings: list[str] = []

    # Layouts are specification data too. Render them during checks so a
    # row that is not exactly four byte columns wide is caught immediately.
    try:
        for layout in (doc.get("layouts") or []):
            layout_table(layout)
        for type_info in yaml_types.values():
            for layout in (type_info.get("layouts") or []):
                layout_table(layout)
    except (TypeError, ValueError) as exc:
        issues.append(str(exc))

    # Types in YAML but not in pickle (stale)
    for tname in yaml_types:
        if tname not in pk_types:
            issues.append(f"YAML type '{tname}' not found in {pk_path.name}")

    # Types in pickle but not in YAML (undocumented), minus the explicit skip list
    skip = set(doc.get("skip_types") or [])
    for tname in sorted(pk_types - set(yaml_types) - skip):
        warnings.append(f"pickle type '{tname}' is not documented in the sidecar")

    # Field/variant names: every name in YAML must appear in the pickle type span
    for tname, type_info in yaml_types.items():
        span = pk_type_span(pk_text, tname)
        if span is None:
            continue  # already reported above
        for name in sorted(sidecar_names(type_info)):
            if not re.search(r"\b" + re.escape(name) + r"\b", span):
                issues.append(
                    f"'{tname}.{name}' documented in YAML but not found in pickle"
                )

    for w in warnings:
        print(f"WARNING: {w}")
    if issues:
        print(f"CHECK FAILED ({pk_path.name}):")
        for issue in issues:
            print(f"  {issue}")
        return False

    print(f"CHECK OK: {pk_path.name}")
    return True


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Generate spec Markdown from a YAML sidecar, or check consistency."
    )
    ap.add_argument("--doc", required=True, metavar="SIDECAR.yml",
                    help="path to the YAML prose sidecar")
    ap.add_argument("--check", action="store_true",
                    help="check YAML/pickle consistency instead of generating")
    ap.add_argument("--out", metavar="FILE",
                    help="output Markdown path (default: docs/generated/<stem>.md)")
    args = ap.parse_args()

    sidecar_path = Path(args.doc)
    if not sidecar_path.exists():
        sys.exit(f"sidecar not found: {sidecar_path}")

    doc = load_sidecar(sidecar_path)

    pickle_name = doc.get("pickle")
    if not pickle_name:
        sys.exit(f"{sidecar_path}: missing 'pickle:' key")

    pk_path = Path("pickles") / pickle_name
    if not pk_path.exists():
        sys.exit(f"pickle not found: {pk_path}")

    if args.check:
        ok = check(doc, pk_path)
        sys.exit(0 if ok else 1)

    out_path = (
        Path(args.out) if args.out
        else Path("docs/generated") / (sidecar_path.stem + ".md")
    )
    render(doc, out_path)


if __name__ == "__main__":
    main()
