#!/usr/bin/env python3
"""Enumerate the finding messages h5policy can emit, and where each one routes.

A finding's MESSAGE is the only per-occurrence discriminator a report carries,
so `registry/findings.yml` resolves a shared code's record family by matching
`contexts` rules against it.  That makes an emitted message with no matching
rule a real gap: `resolve_finding` deliberately refuses to fall back to the
entry's own `record` for an `ambiguous` code, so such a finding names no family
at all and `h5cve verify` cannot pick a canary for it.

Enumerating the messages is harder than grepping for string literals, and every
attempt to do it with a regex has undercounted:

  * the message is an ARGUMENT at a fixed position, not the first or last string
    in the call, and calls span lines -- so arguments are split at paren depth;
  * most messages never appear as a literal at their emit site.  They are
    composed inside a helper (`what + " checksum mismatch"`) from a `what` its
    callers supply, or indirected through the shared v2-btree engine's per-client
    spec (`spec.leaf_sig_message`).

Both indirections are declared in the tables below.  Anything else is reported
as UNANALYZABLE rather than skipped: a new composition style must fail loudly,
because silently dropping it is exactly how the gaps this module exists to catch
were introduced.
"""
import glob
import re

PICKLES = "h5policy/pickles/*.pk"

# emit_fn -> (index of the code argument, index of the message argument).
# None for the code index means the helper hard-codes which codes it emits; see
# COMPOSING_HELPERS.
EMIT_SITES = {
    "h5policy_emit_error": (0, 4),
    "h5policy_emit_error_ev": (0, 4),
    "h5policy_emit_error_unlocated": (0, 2),
    # h5_walk.pk: the shared payload bounds check takes BOTH the code and the
    # message from its caller, so its call sites are emit sites in their own
    # right.  Every message it can produce was invisible until this entry.
    "h5policy_payload_range_ok": (3, 6),
    # h5_checked.pk: overflow-checked arithmetic, code and message both supplied.
    "h5policy_checked_add_u64": (3, 7),
    "h5policy_checked_mul_u64": (3, 7),
    # h5_validate.pk: the shared address-in-file predicate.
    "h5policy_addr_in_file": (2, 5),
}

# Helpers that build the message from a caller-supplied `what` and emit a fixed
# set of codes.  fn -> (index of `what`, {code: [suffixes appended to `what`]}).
COMPOSING_HELPERS = {
    # h5_checked.pk: emits `what` verbatim under two codes.
    "h5policy_checked_addr_range_at": (3, {
        "H5_CORRUPT_OFFSET_OUT_OF_FILE": [""],
        "H5_CORRUPT_LENGTH_OVERFLOW": [""],
    }),
    "h5policy_checked_addr_range": (3, {
        "H5_CORRUPT_OFFSET_OUT_OF_FILE": [""],
        "H5_CORRUPT_LENGTH_OVERFLOW": [""],
    }),
    # h5_btree2.pk / h5_dense_links.pk trailing-checksum verifiers.
    "h5policy_chunkindex_verify_trailing_checksum": (6, {
        "H5_CORRUPT_OFFSET_OUT_OF_FILE": [" outside file"],
        "H5_CORRUPT_BAD_CHECKSUM": [" checksum field outside block",
                                    " checksum mismatch"],
    }),
    "h5policy_dense_verify_trailing_checksum": (6, {
        "H5_CORRUPT_OFFSET_OUT_OF_FILE": [" outside file"],
        "H5_CORRUPT_BAD_CHECKSUM": [" checksum field outside block",
                                    " checksum mismatch"],
    }),
    # h5_btree2.pk: the shared geometry check names its B-tree's role.
    "h5policy_validate_v2_btree_geometry": (4, {
        "H5_CORRUPT_V2_BTREE_RECORD_SIZE": [" v2 B-tree record size is zero"],
        "H5_CORRUPT_V2_BTREE_NODE_SIZE": [" v2 B-tree node cannot hold one record"],
    }),
    # h5_chunkindex.pk: extensible-array block revisit detection.
    "h5policy_ea_mark_block": (2, {
        "H5_CORRUPT_CHUNK_INDEX_CYCLE": [" repeats a metadata-block address"],
    }),
    # h5_dense_links.pk: shared bad-charset emitter; callers pass the whole text.
    "h5policy_emit_bad_link_charset": (2, {
        "H5_CORRUPT_LINK_NAME_CHARSET": [""],
    }),
    # h5_walk.pk: chunk-count budget and the not-decoded-yet index note.
    "h5policy_count_chunks": (5, {"H5_RESOURCE_CHUNK_COUNT": [""]}),
    "h5policy_note_btree_addr": (4, {"H5_UNSUPPORTED_PICKLE_COVERAGE_GAP": [""]}),
    # h5_validate.pk: optional superblock addresses; the code is fixed.
    "h5policy_validate_optional_addr": (4, {"H5_CORRUPT_OFFSET_OUT_OF_FILE": [""]}),
}

