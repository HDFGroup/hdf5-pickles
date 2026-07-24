#!/usr/bin/env python3
"""Load, validate, inspect, and export the sharded finding registry.

The authoritative registry has two independent concerns:

* ``registry/findings/catalog/*.yml`` owns one finding definition in exactly
  one record-family shard.
* ``registry/findings/routes/*.yml`` owns the message-to-role routes for one
  ambiguous finding code.

Callers still receive the historical in-memory shape: a mapping keyed by
finding code, with a flattened ``contexts`` list on ambiguous entries.  Keeping
that compatibility at one seam makes the data layout an implementation detail
instead of something every consumer has to understand.
"""
import argparse
import collections
import json
import os
import sys

import yaml
from yaml.constructor import ConstructorError


TOOLS_DIR = os.path.dirname(os.path.realpath(__file__))
REPO = os.path.dirname(TOOLS_DIR)
REGISTRY_ROOT = os.path.join(REPO, "registry", "findings")
CATALOG_DIR = os.path.join(REGISTRY_ROOT, "catalog")
ROUTES_DIR = os.path.join(REGISTRY_ROOT, "routes")
SCHEMA_VERSION = 1


class RegistryError(ValueError):
    """The sharded registry is incomplete, inconsistent, or malformed."""


class _UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader variant that rejects YAML's silent duplicate-key behavior."""


def _construct_unique_mapping(loader, node, deep=False):
    loader.flatten_mapping(node)
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as exc:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found an unhashable key ({exc})",
                key_node.start_mark,
            ) from exc
        if duplicate:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def _load_yaml(path):
    try:
        with open(path, encoding="utf-8") as source:
            document = yaml.load(source, Loader=_UniqueKeyLoader)
    except (OSError, yaml.YAMLError) as exc:
        raise RegistryError(f"{path}: {exc}") from exc
    if not isinstance(document, dict):
        raise RegistryError(f"{path}: top-level YAML value must be a mapping")
    if document.get("schema_version") != SCHEMA_VERSION:
        raise RegistryError(
            f"{path}: schema_version must be {SCHEMA_VERSION}, "
            f"got {document.get('schema_version')!r}"
        )
    return document


def _yaml_paths(directory):
    try:
        names = sorted(os.listdir(directory))
    except OSError as exc:
        raise RegistryError(f"{directory}: {exc}") from exc
    paths = [
        os.path.join(directory, name)
        for name in names
        if name.endswith((".yml", ".yaml"))
    ]
    if not paths:
        raise RegistryError(f"{directory}: no YAML shards found")
    return paths


def _load_catalog(catalog_dir):
    findings = collections.OrderedDict()
    sources = {}
    for path in _yaml_paths(catalog_dir):
        document = _load_yaml(path)
        unknown = set(document) - {"schema_version", "record", "findings"}
        if unknown:
            raise RegistryError(
                f"{path}: unknown top-level keys: {', '.join(sorted(unknown))}"
            )
        record = document.get("record")
        entries = document.get("findings")
        if not isinstance(record, str) or not record:
            raise RegistryError(f"{path}: record must be a non-empty string")
        expected_name = f"{record}.yml"
        if os.path.basename(path) != expected_name:
            raise RegistryError(
                f"{path}: shard for record {record!r} must be named {expected_name}"
            )
        if not isinstance(entries, dict) or not entries:
            raise RegistryError(f"{path}: findings must be a non-empty mapping")
        for code, entry in entries.items():
            if code in findings:
                raise RegistryError(
                    f"{path}: duplicate finding {code}; first defined in "
                    f"{sources[code]}"
                )
            if not isinstance(code, str) or not code.startswith("H5_"):
                raise RegistryError(f"{path}: invalid finding code {code!r}")
            if not isinstance(entry, dict):
                raise RegistryError(f"{path}: {code} must map to an object")
            if entry.get("record") != record:
                raise RegistryError(
                    f"{path}: {code} record is {entry.get('record')!r}, "
                    f"expected {record!r}"
                )
            if "contexts" in entry:
                raise RegistryError(
                    f"{path}: {code} embeds contexts; put routes in "
                    "registry/findings/routes"
                )
            findings[code] = entry
            sources[code] = path
    return findings


