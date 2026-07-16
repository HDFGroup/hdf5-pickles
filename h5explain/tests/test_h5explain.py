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

"""h5explain regression tests.

Drives the explorer in batch mode against the tests/fixtures files and asserts
on its output.  Absolute file offsets are deliberately never asserted: they
depend on the libhdf5 that wrote the fixture.  Where a test needs the address
of a primitive it scans the fixture for that primitive's signature, which is
independent of h5explain's own decoding.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
H5EXPLAIN = os.path.join(REPO, "h5explain", "tools", "h5explain")
FIXTURES = os.path.join(HERE, "fixtures")


def fixture(name):
    return os.path.join(FIXTURES, name)


def explain(name, *commands, stdin=None, expect_rc=0):
    """Run a batch h5explain session and return its combined output."""
    args = [H5EXPLAIN]
    for cmd in commands:
        args += ["-c", cmd]
    args.append(fixture(name))
    proc = subprocess.run(args, capture_output=True, text=True,
                          input="" if stdin is None else stdin)
    if proc.returncode != expect_rc:
        raise AssertionError(
            f"{args} returned {proc.returncode}, expected {expect_rc}\n"
            f"stdout={proc.stdout}\nstderr={proc.stderr}")
    return proc.stdout + proc.stderr


def signature_offsets(name, signature):
    """Locate primitives by on-disk signature, without asking h5explain."""
    with open(fixture(name), "rb") as fh:
        raw = fh.read()
    offsets = []
    cursor = raw.find(signature)
    while cursor >= 0:
        offsets.append(cursor)
        cursor = raw.find(signature, cursor + 1)
    if not offsets:
        raise AssertionError(f"{name} contains no {signature!r} signature")
    return raw, offsets


def signature_offset(name, signature):
    return signature_offsets(name, signature)[1][0]


def raw_chunk_btree_offset(name):
    """Offset of the v1 B-tree that indexes raw chunks, not group links.

    A v1 B-tree node's type byte follows its signature: 0 is a symbol table,
    1 is a raw data chunk index.  Only the latter needs the chunk rank.
    """
    raw, offsets = signature_offsets(name, b"TREE")
    for off in offsets:
        if raw[off + 4] == 1:
            return off
    raise AssertionError(f"{name} has no raw-chunk v1 B-tree")


# -- batch plumbing ---------------------------------------------------------

def test_command_option_runs_and_exits():
    out = explain("latest.h5", "pwd")
    assert "superblock" in out, out
    # --command implies --quiet, so a scripted session stays diffable.
    assert "interactive HDF5 byte-level explorer" not in out, out


def test_piped_stdin_runs_commands():
    proc = subprocess.run([H5EXPLAIN, fixture("latest.h5")],
                          input="root\npwd\n", capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert "/ at" in proc.stdout, proc.stdout
    assert "interactive HDF5 byte-level explorer" not in proc.stdout, proc.stdout


def test_command_option_does_not_drain_stdin():
    """--command must not block on a stdin the caller never closes.

    A caller that passes --command has already said where its commands come
    from; draining stdin as well would hang the session forever.
    """
    read_fd, write_fd = os.pipe()
    try:
        proc = subprocess.Popen([H5EXPLAIN, "-c", "pwd", fixture("latest.h5")],
                                stdin=read_fd, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True)
        try:
            out, _ = proc.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            raise AssertionError("h5explain -c blocked on an open stdin")
        assert "superblock at" in out, out
    finally:
        os.close(read_fd)
        os.close(write_fd)


def test_help_documents_batch_mode():
    proc = subprocess.run([H5EXPLAIN, "--help"], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert "--batch" in proc.stdout, proc.stdout
    assert "--command" in proc.stdout, proc.stdout


def test_missing_command_argument_is_rejected():
    proc = subprocess.run([H5EXPLAIN, "-c"], capture_output=True, text=True)
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "requires an argument" in proc.stderr, proc.stderr


def test_banner_is_shown_when_not_scripted():
    # No -c and no piped commands: the session still prints its banner.
    proc = subprocess.run([H5EXPLAIN, fixture("latest.h5")],
                          stdin=subprocess.DEVNULL,
                          capture_output=True, text=True)
    assert "interactive HDF5 byte-level explorer" in proc.stdout, proc.stdout


# -- startup and navigation -------------------------------------------------

def test_start_lands_on_superblock():
    out = explain("latest.h5", "pwd")
    assert "superblock at 0UL#B (HDF5 superblock)" in out, out


def test_root_reaches_root_object_header():
    for name in ("latest.h5", "earliest.h5", "dense.h5", "chunked.h5"):
        out = explain(name, "root", "pwd")
        assert "/ at" in out and "(object header)" in out, (name, out)


def test_cd_labels_the_path():
    out = explain("latest.h5", "root", 'cd ("group_a")', "pwd")
    assert "/group_a at" in out, out
    assert "(object header)" in out, out


def test_userblock_files_translate_metadata_addresses():
    for name in ("userblock_latest.h5", "userblock_earliest.h5"):
        out = explain(name, "h5super", "root", 'cd ("group_a/values")', "pwd",
                      "check")
        assert "superblock at 512UL#B" in out, (name, out)
        assert "/group_a/values" in out, (name, out)
        assert "h5policy: accept" in out, (name, out)
        assert "did not decode" not in out, (name, out)


def test_cd_unknown_link_reports_and_stays_put():
    out = explain("latest.h5", "root", 'cd ("no_such_link")', "pwd")
    assert 'no hard link named "no_such_link"' in out, out
    # The failed cd must not move the cursor off the root header.
    assert "/ at" in out, out


def test_cd_requires_an_object_header():
    out = explain("latest.h5", 'cd ("group_a")')
    assert "only available when the current primitive is an object header" in out, out


def test_cd_walks_a_multi_component_relative_path():
    out = explain("latest.h5", "root", 'cd ("group_a/values")', "pwd")
    assert "/group_a/values at" in out, out


def test_cd_walks_an_absolute_path():
    out = explain("latest.h5", "root", 'cd ("group_a")', 'cd ("/top")', "pwd")
    assert "/top at" in out, out


def test_cd_parent_goes_up_one_level():
    out = explain("latest.h5", "root", 'cd ("group_a/values")', 'cd ("..")', "pwd")
    assert "/group_a at" in out, out


def test_cd_parent_clamps_at_the_root():
    out = explain("latest.h5", "root", 'cd ("..")', 'cd ("..")', "pwd")
    assert "/ at" in out, out


def test_cd_mixed_updir_path():
    out = explain("latest.h5", "root", 'cd ("group_a")',
                  'cd ("../group_a/./values")', "pwd")
    assert "/group_a/values at" in out, out


def test_cd_failure_part_way_leaves_the_cursor_alone():
    # The walk resolves the whole path before moving, so a bad component must
    # not strand the cursor half-way down it.
    out = explain("latest.h5", "root", 'cd ("group_a/no_such_link")', "pwd")
    assert 'no hard link named "no_such_link"' in out, out
    assert "/ at" in out, out


def test_cd_parent_from_unlabeled_header_explains_itself():
    off = signature_offset("latest.h5", b"OHDR")
    out = explain("latest.h5", 'gos ("%d")' % off, 'cd ("..")', "pwd")
    assert "cannot resolve" in out, out
    assert "(unlabeled) at" in out, out


def test_cd_relative_still_works_from_an_unlabeled_header():
    off = signature_offset("latest.h5", b"OHDR")
    out = explain("latest.h5", 'gos ("%d")' % off, 'cd ("group_a")', "pwd")
    assert "group_a at" in out, out


def test_cd_dense_multi_component_path():
    out = explain("dense.h5", "root", 'cd ("dense/child_03")', "pwd")
    assert "/dense/child_03 at" in out, out


def test_cd_symbol_table_multi_component_path():
    out = explain("earliest.h5", "root", 'cd ("group_a/values")', "pwd")
    assert "/group_a/values at" in out, out


# -- history ----------------------------------------------------------------

def test_back_retraces_more_than_one_step():
    out = explain("latest.h5", "root", 'cd ("group_a")', 'cd ("values")',
                  "back", "pwd", "back", "pwd", "back", "pwd")
    lines = [l for l in out.splitlines() if " at " in l and "current:" not in l]
    assert len(lines) == 3, out
    assert "/group_a at" in lines[0], lines
    assert "/ at" in lines[1], lines
    assert "superblock at" in lines[2], lines


def test_back_reports_an_exhausted_history():
    out = explain("latest.h5", "back", "back")
    assert out.count("no previous location") == 2, out


def test_failed_cd_does_not_push_history():
    # A cd that found nothing never moved, so back must not treat it as a step.
    out = explain("latest.h5", "root", 'cd ("no_such_link")', "back", "pwd")
    assert "superblock at" in out, out


# -- bounds -----------------------------------------------------------------

def test_go_past_eof_is_refused():
    size = os.path.getsize(fixture("latest.h5"))
    out = explain("latest.h5", 'gos ("%d")' % (size + 1000), "pwd")
    assert "past the end of the file" in out, out
    assert "unhandled" not in out, out
    # The refused go must leave the cursor where it was.
    assert "superblock at" in out, out


def test_go_to_eof_offset_is_refused():
    size = os.path.getsize(fixture("latest.h5"))
    out = explain("latest.h5", 'gos ("%d")' % size, "pwd")
    assert "past the end of the file" in out, out


def test_go_near_eof_decodes_as_raw_without_raising():
    # The last byte is in range but has no room for a 4-byte signature; kind
    # detection must fall back to raw rather than read past the end.
    size = os.path.getsize(fixture("latest.h5"))
    out = explain("latest.h5", 'gos ("%d")' % (size - 1), "pwd")
    assert "raw bytes" in out, out
    assert "unhandled" not in out, out


def test_start_offset_past_eof_is_refused():
    size = os.path.getsize(fixture("latest.h5"))
    proc = subprocess.run([H5EXPLAIN, "-c", "pwd", fixture("latest.h5"),
                           str(size + 1000)],
                          capture_output=True, text=True, input="")
    out = proc.stdout + proc.stderr
    assert "past the end of the file" in out, out


# -- link listing across the three storage layouts --------------------------

def test_ls_lists_compact_links():
    out = explain("latest.h5", "root", "ls")
    assert "group_a ->" in out, out
    assert "top ->" in out, out


def test_ls_lists_symbol_table_links():
    # earliest.h5 stores group links in a v1 B-tree plus local heap.
    out = explain("earliest.h5", "root", "ls")
    assert "group_a ->" in out, out
    assert "top ->" in out, out


def test_ls_lists_dense_links():
    # dense.h5's group is past the compact-to-dense threshold, so its links
    # live in a fractal heap indexed by a v2 B-tree.
    out = explain("dense.h5", "root", 'cd ("dense")', "ls")
    found = [n for n in range(24) if ("child_%02d ->" % n) in out]
    assert len(found) == 24, f"found {len(found)} of 24 dense links\n{out}"


def test_ls_on_empty_result_says_so():
    out = explain("latest.h5", "root", 'cd ("top")', "ls")
    # A dataset header has no hard links.
    assert "(none found)" in out, out


# -- kind detection ---------------------------------------------------------

def test_detect_kind_names_each_signed_primitive():
    cases = [
        ("chunked.h5", b"FAHD", "fixed array header"),
        ("chunked.h5", b"EAHD", "extensible array header"),
        ("chunked.h5", b"BTHD", "version 2 B-tree header"),
        ("earliest.h5", b"TREE", "version 1 B-tree node"),
        ("earliest.h5", b"SNOD", "symbol table node"),
        ("earliest.h5", b"HEAP", "local heap"),
        ("latest.h5", b"OHDR", "object header"),
    ]
    for name, sig, expected in cases:
        off = signature_offset(name, sig)
        out = explain(name, 'gos ("%d")' % off, "pwd")
        assert expected in out, (name, sig, expected, out)


def heuristic_false_positive_offset(name):
    """An offset the v1-header probe accepts but that is not a header.

    latest.h5 only has signature-bearing v2 headers, so anything the probe
    (version 1, reserved 0, 1..255 messages) accepts there is a false positive.
    """
    with open(fixture(name), "rb") as fh:
        raw = fh.read()
    for off in range(len(raw) - 4):
        if raw[off] == 1 and raw[off + 1] == 0:
            count = raw[off + 2] | (raw[off + 3] << 8)
            if 1 <= count <= 255:
                return off
    raise AssertionError(f"{name} has no heuristic false positive to test")


def test_inferred_kind_is_marked_as_such():
    # earliest.h5's root is a v1 header: reachable, but signature-free.  Going
    # there blind means the kind was guessed, and pwd has to say so.
    out = explain("earliest.h5", 'gos ("96")', "pwd")
    assert "(object header)" in out, out
    assert "inferred: no signature" in out, out


def test_signature_confirmed_kind_is_not_marked():
    off = signature_offset("latest.h5", b"OHDR")
    out = explain("latest.h5", 'gos ("%d")' % off, "pwd")
    assert "(object header)" in out, out
    assert "inferred" not in out, out


def test_structurally_reached_v1_header_is_not_marked():
    # Same signature-free header as above, but reached through the superblock's
    # root address: the pointer corroborates the kind, so no warning is due.
    out = explain("earliest.h5", "root", "pwd")
    assert "(object header)" in out, out
    assert "inferred" not in out, out


def test_inferred_marking_survives_back():
    # Confidence is part of the location, so retracing to it must restore it.
    out = explain("earliest.h5", 'gos ("96")', "root", "back", "pwd")
    assert "inferred: no signature" in out, out


def test_heuristic_false_positive_is_flagged_and_fails_cleanly():
    off = heuristic_false_positive_offset("latest.h5")
    out = explain("latest.h5", 'gos ("%d")' % off, "pwd", "info")
    # The probe misfires here, so the marker is the only thing standing between
    # the user and a confident-looking decode of unrelated bytes.
    assert "inferred: no signature" in out, out
    assert "does not decode" in out, out
    # A misfire must not surface as a raw poke backtrace.
    assert "unhandled" not in out, out


def test_info_on_undecodable_primitive_points_at_dump():
    off = heuristic_false_positive_offset("latest.h5")
    out = explain("latest.h5", 'gos ("%d")' % off, "info")
    assert "use dump to inspect the raw bytes" in out, out


def test_detect_kind_finds_v1_object_header_without_signature():
    # earliest.h5 has v1 headers, which carry no signature; root must still
    # resolve to an object header via the version/message-count heuristic.
    out = explain("earliest.h5", "root", "pwd")
    assert "(object header)" in out, out


# -- primitive-specific inspection ------------------------------------------

def test_traverse_rejects_primitives_without_an_index():
    out = explain("latest.h5", "root", "traverse")
    assert "traverse is available from TREE, BTHD, FAHD, or EAHD" in out, out


def test_traverse_walks_a_fixed_array():
    off = signature_offset("chunked.h5", b"FAHD")
    out = explain("chunked.h5", 'gos ("%d")' % off, "traverse")
    assert "FAHD" in out or "fa_hdr" in out or "fa_dblock" in out, out


def test_v1_btree_ndims_is_learned_from_the_layout_message():
    """Visiting the dataset header first teaches h5explain the chunk rank.

    Without that context the raw-chunk B-tree decode falls back to ndims=1 and
    h5explain says so; with it the note is gone and the node's extent grows to
    cover the real key width.
    """
    off = raw_chunk_btree_offset("earliest.h5")
    cold = explain("earliest.h5", 'gos ("%d")' % off, "info")
    assert "set_bt1_ndims" in cold, cold

    warm = explain("earliest.h5", "root", 'cd ("chunked")',
                   'gos ("%d")' % off, "info")
    assert "set_bt1_ndims" not in warm, warm

    def extent(out):
        marker = "extent="
        line = [l for l in out.splitlines() if marker in l][0]
        return int(line.split(marker)[1].split("UL#b")[0])

    assert extent(warm) > extent(cold), (extent(cold), extent(warm))


def test_msgs_requires_an_object_header():
    out = explain("latest.h5", "msgs")
    assert "only available when the current primitive is an object header" in out, out


def test_msgs_decodes_dataset_messages():
    out = explain("latest.h5", "root", 'cd ("top")', "msgs")
    assert "oh_msg_layout" in out, out


def test_h5dump_covers_the_primitive_extent():
    out = explain("latest.h5", "root", "h5dump")
    # The hex dump is anchored at the header and shows its signature bytes.
    assert "OHDR" in out or "4f 48 44 52" in out, out


# -- offset parsing ---------------------------------------------------------

def test_gos_accepts_hex_and_decimal():
    off = signature_offset("latest.h5", b"OHDR")
    dec = explain("latest.h5", 'gos ("%d")' % off, "pwd")
    hexed = explain("latest.h5", 'gos ("0x%x")' % off, "pwd")
    assert "object header" in dec, dec
    assert "object header" in hexed, hexed


def test_gos_rejects_a_non_numeric_offset():
    out = explain("latest.h5", 'gos ("banana")')
    assert "invalid offset" in out, out


def test_start_offset_argument_is_validated():
    proc = subprocess.run([H5EXPLAIN, fixture("latest.h5"), "banana"],
                          capture_output=True, text=True)
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "must be decimal or hexadecimal" in proc.stderr, proc.stderr


# -- policy integration (check / check_all / profile) ------------------------

# A private copy of the h5policy corpus, generated by run.sh.  Deliberately not
# h5policy/tests: reading another suite's fixtures while it regenerates them
# races, and this suite has no business writing there.
CORPUS = os.path.join(HERE, "corpus")


def corpus(rel):
    return os.path.join(CORPUS, rel)


def explain_path(path, *commands):
    """Run a batch session against a path outside tests/fixtures."""
    args = [H5EXPLAIN]
    for cmd in commands:
        args += ["-c", cmd]
    args.append(path)
    proc = subprocess.run(args, capture_output=True, text=True, input="")
    if proc.returncode != 0:
        raise AssertionError(f"{args} returned {proc.returncode}\n{proc.stderr}")
    return proc.stdout + proc.stderr


BAD_BTREE = "malformed/bad_btree_key.h5"


def test_check_accepts_a_clean_file():
    out = explain("latest.h5", "root", "check")
    assert "h5policy: accept" in out, out
    assert "The walk reached it." in out, out


def test_check_reports_the_profile_it_used():
    out = explain("latest.h5", "root", "check")
    assert "profile untrusted_strict" in out, out


def test_check_rejects_a_corrupt_file():
    out = explain_path(corpus(BAD_BTREE), "root", "check")
    assert "h5policy: reject_corrupt" in out, out


def test_check_surfaces_a_finding_anchored_to_the_cursors_object():
    # The finding's bytes are at the heap (0xa0), outside the root header's
    # extent, but it is a finding *about* the root group.  Standing on the root
    # must surface it; filtering on the byte offset alone would not.
    out = explain_path(corpus(BAD_BTREE), "root", "check")
    assert "H5_CORRUPT_HEAP_OFFSET_OUT_OF_BOUNDS" in out, out
    assert "bearing on /" in out, out


def test_check_all_lists_every_finding():
    out = explain_path(corpus(BAD_BTREE), "check_all")
    assert "1 finding(s):" in out, out
    assert "H5_CORRUPT_HEAP_OFFSET_OUT_OF_BOUNDS" in out, out


def test_check_all_on_a_clean_file_says_no_findings():
    out = explain("latest.h5", "check_all")
    assert "No findings." in out, out


def test_check_reports_findings_elsewhere_in_the_file():
    # Cursor on a primitive with no findings of its own, in a file that has one.
    out = explain_path(corpus(BAD_BTREE), "h5super", "check")
    assert "further finding(s) elsewhere" in out, out


def test_check_says_not_reached_for_an_unreachable_header():
    # A heuristic false positive in a clean file: the walk completed and never
    # went there, so h5policy vouches for nothing at this offset.
    off = heuristic_false_positive_offset("latest.h5")
    out = explain("latest.h5", 'gos ("%d")' % off, "check")
    assert "never reached it" in out, out


def test_check_resolves_reachability_for_a_fixed_array_header():
    # h5policy's reachability record covers what its walk read, so a chunk index
    # is answerable now; it used to report that reachability was unknown here.
    off = signature_offset("chunked.h5", b"FAHD")
    out = explain("chunked.h5", 'gos ("%d")' % off, "check")
    assert "The walk reached it." in out, out


def test_check_resolves_reachability_for_a_local_heap():
    off = signature_offset("earliest.h5", b"HEAP")
    out = explain("earliest.h5", 'gos ("%d")' % off, "check")
    assert "The walk reached it." in out, out


def test_check_resolves_reachability_for_array_and_btree_structures():
    for name, sig in (("chunked.h5", b"EAHD"), ("chunked.h5", b"BTHD"),
                      ("chunked.h5", b"FADB"), ("earliest.h5", b"SNOD"),
                      ("earliest.h5", b"TREE")):
        off = signature_offset(name, sig)
        out = explain(name, 'gos ("%d")' % off, "check")
        assert "The walk reached it." in out, (name, sig, out)


# The reachability states, queried directly.  h5explain_cursor_reachability is
# the decision point, and some of its branches are masked in `check` output --
# a finding on the cursor suppresses the reachability line entirely.
REACH_REACHED, REACH_NOT_REACHED, REACH_UNRECORDED = 0, 1, 2
REACH_INCOMPLETE, REACH_RECORD_FULL = 3, 4


def reachability(name, *setup):
    cmds = list(setup) + ["h5explain_run_policy;",
                          'printf("REACH=%i32d\\n", h5explain_cursor_reachability);']
    out = explain(name, *cmds)
    for line in out.splitlines():
        if line.startswith("REACH="):
            return int(line.split("=")[1])
    raise AssertionError(f"no reachability reported\n{out}")


def test_reachability_of_a_located_superblock():
    assert reachability("latest.h5", "h5super") == REACH_REACHED


def test_unlocated_superblock_is_not_claimed_as_reached():
    # The superblock is not "reached by definition": this file's signature was
    # never located, so the walk never reached one.  Under untrusted-strict the
    # walk also halts, which is the weaker of the two honest answers.
    assert reachability("bad_signature.h5", "h5super") == REACH_INCOMPLETE


def test_forensic_proves_an_unlocated_superblock_was_never_reached():
    # forensic keeps walking past corruption, so the walk completes and the
    # absence becomes provable rather than merely unknown.
    assert reachability("bad_signature.h5", 'profile ("forensic")',
                        "h5super") == REACH_NOT_REACHED


def test_unwalked_kinds_are_still_not_claimed():
    # h5policy accounts for extensible-array secondary and data blocks from the
    # index header rather than walking them, so the record cannot speak to them.
    off = heuristic_false_positive_offset("latest.h5")
    for kind in ("H5EX_KIND_EA_SBLOCK", "H5EX_KIND_EA_DBLOCK"):
        got = reachability("latest.h5", 'gos ("%d")' % off,
                           "h5explain_cur_kind = %s;" % kind)
        assert got == REACH_UNRECORDED, (kind, got)


def test_the_same_address_answers_by_kind():
    # The contrast that shows the kind decides whether silence is informative:
    # one address, walked-kind vs unwalked-kind.
    off = heuristic_false_positive_offset("latest.h5")
    assert reachability("latest.h5", 'gos ("%d")' % off) == REACH_NOT_REACHED
    assert reachability("latest.h5", 'gos ("%d")' % off,
                        "h5explain_cur_kind = H5EX_KIND_EA_SBLOCK;") \
        == REACH_UNRECORDED


def test_unwalked_kind_message_explains_why():
    off = heuristic_false_positive_offset("latest.h5")
    out = explain("latest.h5", 'gos ("%d")' % off,
                  "h5explain_cur_kind = H5EX_KIND_EA_SBLOCK;", "check")
    assert "from its index header rather than walking it" in out, out


def test_kind_mismatch_is_surfaced():
    # h5policy read a superblock at 0; tell the cursor it is something else and
    # the disagreement must be reported -- two structures cannot share bytes.
    out = explain("latest.h5", "h5super",
                  "h5explain_cur_kind = H5EX_KIND_LHEAP;", "check")
    assert "read a SUPER at this address" in out, out
    assert "one of the two readings is wrong" in out, out


def test_no_mismatch_note_when_the_kinds_agree():
    out = explain("latest.h5", "h5super", "check")
    assert "one of the two readings is wrong" not in out, out


def test_check_does_not_claim_not_reached_when_the_walk_stopped_early():
    # Under untrusted-strict the walk halts at the corruption, so an unvisited
    # header proves nothing.  Saying "never reached" here would be a lie.
    out = explain_path(corpus(BAD_BTREE), 'gos ("800")', "check")
    assert "stopped early" in out, out
    assert "never reached it" not in out, out


def test_forensic_profile_resolves_a_halted_walk():
    # The "stopped early" message tells the user to try forensic; that advice
    # has to actually work.
    strict = explain_path(corpus(BAD_BTREE), 'gos ("800")', "check")
    assert "stopped early" in strict, strict
    forensic = explain_path(corpus(BAD_BTREE), 'profile ("forensic")',
                            'gos ("800")', "check")
    assert "The walk reached it." in forensic, forensic


def test_profile_shows_and_sets():
    out = explain("latest.h5", "profile", 'profile ("forensic")', "profile")
    assert out.count("untrusted_strict") >= 1, out
    assert out.count("forensic") >= 2, out


def test_profile_rejects_an_unknown_name():
    out = explain("latest.h5", 'profile ("bogus")', "profile")
    assert 'unknown profile "bogus"' in out, out
    # The bad name must not have taken effect.
    assert "h5policy profile: untrusted_strict" in out, out


def test_check_leaves_navigation_state_untouched():
    # h5policy and h5explain hold separate bindings of the shared format
    # globals; a check must not disturb the context h5explain primed.
    out = explain("earliest.h5", "root", 'cd ("chunked")', "info", "check", "info")
    infos = [l for l in out.splitlines() if "extent=" in l]
    assert len(infos) == 2, out
    assert infos[0] == infos[1], infos


def test_check_preserves_learned_btree_context():
    off = raw_chunk_btree_offset("earliest.h5")
    out = explain("earliest.h5", "root", 'cd ("chunked")', 'gos ("%d")' % off,
                  "info", "check", "info")
    infos = [l for l in out.splitlines() if "extent=" in l]
    assert len(infos) == 2, out
    assert infos[0] == infos[1], infos
    # The learned rank must survive, not fall back to the ndims=1 decode.
    assert "set_bt1_ndims" not in out, out


# -- finding-cap truncation and the offset-0 placeholder ---------------------

# A corpus fixture that yields several findings under forensic, so capping the
# finding limit truncates a real run rather than an artificial one.
MULTI_FINDING = "malformed/bad_compact_layout_overrun.h5"

# Lowering a production ceiling to make a boundary testable is the same tactic
# h5policy's own suite uses for its reduced-boundary cases (tests/README.md);
# the real cap is 4096, which no small fixture can reach.
CAP_ONE = "H5POLICY_MAX_FINDINGS = 1UL;"


def test_check_reports_that_the_finding_limit_was_reached():
    out = explain_path(corpus(MULTI_FINDING), CAP_ONE, 'profile ("forensic")',
                       "h5super", "check")
    assert "finding limit was reached" in out, out


def test_check_does_not_claim_no_findings_once_truncated():
    # Past the cap, "no findings here" is unsupportable: a finding on these
    # bytes may have been dropped rather than never raised.
    out = explain_path(corpus(MULTI_FINDING), CAP_ONE, 'profile ("forensic")',
                       "h5super", "check")
    assert "may have been dropped rather than never raised" in out, out
    assert "No findings at this primitive." not in out, out


def test_untruncated_check_makes_the_plain_claim():
    # The hedge must appear only when it is earned.
    out = explain("latest.h5", "root", "check")
    assert "No findings at this primitive." in out, out
    assert "may have been dropped" not in out, out


def test_placeholder_offset_findings_do_not_anchor_to_the_superblock():
    # The truncation marker has no byte location. Its numeric offset remains 0
    # for report compatibility, but the explicit validity bit prevents it from
    # attaching to a superblock that genuinely begins at byte 0.
    out = explain_path(corpus(MULTI_FINDING), CAP_ONE, 'profile ("forensic")',
                       "h5super", "check")
    assert "H5_POLICY_FINDINGS_TRUNCATED" not in out, out


def test_genuine_offset_zero_finding_still_anchors_by_object():
    # A bad superblock signature genuinely lives at byte 0, so the location bit
    # lets it anchor by extent without treating zero as a sentinel.
    out = explain("bad_signature.h5", "check")
    assert "H5_CORRUPT_BAD_SIGNATURE" in out, out
    assert "bearing on superblock" in out, out


# -- opening a file whose superblock does not decode -------------------------

def test_session_opens_despite_an_undecodable_superblock():
    out = explain("bad_signature.h5", "pwd")
    assert "superblock at 0UL#B (HDF5 superblock)" in out, out
    assert "unhandled" not in out, out


def test_undecodable_superblock_is_reported_not_raised():
    out = explain("bad_signature.h5", "pwd")
    assert "did not decode" in out, out


def test_navigation_still_works_after_a_bad_superblock():
    # The session must remain usable: dump reads bytes regardless of decoding.
    out = explain("bad_signature.h5", "dump")
    assert "unhandled" not in out, out


# -- policy pickles are loaded only when the session may use them ------------

def test_policy_command_in_a_batch_session_loads_the_pickles():
    # Naming a policy command is what pulls them in; the real check answers.
    out = explain("latest.h5", "root", "check")
    assert "h5policy: accept" in out, out
    assert "are not loaded in this session" not in out, out


def test_batch_session_without_policy_commands_says_so_if_asked():
    # --no-policy stands in for the auto-skip: the commands never mention a
    # policy command, so the pickles are absent and check must explain itself
    # rather than surface poke's "undefined variable".
    proc = subprocess.run([H5EXPLAIN, "--no-policy", "-c", "check",
                           fixture("latest.h5")],
                          capture_output=True, text=True, input="")
    combined = proc.stdout + proc.stderr
    assert "are not loaded in this session" in combined, combined
    assert "Rerun with --policy" in combined, combined
    assert "undefined variable" not in combined, combined


def test_no_policy_stubs_cover_every_policy_command():
    for cmd in ("check", "check_all", 'profile ("forensic")'):
        proc = subprocess.run([H5EXPLAIN, "--no-policy", "-c", cmd,
                               fixture("latest.h5")],
                              capture_output=True, text=True, input="")
        combined = proc.stdout + proc.stderr
        assert "are not loaded in this session" in combined, (cmd, combined)
        assert "undefined variable" not in combined, (cmd, combined)


def test_policy_flag_forces_the_pickles_in():
    proc = subprocess.run([H5EXPLAIN, "--policy", "-c", "check",
                           fixture("latest.h5")],
                          capture_output=True, text=True, input="")
    combined = proc.stdout + proc.stderr
    assert "h5policy: accept" in combined, combined


def test_interactive_sessions_always_load_the_policy_pickles():
    # No commands are known up front, so the user may type check at any prompt.
    # The banner advertising the policy commands proves they were loaded.
    proc = subprocess.run([H5EXPLAIN, fixture("latest.h5")],
                          stdin=subprocess.DEVNULL,
                          capture_output=True, text=True)
    assert "Policy:" in proc.stdout, proc.stdout


def test_banner_advertises_policy_commands():
    proc = subprocess.run([H5EXPLAIN, fixture("latest.h5")],
                          stdin=subprocess.DEVNULL, capture_output=True, text=True)
    assert "check" in proc.stdout, proc.stdout
    assert "Policy:" in proc.stdout, proc.stdout


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failures = 0
    for test in tests:
        try:
            test()
        except AssertionError as exc:
            failures += 1
            print("FAIL %s\n  %s" % (test.__name__, exc))
        else:
            print("ok   %s" % test.__name__)
    if failures:
        print("\nh5explain tests FAILED (%d of %d)" % (failures, len(tests)))
        return 1
    print("\nh5explain tests passed (%d)" % len(tests))
    return 0


if __name__ == "__main__":
    sys.exit(main())
