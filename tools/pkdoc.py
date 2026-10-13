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
    python3 tools/pkdoc.py --index docs/spec/index.yml
    python3 tools/pkdoc.py --index docs/spec/index.yml --check
"""

# Defers evaluation of this file's `X | None`-style annotations to strings,
# so they don't raise TypeError on Python < 3.10 (matches the same import in
# check_hygiene.py / check_ssp_control_evidence.py / check_tutorial.py).
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML not installed.  Run: pip install pyyaml")


HDF5_FMT4_URL = (
    "https://support.hdfgroup.org/documentation/hdf5/latest/_f_m_t4.html"
)
VALID_COVERAGE = {"covered", "partial", "not-covered"}
FMT4_SECTION_ORDER = (
    "I", "I.A", "I.B", "I.C", "I.D",
    "II", "II.A", "II.B", "II.C",
    "III", "III.A", "III.A.1", "III.A.2", "III.B", "III.C", "III.D",
    "III.E", "III.F", "III.G", "III.H", "III.I", "III.J",
    "IV", "IV.A", "IV.A.1", "IV.A.2", "IV.A.3",
    "IV.A.3.a", "IV.A.3.b", "IV.A.3.c", "IV.A.3.d", "IV.A.3.e",
    "IV.A.3.f", "IV.A.3.g", "IV.A.3.h", "IV.A.3.i", "IV.A.3.j",
    "IV.A.3.k", "IV.A.3.l", "IV.A.3.m", "IV.A.3.n", "IV.A.3.o",
    "IV.A.3.p", "IV.A.3.q", "IV.A.3.r", "IV.A.3.s", "IV.A.3.t",
    "IV.A.3.u", "IV.A.3.v", "IV.A.3.w", "IV.A.3.x", "IV.A.3.y", "IV.B",
    "V", "VI",
    "VII", "VII.A", "VII.B", "VII.C", "VII.D", "VII.E",
    "VIII", "VIII.A", "VIII.B", "VIII.C", "VIII.D",
)


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
        doc = yaml.safe_load(f)
    if not isinstance(doc, dict):
        raise ValueError(f"{path}: expected a YAML mapping")
    return doc


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


def type_nodes(type_info: dict):
    """Yield a type or variant node and all of its nested variants."""
    yield type_info
    for variant in (type_info.get("variants") or {}).values():
        if isinstance(variant, dict):
            yield from type_nodes(variant)


def display_name(identifier: str, info: dict | None = None) -> str:
    """Return a specification-facing label while retaining identifiers elsewhere."""
    if info:
        explicit = (info.get("title") or info.get("label") or "").strip()
        if explicit:
            return explicit

    version_pair = re.fullmatch(r"v(\d+)_v(\d+)", identifier)
    if version_pair:
        return f"Versions {version_pair.group(1)} and {version_pair.group(2)}"

    special = {
        "addr": "Address",
        "btree": "B-tree",
        "bt1": "Version 1 B-tree",
        "bt2": "Version 2 B-tree",
        "dspace": "Dataspace",
        "dtype": "Datatype",
        "drv": "Driver",
        "elm": "Element",
        "eof": "End-of-file",
        "filt": "Filtered",
        "fs": "Free-space",
        "hdr": "Header",
        "id": "ID",
        "idx": "Index",
        "msg": "Message",
        "ndims": "Number of Dimensions",
        "nrec": "Number of Records",
        "oh": "Object Header",
        "obj": "Object",
        "res": "Reserved",
        "sohm": "SOHM",
        "stab": "Symbol Table",
        "super": "Superblock",
        "vds": "VDS",
        "vers": "Version",
    }
    words: list[str] = []
    for token in identifier.strip("_").split("_"):
        if not token:
            continue
        if token in special:
            words.append(special[token])
        elif token == "sizeof":
            words.append("Size of")
        elif re.fullmatch(r"v\d+", token):
            words.append(f"Version {token[1:]}")
        elif re.fullmatch(r"res\d+", token):
            words.append("Reserved")
        else:
            words.append(token.capitalize())
    return " ".join(words) or identifier


# ── Markdown renderer ─────────────────────────────────────────────────────────

def field_table(fields: dict, title: str) -> str:
    rows = [f"**Fields: {title}**", "", "| Field | Pickle identifier | Description |",
            "|-------|-------------------|-------------|"]
    for name, info in fields.items():
        if isinstance(info, dict):
            label = display_name(name, info)
            desc = (info.get("desc") or "").strip()
            note = (info.get("note") or "").strip()
            if note:
                desc = f"{desc} _{note}_"
        else:
            label = display_name(name)
            desc = str(info).strip() if info else ""
        rows.append(f"| {label} | `{name}` | {desc} |")
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
                field_name = str(cell.get("field") or "").strip()
                label = str(cell.get("label") or "").strip()
                if not label and field_name:
                    label = display_name(field_name)
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


def render_type(
    name: str,
    type_yaml: dict,
    heading: str = "##",
    bound_layouts: list[dict] | None = None,
    is_variant: bool = False,
) -> list[str]:
    out: list[str] = []
    title = display_name(name, type_yaml)
    upstream_anchor = (
        type_yaml.get("anchor")
        or (type_yaml.get("upstream") or {}).get("anchor")
        or ""
    ).strip()
    if upstream_anchor:
        out.append(f'<a id="{upstream_anchor}"></a>\n')
    out.append(f"{heading} {title}\n")
    identifier_kind = "union arm" if is_variant else "type"
    out.append(f"Pickle {identifier_kind}: `{name}`.\n")
    desc = (type_yaml.get("desc") or "").strip()
    if desc:
        out.append(f"{desc}\n")
    for layout in (bound_layouts or []) + (type_yaml.get("layouts") or []):
        out.append(layout_table(layout))
    fields = type_yaml.get("fields")
    if fields:
        out.append(field_table(fields, title))
        out.append("")
    for vname, vinfo in (type_yaml.get("variants") or {}).items():
        if not isinstance(vinfo, dict):
            vinfo = {"desc": str(vinfo) if vinfo else ""}
        out.extend(render_type(vname, vinfo, heading=heading + "#", is_variant=True))
    return out


def render_text(doc: dict) -> str:
    lines: list[str] = []

    section = doc.get("section", "")
    if section:
        lines.append(f"# {section}\n")

    upstream = doc.get("upstream") or {}
    upstream_sections = upstream.get("sections") or []
    if isinstance(upstream_sections, str):
        upstream_sections = [upstream_sections]
    upstream_anchor = (upstream.get("anchor") or "").strip()
    if upstream_anchor:
        lines.append(f'<a id="{upstream_anchor}"></a>\n')
    upstream_url = HDF5_FMT4_URL + (f"#{upstream_anchor}" if upstream_anchor else "")
    if upstream_sections:
        section_text = ", ".join(str(value) for value in upstream_sections)
        version = str(upstream.get("version") or "4.0")
        coverage = str(doc.get("coverage") or "partial").replace("-", " ").title()
        lines.append(
            f"Upstream: [HDF5 File Format Specification {version}, "
            f"section {section_text}]({upstream_url}) · Coverage: **{coverage}**\n"
        )

    intro = (doc.get("intro") or "").strip()
    if intro:
        lines.append(intro)
        lines.append("")

    layouts = doc.get("layouts") or []
    bound_layouts: dict[str, list[dict]] = {}
    for layout in layouts:
        bound_type = str(layout.get("type") or "").strip()
        if bound_type:
            bound_layouts.setdefault(bound_type, []).append(layout)
        else:
            lines.append(layout_table(layout))

    yaml_types = doc.get("types") or {}
    type_order = doc.get("type_order") or list(yaml_types)
    for type_name in type_order:
        type_info = yaml_types[type_name]
        lines.extend(
            render_type(type_name, type_info, bound_layouts=bound_layouts.get(type_name))
        )
        lines.append("")

    note = (doc.get("note") or "").strip()
    if note:
        lines.append(f"> **Note:** {note}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render(doc: dict, out_path: Path) -> None:
    text = render_text(doc)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text)
    print(f"Written: {out_path}")


def flatten_sections(sections: list[dict], parent: str | None = None):
    """Yield manifest sections in display order with their depth and parent."""
    for section in sections:
        yield section, parent
        yield from flatten_sections(section.get("children") or [], section.get("id"))


def manifest_doc_link(section: dict) -> str | None:
    stem = str(section.get("doc") or "").strip()
    if not stem:
        return None
    anchor = str(section.get("local_anchor") or "").strip()
    return f"{stem}.md" + (f"#{anchor}" if anchor else "")


def render_section_list(sections: list[dict], depth: int = 0) -> list[str]:
    lines: list[str] = []
    for section in sections:
        section_id = str(section.get("id") or "").strip()
        title = str(section.get("title") or "").strip()
        label = f"{section_id}. {title}"
        link = manifest_doc_link(section)
        if link:
            label = f"[{label}]({link})"
        status = str(section.get("status") or "not-covered").replace("-", " ").title()
        note = str(section.get("note") or "").strip()
        suffix = f" — {status}"
        if note:
            suffix += f"; {note}"
        lines.append(f"{'  ' * depth}- {label}{suffix}")
        children = section.get("children") or []
        if children:
            lines.extend(render_section_list(children, depth + 1))
    return lines


def render_index_text(index: dict) -> str:
    title = str(index.get("title") or "H5Lens HDF5 File Format Reference").strip()
    source = index.get("source") or {}
    intro = str(index.get("intro") or "").strip()
    lines = [f"# {title}", ""]
    if intro:
        lines.extend([intro, ""])

    source_title = str(source.get("title") or "HDF5 File Format Specification").strip()
    source_url = str(source.get("url") or HDF5_FMT4_URL).strip()
    version = str(source.get("version") or "").strip()
    retrieved = str(source.get("retrieved") or "").strip()
    source_label = source_title + (f" Version {version}" if version else "")
    source_line = f"Canonical organization: [{source_label}]({source_url})"
    if retrieved:
        source_line += f" (reviewed {retrieved})"
    lines.extend([source_line + ".", ""])

    lines.extend([
        "Coverage labels describe H5Lens, not the upstream specification:",
        "",
        "- **Covered** — an executable pickle definition and field documentation exist.",
        "- **Partial** — only part of the upstream section or its variants is documented.",
        "- **Not covered** — there is no first-class H5Lens format page yet.",
        "",
        "## Contents",
        "",
    ])
    lines.extend(render_section_list(index.get("sections") or []))

    extensions = index.get("extensions") or []
    if extensions:
        lines.extend(["", "## H5Lens extensions", ""])
        for extension in extensions:
            title = str(extension.get("title") or "").strip()
            doc = str(extension.get("doc") or "").strip()
            anchor = str(extension.get("local_anchor") or "").strip()
            link = f"{doc}.md" + (f"#{anchor}" if anchor else "")
            lines.append(f"- [{title}]({link})")

    lines.extend([
        "",
        "## Reading and maintaining the reference",
        "",
        "Specification names are shown first; executable GNU poke identifiers are shown",
        "alongside them. Pages are generated from [`pickles/`](../../pickles/) and",
        "[`docs/spec/`](../spec/). See the [documentation workflow](../README.md) to",
        "regenerate the pages and validate their mappings.",
        "",
    ])
    return "\n".join(lines)


# ── Checker ───────────────────────────────────────────────────────────────────

def layout_fields(layout: dict) -> set[str]:
    names: set[str] = set()
    for row in (layout.get("rows") or []):
        cells = row if isinstance(row, list) else [row]
        for cell in cells:
            if isinstance(cell, dict) and cell.get("field"):
                names.add(str(cell["field"]))
    return names


def validate_layout_fields(
    layout: dict,
    type_info: dict,
    context: str,
    issues: list[str],
) -> None:
    known = sidecar_names(type_info)
    for name in sorted(layout_fields(layout) - known):
        issues.append(f"layout '{context}' references undocumented field '{name}'")


def check(doc: dict, pk_path: Path) -> bool:
    pk_text = strip_comments(pk_path.read_text())
    pk_types = pk_top_level_types(pk_text)
    yaml_types: dict = doc.get("types") or {}

    issues: list[str] = []
    warnings: list[str] = []

    type_order = doc.get("type_order")
    if type_order is not None:
        if not isinstance(type_order, list):
            issues.append("type_order must be a list")
        elif len(type_order) != len(set(type_order)):
            issues.append("type_order contains duplicate type names")
        elif set(type_order) != set(yaml_types):
            missing = sorted(set(yaml_types) - set(type_order))
            unknown = sorted(set(type_order) - set(yaml_types))
            if missing:
                issues.append("type_order omits: " + ", ".join(missing))
            if unknown:
                issues.append("type_order names unknown types: " + ", ".join(unknown))

    coverage = str(doc.get("coverage") or "").strip()
    if coverage not in VALID_COVERAGE:
        issues.append(
            "coverage must be one of: " + ", ".join(sorted(VALID_COVERAGE))
        )

    upstream = doc.get("upstream") or {}
    if str(upstream.get("version") or "").strip() != "4.0":
        issues.append("upstream.version must be '4.0'")
    upstream_sections = upstream.get("sections") or []
    if isinstance(upstream_sections, str):
        upstream_sections = [upstream_sections]
    if not upstream_sections:
        issues.append("upstream.sections must name at least one canonical section")

    # Layouts are specification data too. Render them during checks so a
    # row that is not exactly four byte columns wide is caught immediately.
    try:
        for layout in (doc.get("layouts") or []):
            layout_table(layout)
            bound_type = str(layout.get("type") or "").strip()
            if bound_type:
                if bound_type not in yaml_types:
                    issues.append(
                        f"layout '{layout.get('title')}' binds unknown type '{bound_type}'"
                    )
                else:
                    validate_layout_fields(
                        layout,
                        yaml_types[bound_type],
                        str(layout.get("title") or "Layout"),
                        issues,
                    )
            elif layout_fields(layout):
                issues.append(
                    f"layout '{layout.get('title')}' uses field references without a type"
                )
        for tname, type_info in yaml_types.items():
            for node in type_nodes(type_info):
                for layout in (node.get("layouts") or []):
                    layout_table(layout)
                    validate_layout_fields(
                        layout,
                        node,
                        f"{tname}: {layout.get('title') or 'Layout'}",
                        issues,
                    )
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


def check_generated(expected: str, generated_path: Path) -> bool:
    if not generated_path.exists():
        print(f"GENERATED CHECK FAILED: missing {generated_path}")
        return False
    if generated_path.read_text() != expected:
        print(f"GENERATED CHECK FAILED: stale {generated_path}")
        return False
    print(f"GENERATED CHECK OK: {generated_path}")
    return True


def check_index(index: dict, index_path: Path) -> bool:
    issues: list[str] = []
    source = index.get("source") or {}
    source_version = str(source.get("version") or "").strip()
    if source_version != "4.0":
        issues.append("source.version must be '4.0'")
    if str(source.get("url") or "").strip() != HDF5_FMT4_URL:
        issues.append(f"source.url must be {HDF5_FMT4_URL}")
    if not str(source.get("retrieved") or "").strip():
        issues.append("source.retrieved must record when the upstream hierarchy was reviewed")

    sections = list(flatten_sections(index.get("sections") or []))
    seen_ids: set[str] = set()
    referenced_docs: set[str] = set()
    section_ids: set[str] = set()
    doc_sections: list[tuple[str, str]] = []

    for section, parent in sections:
        section_id = str(section.get("id") or "").strip()
        title = str(section.get("title") or "").strip()
        status = str(section.get("status") or "").strip()
        doc_stem = str(section.get("doc") or "").strip()

        if not section_id:
            issues.append("manifest section is missing id")
            continue
        if section_id in seen_ids:
            issues.append(f"duplicate manifest section '{section_id}'")
        seen_ids.add(section_id)
        section_ids.add(section_id)
        if parent and not section_id.startswith(parent + "."):
            issues.append(f"section '{section_id}' is not a child of '{parent}'")
        if not title:
            issues.append(f"section '{section_id}' is missing title")
        if status not in VALID_COVERAGE:
            issues.append(
                f"section '{section_id}' has invalid coverage status '{status}'"
            )
        if status == "not-covered" and doc_stem:
            issues.append(f"not-covered section '{section_id}' must not link a page")
        if doc_stem:
            referenced_docs.add(doc_stem)
            doc_sections.append((doc_stem, section_id))

    actual_order = tuple(
        str(section.get("id") or "").strip() for section, _parent in sections
    )
    if actual_order != FMT4_SECTION_ORDER:
        issues.append(
            "section IDs or order differ from the reviewed Version 4.0 hierarchy"
        )

    spec_dir = index_path.parent
    sidecar_paths = {
        path.stem: path for path in spec_dir.glob("*.yml") if path != index_path
    }
    for doc_stem in sorted(referenced_docs - set(sidecar_paths)):
        issues.append(f"manifest links missing sidecar '{doc_stem}.yml'")
    for doc_stem in sorted(set(sidecar_paths) - referenced_docs):
        issues.append(f"sidecar '{doc_stem}.yml' is absent from the manifest")

    loaded_docs: dict[str, dict] = {}
    for stem, path in sidecar_paths.items():
        try:
            loaded_docs[stem] = load_sidecar(path)
        except (OSError, ValueError, yaml.YAMLError) as exc:
            issues.append(str(exc))

    for stem, doc in loaded_docs.items():
        upstream = doc.get("upstream") or {}
        if str(upstream.get("version") or "").strip() != source_version:
            issues.append(f"{stem}.yml upstream version differs from the manifest")
        declared = upstream.get("sections") or []
        if isinstance(declared, str):
            declared = [declared]
        for section_id in declared:
            if str(section_id) not in section_ids:
                issues.append(
                    f"{stem}.yml declares unknown upstream section '{section_id}'"
                )

    for stem, section_id in doc_sections:
        doc = loaded_docs.get(stem) or {}
        declared = (doc.get("upstream") or {}).get("sections") or []
        if isinstance(declared, str):
            declared = [declared]
        if not any(
            section_id == str(parent) or section_id.startswith(str(parent) + ".")
            for parent in declared
        ):
            issues.append(
                f"manifest section '{section_id}' is not declared by {stem}.yml"
            )

    rendered_docs = {stem: render_text(doc) for stem, doc in loaded_docs.items()}
    for section, _parent in sections:
        stem = str(section.get("doc") or "").strip()
        anchor = str(section.get("local_anchor") or "").strip()
        if stem and anchor and f'id="{anchor}"' not in rendered_docs.get(stem, ""):
            issues.append(
                f"manifest section '{section.get('id')}' links missing anchor "
                f"'{anchor}' in {stem}.yml"
            )

    for extension in (index.get("extensions") or []):
        stem = str(extension.get("doc") or "").strip()
        anchor = str(extension.get("local_anchor") or "").strip()
        if not str(extension.get("title") or "").strip():
            issues.append("manifest extension is missing title")
        if stem and stem not in sidecar_paths:
            issues.append(f"manifest extension links missing sidecar '{stem}.yml'")
        if stem and anchor and f'id="{anchor}"' not in rendered_docs.get(stem, ""):
            issues.append(
                f"manifest extension links missing anchor '{anchor}' in {stem}.yml"
            )

    if issues:
        print(f"INDEX CHECK FAILED ({index_path}):")
        for issue in issues:
            print(f"  {issue}")
        return False

    print(
        f"INDEX CHECK OK: {len(seen_ids)} upstream sections and "
        f"{len(referenced_docs)} sidecars"
    )
    return True


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Generate or check HDF5 format Markdown and its coverage index."
    )
    source = ap.add_mutually_exclusive_group(required=True)
    source.add_argument("--doc", metavar="SIDECAR.yml",
                        help="path to a YAML prose sidecar")
    source.add_argument("--index", metavar="INDEX.yml",
                        help="path to the format-reference index manifest")
    ap.add_argument("--check", action="store_true",
                    help="check source consistency instead of generating")
    ap.add_argument("--check-generated", metavar="FILE",
                    help="also verify that FILE matches generated output")
    ap.add_argument("--out", metavar="FILE",
                    help="output Markdown path")
    args = ap.parse_args()

    sidecar_path = Path(args.doc or args.index)
    if not sidecar_path.exists():
        sys.exit(f"YAML source not found: {sidecar_path}")

    try:
        doc = load_sidecar(sidecar_path)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        sys.exit(str(exc))

    if args.index:
        expected = render_index_text(doc)
        ok = True
        if args.check:
            ok = check_index(doc, sidecar_path) and ok
        if args.check_generated:
            ok = check_generated(expected, Path(args.check_generated)) and ok
        if args.check or args.check_generated:
            sys.exit(0 if ok else 1)

        out_path = Path(args.out) if args.out else Path("docs/generated/README.md")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(expected)
        print(f"Written: {out_path}")
        return

    pickle_name = doc.get("pickle")
    if not pickle_name:
        sys.exit(f"{sidecar_path}: missing 'pickle:' key")

    pk_path = Path("pickles") / pickle_name
    if not pk_path.exists():
        sys.exit(f"pickle not found: {pk_path}")

    expected = render_text(doc)
    ok = True
    if args.check:
        ok = check(doc, pk_path) and ok
    if args.check_generated:
        ok = check_generated(expected, Path(args.check_generated)) and ok
    if args.check or args.check_generated:
        sys.exit(0 if ok else 1)

    out_path = (
        Path(args.out) if args.out
        else Path("docs/generated") / (sidecar_path.stem + ".md")
    )
    render(doc, out_path)


if __name__ == "__main__":
    main()