# The shared v2-btree engine passes `spec.leaf_what : spec.internal_what` into a
# composing helper, so those literals expand exactly like a caller-supplied
# `what`.  _resolve_expr already unions a spec field across every client that
# assigns it, which is what the engine does at runtime -- one code path serves
# all of them -- so no separate handling is needed.


def split_args(src, open_paren):
    """Arguments of the call whose '(' is at src[open_paren], split at depth 1."""
    depth = 0
    current = ""
    out = []
    i = open_paren
    while i < len(src):
        c = src[i]
        if c == "(":
            depth += 1
            if depth == 1:
                i += 1
                continue
        elif c == ")":
            depth -= 1
            if depth == 0:
                out.append(current)
                return out
        if depth == 1 and c == ",":
            out.append(current)
            current = ""
        else:
            current += c
        i += 1
    return out                      # unterminated call; caller treats as unusable


_STRING = re.compile(r'"((?:[^"\\]|\\.)*)"')


def _literal(expr):
    m = _STRING.fullmatch(expr.strip())
    return m.group(1) if m else None


def _spec_fields(sources):
    """field name -> {defining source -> {literal values}}.

    Grouped BY CLIENT on purpose.  The shared v2-btree engine reads several spec
    fields at one emit site (`spec.cycle_code` alongside `spec.cycle_message`),
    and each client supplies a coherent set.  Unioning across clients first
    would pair the chunk index's code with the SOHM index's message and invent
    (code, message) combinations that can never occur at runtime.
    """
    out = {}
    for path, src in sources.items():
        for m in re.finditer(
                r'\b([a-z_]+_(?:message|what|code))\s*=\s*"((?:[^"\\]|\\.)*)"', src):
            out.setdefault(m.group(1), {}).setdefault(path, set()).add(m.group(2))
    return out


def _spec_clients(expr, spec_fields):
    """(fields, clients) for an expression built from spec fields, else None."""
    fields = re.findall(r"spec\.([a-z_]+)", expr)
    if not fields or '"' in expr or any(f not in spec_fields for f in fields):
        return None
    clients = set()
    for f in fields:
        clients |= set(spec_fields[f])
    return fields, clients


def _resolve_expr(expr, spec_fields, client=None):
    """Literal values an emit expression can take, optionally for one client.

    Handles a bare literal, `spec.FIELD`, and a ternary over spec fields.
    Returns None when the expression is not understood -- the caller reports
    that rather than dropping it.
    """
    expr = " ".join(expr.split())
    lit = _literal(expr)
    if lit is not None:
        return {lit}
    if '"' in expr:
        return None
    resolved = _spec_clients(expr, spec_fields)
    if resolved is None:
        return None
    fields, clients = resolved
    values = set()
    for f in fields:
        by_client = spec_fields[f]
        for owner in ([client] if client is not None else by_client):
            values |= by_client.get(owner, set())
    # A spec field assigned "" is a placeholder for a client that does not run
    # the guarded check at all -- h5_chunkindex.pk sets `check_subtree_count = 0`
    # and `subtree_count_message = ""`, so that emit is unreachable for it.  The
    # guard is a runtime condition this static pass cannot evaluate, so drop the
    # empty value rather than report an unroutable message that never occurs.
    # A genuinely empty message from a LITERAL emit is still surfaced: only the
    # spec-field path reaches here.
    values.discard("")
    return values or None


def _helper_bodies(src):
    """[(start, end)] of every COMPOSING_HELPERS definition in one source.

    Inside such a body the message is built from the helper's own PARAMETER, so
    the expression is necessarily non-literal.  Those emits are already accounted
    for by expanding each CALL site, so reporting them again would be noise that
    trains the reader to ignore the unanalyzable list.
    """
    spans = []
    for m in re.finditer(r"^fun\s+([a-z0-9_]+)\s*=", src, re.M):
        if m.group(1) not in COMPOSING_HELPERS and m.group(1) not in EMIT_SITES:
            continue
        nxt = re.compile(r"^fun\s", re.M).search(src, m.end())
        spans.append((m.start(), nxt.start() if nxt else len(src)))
    return spans


