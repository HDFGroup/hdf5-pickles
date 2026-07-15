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