def _load_routes(routes_dir, findings):
    routed_codes = set()
    for path in _yaml_paths(routes_dir):
        document = _load_yaml(path)
        unknown = set(document) - {"schema_version", "finding", "routes"}
        if unknown:
            raise RegistryError(
                f"{path}: unknown top-level keys: {', '.join(sorted(unknown))}"
            )
        code = document.get("finding")
        routes = document.get("routes")
        if not isinstance(code, str) or not code:
            raise RegistryError(f"{path}: finding must be a non-empty string")
        expected_name = f"{code}.yml"
        if os.path.basename(path) != expected_name:
            raise RegistryError(
                f"{path}: routes for {code!r} must be named {expected_name}"
            )
        if code in routed_codes:
            raise RegistryError(f"{path}: duplicate route shard for {code}")
        routed_codes.add(code)
        if code not in findings:
            raise RegistryError(f"{path}: routes unknown finding {code}")
        if not findings[code].get("ambiguous"):
            raise RegistryError(f"{path}: routes non-ambiguous finding {code}")
        if not isinstance(routes, list) or not routes:
            raise RegistryError(f"{path}: routes must be a non-empty list")

        contexts = []
        seen_matches = set()
        source_index = 0
        for route_index, route in enumerate(routes):
            if not isinstance(route, dict):
                raise RegistryError(
                    f"{path}: route {route_index} must be a mapping"
                )
            unknown = set(route) - {
                "record", "invariant", "scope", "evidence", "matches"
            }
            if unknown:
                raise RegistryError(
                    f"{path}: route {route_index} has unknown keys: "
                    f"{', '.join(sorted(unknown))}"
                )
            matches = route.get("matches")
            if not isinstance(matches, list) or not matches:
                raise RegistryError(
                    f"{path}: route {route_index} matches must be a non-empty list"
                )
            role = {
                key: value
                for key, value in route.items()
                if key != "matches"
            }
            if not isinstance(role.get("record"), str) or not role["record"]:
                raise RegistryError(
                    f"{path}: route {route_index} record must be a non-empty string"
                )
            for match in matches:
                if not isinstance(match, str) or not match:
                    raise RegistryError(
                        f"{path}: route {route_index} contains an invalid match"
                    )
                if match in seen_matches:
                    raise RegistryError(
                        f"{path}: duplicate match {match!r} for {code}"
                    )
                seen_matches.add(match)
                contexts.append(
                    {
                        "match": match,
                        **role,
                        "_source_index": source_index,
                    }
                )
                source_index += 1

        # Resolution is a substring match.  A longer discriminator must win
        # whenever one rule contains another; source order breaks harmless
        # equal-length ties deterministically.
        contexts.sort(
            key=lambda context: (
                -len(context["match"]),
                context["_source_index"],
            )
        )
        for context in contexts:
            del context["_source_index"]
        findings[code]["contexts"] = contexts

def load_findings(catalog_dir=CATALOG_DIR, routes_dir=ROUTES_DIR):
    """Return all finding definitions with grouped routes flattened to contexts."""
    findings = _load_catalog(catalog_dir)
    _load_routes(routes_dir, findings)
    return findings


def registry_stats(findings):
    """Return stable statistics derived from a loaded finding mapping."""
    ambiguous = sum(bool(entry.get("ambiguous")) for entry in findings.values())
    contexts = sum(
        len(entry.get("contexts", []))
        for entry in findings.values()
    )
    routed = sum(bool(entry.get("contexts")) for entry in findings.values())
    records = collections.Counter(
        entry.get("record") for entry in findings.values()
    )
    return {
        "findings": len(findings),
        "ambiguous_findings": ambiguous,
        "routed_findings": routed,
        "context_rules": contexts,
        "record_families": len(records),
        "findings_by_record": dict(sorted(records.items())),
    }


def export_document(findings):
    """Build the historical flat document for compatibility consumers."""
    return {
        "schema_version": SCHEMA_VERSION,
        "findings": dict(findings),
    }


def write_export(findings, path):
    header = (
        "# Generated compatibility export from registry/findings/catalog and\n"
        "# registry/findings/routes. Do not edit this output by hand.\n"
    )
    rendered = yaml.safe_dump(
        export_document(findings),
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        width=1000,
    )
    if path == "-":
        sys.stdout.write(header + rendered)
        return
    with open(path, "w", encoding="utf-8") as target:
        target.write(header)
        target.write(rendered)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("check", help="load and validate every registry shard")
    stats_parser = subparsers.add_parser("stats", help="print derived statistics")
    stats_parser.add_argument("--json", action="store_true", help="emit JSON")
    export_parser = subparsers.add_parser(
        "export",
        help="write the historical flat YAML document",
    )
    export_parser.add_argument(
        "path",
        nargs="?",
        default="-",
        help="output path (default: stdout)",
    )
    args = parser.parse_args(argv)

    try:
        findings = load_findings()
    except RegistryError as exc:
        parser.exit(1, f"finding-registry: {exc}\n")

    stats = registry_stats(findings)
    if args.command == "check":
        print(
            f"findings={stats['findings']} "
            f"ambiguous={stats['ambiguous_findings']} "
            f"routed={stats['routed_findings']} "
            f"contexts={stats['context_rules']} "
            f"records={stats['record_families']}"
        )
    elif args.command == "stats":
        if args.json:
            print(json.dumps(stats, indent=2, sort_keys=True))
        else:
            print(
                f"findings: {stats['findings']}\n"
                f"ambiguous findings: {stats['ambiguous_findings']}\n"
                f"routed findings: {stats['routed_findings']}\n"
                f"context rules: {stats['context_rules']}\n"
                f"record families: {stats['record_families']}"
            )
            for record, count in stats["findings_by_record"].items():
                print(f"  {record}: {count}")
    else:
        write_export(findings, args.path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