def extract(pattern=PICKLES):
    """Return (messages, unanalyzable).

    messages: {code: {message: {source file, ...}}}
    unanalyzable: [(source, function, expression), ...]
    """
    sources = {p: open(p).read() for p in sorted(glob.glob(pattern))}
    spec_fields = _spec_fields(sources)
    messages = {}
    unanalyzable = []

    def add(code, msg, where):
        messages.setdefault(code, {}).setdefault(msg, set()).add(where)

    for path, src in sources.items():
        base = path.split("/")[-1]
        bodies = _helper_bodies(src)
        inside = lambda pos: any(a <= pos < b for a, b in bodies)

        for fn, (code_idx, msg_idx) in EMIT_SITES.items():
            for m in re.finditer(rf"\b{fn}\s*\(", src):
                args = split_args(src, m.end() - 1)
                if len(args) <= max(code_idx, msg_idx):
                    continue
                # When BOTH code and message come from the spec, resolve them
                # per client so each client's code pairs only with its own
                # message.
                spec_code = _spec_clients(" ".join(args[code_idx].split()),
                                          spec_fields)
                spec_msg = _spec_clients(" ".join(args[msg_idx].split()),
                                         spec_fields)
                if spec_code and spec_msg:
                    for client in spec_code[1] & spec_msg[1]:
                        codes = _resolve_expr(args[code_idx], spec_fields, client)
                        msgs_ = _resolve_expr(args[msg_idx], spec_fields, client)
                        for c in codes or ():
                            for v in msgs_ or ():
                                add(c, v, base)
                    continue
                code = _literal(args[code_idx])
                if code is None:
                    # A non-literal CODE is as opaque as a non-literal message:
                    # report it rather than skipping, or a whole emitter can go
                    # unenumerated (this is how h5policy_payload_range_ok's call
                    # sites were missed).
                    if not inside(m.start()):
                        unanalyzable.append(
                            (base, fn, " ".join(args[code_idx].split())[:90]))
                    continue
                values = _resolve_expr(args[msg_idx], spec_fields)
                if values is None:
                    if not inside(m.start()):
                        unanalyzable.append(
                            (base, fn, " ".join(args[msg_idx].split())[:90]))
                    continue
                for v in values:
                    add(code, v, base)

        for fn, (what_idx, codes) in COMPOSING_HELPERS.items():
            for m in re.finditer(rf"\b{fn}\s*\(", src):
                args = split_args(src, m.end() - 1)
                if len(args) <= what_idx:
                    continue
                values = _resolve_expr(args[what_idx], spec_fields)
                if values is None:
                    if not inside(m.start()):
                        unanalyzable.append(
                            (base, fn, " ".join(args[what_idx].split())[:90]))
                    continue
                for what in values:
                    for code, suffixes in codes.items():
                        for suffix in suffixes:
                            add(code, what + suffix, base)

    return messages, unanalyzable


def unrouted(messages, findings, resolve):
    """{code: [messages that resolve to no record]}, ambiguous codes only."""
    out = {}
    for code, msgs in messages.items():
        entry = findings.get(code)
        if not entry or not entry.get("ambiguous"):
            continue
        bad = sorted(m for m in msgs if not resolve(code, m, findings)["record"])
        if bad:
            out[code] = bad
    return out


ROUTING_PATH = "registry/message-routing.yml"

HEADER = """# Finding messages that resolve to NO record family.
#
# This file is a MEASUREMENT, regenerated by `tools/message_routing.py --write`,
# not a hand-maintained list.  `tools/check_registry.py` recomputes it and fails
# on drift in either direction, the same contract libhdf5-evidence.yml uses:
#
#   * a message here that now routes  -> stale; someone fixed it, regenerate
#   * a message that routes to nothing and is NOT here -> a new gap
#
# Why it matters: a finding's message is the only per-occurrence discriminator a
# report carries, so `contexts` rules in findings.yml resolve a shared code's
# family from it.  For an `ambiguous` code, `resolve_finding` deliberately
# refuses to fall back to the entry's own `record`, so a message matching no
# rule names no family at all and `h5cve verify` cannot select a canary for it.
#
# Entries are a backlog, not an accepted state.  Emptying a code's list is the
# work; see the git history of findings.yml for H5_CORRUPT_OFFSET_OUT_OF_FILE,
# H5_CORRUPT_BAD_SIGNATURE and H5_CORRUPT_BAD_CHECKSUM as worked examples.
"""


def write_inventory(unrouted_map, path=ROUTING_PATH):
    import json
    lines = [HEADER, "schema_version: 1", ""]
    if not unrouted_map:
        lines.append("unrouted: {}")
    else:
        lines.append("unrouted:")
        for code in sorted(unrouted_map):
            lines.append(f"  {code}:")
            for msg in sorted(unrouted_map[code]):
                # json.dumps produces a double-quoted scalar that YAML reads
                # back identically, including any embedded quote.
                lines.append(f"    - {json.dumps(msg)}")
    open(path, "w").write("\n".join(lines) + "\n")


if __name__ == "__main__":
    import importlib.machinery
    import importlib.util
    import sys
    import yaml

    loader = importlib.machinery.SourceFileLoader("h5cve", "tools/h5cve")
    spec = importlib.util.spec_from_loader("h5cve", loader)
    h5cve = importlib.util.module_from_spec(spec)
    loader.exec_module(h5cve)
    findings = yaml.safe_load(open("registry/findings.yml"))["findings"]

    messages, unanalyzable = extract()
    for entry in unanalyzable:
        print("UNANALYZABLE %s %s: %s" % entry)
    gaps = unrouted(messages, findings, h5cve.resolve_finding)
    total = sum(len(v) for v in gaps.values())
    if "--write" in sys.argv:
        write_inventory(gaps)
        print(f"wrote {ROUTING_PATH}: {total} unrouted messages, "
              f"{len(gaps)} codes")
    else:
        print(f"{sum(len(v) for v in messages.values())} messages, "
              f"{len(messages)} codes, {total} unrouted across {len(gaps)} codes, "
              f"{len(unanalyzable)} unanalyzable")
