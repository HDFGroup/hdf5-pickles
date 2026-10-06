# Assert-masked deserializer invariants

**Status: draft, work in progress.** This catalogs GitHub issue #87: places
where a value decoded from untrusted HDF5 file bytes is validated only by
`assert()` — or by ordinary `if (...) HGOTO_ERROR(...)` code wrapped in
`#ifndef NDEBUG` — rather than a real, always-on check. Both mechanisms
disappear identically under `-DNDEBUG`, i.e. in every shipped Release build,
so both count as "assert-masked" here.

Six of the issue's seven named areas are complete (SOHM, Extensible
arrays, V2 B-trees, Free-space managers, Metadata-cache images, Fractal
heaps); the other one (Dataset chunk records) is not yet started. This is a
first pass, not a final document.

## Scope

**In scope:** a check that exists in the source but is defeated by a build
flag (`assert()`, or a `#ifndef NDEBUG` block), validating a value that comes
from untrusted file bytes.

**Out of scope:** asserts on pure internal/programmer state unrelated to file
bytes (caller-supplied pointers, ref-counts, cache-state invariants); sites
where a newer, non-`assert` initialization helper already performs a real,
`NDEBUG`-surviving check; debug-only or test-only code paths not reachable
from an ordinary application opening an untrusted file.

**How findings were verified.** Every finding below claiming a *measured*
consequence was checked by building a real, byte-level fixture — one or two
bytes changed in a valid seed file, its Jenkins-lookup3 checksum resealed —
and then observing both `h5policy`'s verdict and a real libhdf5 build's
actual behavior (timing, memory, and, where useful, the full HDF5 error
stack via a minimal C reproducer). Findings not yet given this treatment are
marked "traced, not yet measured" rather than assumed either way.

**Abbreviations used throughout the tables below:** OOM (out-of-memory), DoS
(denial-of-service), ASan (AddressSanitizer, a compiler instrumentation that
crashes immediately at the point of an invalid memory access rather than
letting the corruption surface later or silently), RSS (resident set size —
a process's actual physical-memory usage), and the POSIX signals SIGSEGV
(invalid memory access), SIGABRT (abnormal-termination request, often from
an internal safety check firing), and SIGBUS (a fatal bus error, e.g. a
misaligned or unmapped access).

## SOHM (`H5SM*.c`, 170 asserts across 5 files — complete)

Every finding below has now been built as a real fixture (one or two bytes
changed in a valid seed, checksum resealed) and measured against both
`h5policy` and a real libhdf5 build — none are "traced only."

| # | Invariant | Root cause | Guard site(s) | Consequence | `h5policy` |
|---|---|---|---|---|---|
| 1 | Table format `version` | `H5Oshmesg.c:87` — raw decode, no check at the decode site itself | `H5SMcache.c:214` | **Measured: inert.** Opens and reads normally — only one version is ever defined and nothing branches on it | Confirmed: dedicated check (`H5_CORRUPT_SOHM_VERSION`, `h5_sohm.pk:635 (version != 0UL)`) |
| 2 | `num_indexes` bounds | `H5Oshmesg.c:95` — raw decode, no check at the decode site itself | `H5SMcache.c:222`, `H5SM.c:1960` | **Measured: clean file-open failure** — an inflated count sizes the expected master-table read past the file's real end-of-allocation (`addr overflow`), no crash, no memory growth | Confirmed: dedicated check (`H5_CORRUPT_SOHM_INDEX_COUNT`, valid range 1-8, `h5_sohm.pk:646 (nindexes > 8UL)`) |
| 3 | Message `location` legality | `H5SMmessage.c:312` — raw decode, no check at the decode site itself; only two legal encoded values exist, and a third is never rejected anywhere in the subsystem either | `H5SMmessage.c:227,320`, `H5SM.c:1178,1310,2196,2371`, `H5SMbtree2.c:181` | **Measured: reads unaffected; a write fails.** An illegal value falls into the wrong branch, reinterpreting an in-heap record's bytes as an in-object-header record — genuine type confusion, caught cleanly by an address-vs-end-of-allocation bound | Confirmed: dedicated check (`H5_CORRUPT_SOHM_LOCATION`, `h5_sohm.pk:69 (storage > 1UL)`) |
| 4 | Index `index_type` legality | `H5SMcache.c:247` — raw decode, no check at the decode site itself | `H5SM.c:571,1322,1462,1810,2181,2700` (each silently treats an illegal 3rd value as `BTREE`) | **Measured: reads unaffected; a write fails.** The illegal value falls into the B-tree branch, which then tries to open a *list* structure's address as a v2 B-tree header — genuine type confusion, caught cleanly by a checksum mismatch | Confirmed: dedicated check (`H5_CORRUPT_SOHM_INDEX_TYPE`, `h5_sohm.pk:707-710 (invalid index type)`) |
| 5 | `list_max`/`btree_min` cross-index consistency | `H5SM.c:1984-1985` — decoded independently per index, no cross-check | `H5SM.c:1984-1985` | **Measured: silent misreporting, no functional break.** Built a genuine 2-index file, patched only one index's values (unreachable via any legitimate API call). `H5Fget_create_plist()` silently reports the *other* index's values — the real list↔B-tree conversion logic is unaffected since it reads each index's own values directly | **None — confirmed coverage gap.** `h5policy` accepts the crafted file outright |
| 6 | `msg_type_id` out-of-bounds array index | `H5SMmessage.c:323` — raw decode, indexes a fixed 27-element array with no bound check before the access | `H5SM.c:2343-2344`, `H5Omessage.c:1091` | **Measured, cross-platform (macOS + Linux, stock and ASan builds): the out-of-bounds read genuinely executes on a real, crafted file, and is silent on every build tested** — not because the access is safe, but because (a) ASan's redzones don't cover "wild" far-out-of-bounds reads on small globals, a general sanitizer limitation, not platform-specific, and (b) the one reachable consumer path uses the resulting garbage value only in a pointer-*equality* comparison, never a dereference | Confirmed: dedicated check (`H5_CORRUPT_SOHM_MESSAGE_TYPES`, `h5_sohm.pk:103-104 (msg_type >= 16UL)`) |

**Also checked, not a vulnerability:** the *within*-index
relationship `num_messages > list_max` (a single index whose message count
already exceeds its own declared capacity) is already properly guarded — a
real, deliberate check in `H5SM__cache_list_verify_chksum`
(`H5SMcache.c:495-496`, `"number of SOHM messages exceeds list size"`), not
masked by anything.

**Note on `h5policy` coverage generally:** five of these six invariants
have a dedicated check, all defined in `h5policy/pickles/h5_sohm.pk` (see
the table for each one's specific code). The sixth, `list_max`/`btree_min`
cross-index divergence (finding #5 above), is a genuine gap: `h5policy`
has no check for it at all and accepts the crafted file outright.

**Recommendation for finding #5 (not implemented here):** unlike the other
five, closing this one needs two separate fixes, not one. On the libhdf5
side, the assert at `H5SM.c:1984-1985` could be promoted to a real,
always-on check that rejects the file at open time when any two indexes'
`list_max`/`btree_min` diverge — safe to do unconditionally, since no
legitimate writer can ever produce a divergent file in the first place. On
the `h5policy` side, that promotion alone would not add coverage: there is
no existing check to strengthen, so closing the gap needs a genuinely new
check in `h5policy/pickles/h5_sohm.pk` for this same cross-index
relationship. Both are deliberately left as recommendations rather than
changes in this PR — worth a maintainer decision on priority and exact
shape before anyone implements them.

## Extensible arrays (`H5EA*.c`, 314 asserts across 11 files — complete)

Two independent, fully-measured severe findings — finding #1 in the table
below (header `nsblks` underflow), and `max_idx_set`, covered separately
under **Adjacent findings** since it isn't literally assert-masked;
everything else across all 11 files reconciles to internal/write-path
checks or an echo of one of these two.

All six `H5EA_create_t` header parameters share one root cause
(`H5EAcache.c:320-328` — raw decode, no check at the decode site itself;
real validation exists only in `H5EA__hdr_create`, `H5EAhdr.c:346-388`,
masked by `#ifndef NDEBUG` and create-path-only in any case), so the table
below lists each field's own measured consequence rather than repeating the
shared root cause for rows 1-5; rows 6-7 are two further candidates found
one level deeper in the call graph, each with its own root-cause site:

| # | Invariant | Root cause | Guard site(s) | Consequence | `h5policy` |
|---|---|---|---|---|---|
| 1 | `max_nelmts_bits` + `data_blk_min_elmts` (→ `hdr->nsblks`) | `H5EAcache.c:320-328` (shared, see above) | `H5EAhdr.c:180-182` (weak, nonzero-only) | **Measured: severe OOM DoS** — 1 byte changed, 55GB+ RAM, OOM-killed after 22s, ordinary dataset read | Confirmed: dedicated geometry check rejects instantly |
| 2 | `max_dblk_page_nelmts_bits` (→ `dblk_page_nelmts` via `1 << max_dblk_page_nelmts_bits`) | same | `H5EAcache.c:1011,1014,1018,1423` (react after the fact) | Measured: data-loss-on-read (checksum mismatch, no crash) | Confirmed, same check |
| 3 | `sup_blk_min_data_ptrs` | same | — | Measured: data-loss-on-read (checksum mismatch); a cross-field variant (`nsblk_addrs`, computed unguarded at `H5EAiblock.c:113-115` — see row 7) caught by a 3rd, distinct incidental mechanism — see below | Confirmed, same check |
| 4 | `raw_elmt_size` | same | — | Measured: data-loss-on-read (checksum mismatch) | Confirmed, same check |
| 5 | `idx_blk_elmts` | same | — | Measured: data-loss-on-read — checksum mismatch at `0`; addr-overflow at a value that actually violates page capacity | Confirmed directly for a violating value |
| 6 | `H5EA__hdr_alloc_elmts`'s `idx` underflow (one level deeper) | `H5EAhdr.c:245` — no check at this computation site | `H5EAhdr.c:316-317` (sibling `free_elmts` asserts on the same `idx`, elsewhere) | Measured: subsumed by #2's condition, not an independent hazard | n/a — same check already catches the precondition |
| 7 | `H5EA__iblock_alloc`'s `nsblk_addrs` underflow (cross-field, one level deeper) | `H5EAiblock.c:113-115` — zero guard | — | Measured: caught by a 3rd incidental mechanism (`H5C__load_entry` generic length-sanity bound), ~18-exabyte wrap, ~3.5MB peak memory, not independent | Confirmed: dedicated check also covers this relationship |

### Finding #1 in depth — header `nsblks` underflow: severe OOM DoS

`H5EA__hdr_init` (`H5EAhdr.c:185`) computes:

```c
hdr->nsblks = 1 + (hdr->cparam.max_nelmts_bits - H5VM_log2_of2(hdr->cparam.data_blk_min_elmts));
```

If `max_nelmts_bits < log2(data_blk_min_elmts)`, this underflows in unsigned
32-bit arithmetic to a value near 2^32, sizing an `H5FL_SEQ_MALLOC` followed
by a loop that writes every slot.

**Measured:** one byte changed in a 2208-byte valid seed file
(`max_nelmts_bits` 32→1). `h5policy --profile untrusted-strict` rejects it
instantly, zero memory (`H5_CORRUPT_EXTENSIBLE_ARRAY_GEOMETRY`, `h5_chunkindex.pk:1456-1463 (max_nelmts_bits > 64UL)`, a
deliberate, comprehensive geometry check covering all six fields and their
cross-relationships). A real build (h5py 3.14.0 / HDF5 1.14.6, arm64 macOS)
opens the file fine, then an *ordinary* `dataset[...]` read causes:

```
maximum resident set size: 5,447,286,784 bytes   (~5.4 GB)
peak memory footprint:    55,473,675,312 bytes   (~55.5 GB)
real time: 22.37s before the process was killed
```

A ~2KB file, one byte changed, no special API calls — just opening a file
and reading a dataset the ordinary way.

**Why #1 alone is severe while #2-#7 are not (the generalized rule, tested
across all seven rows above):** a field's bad value produces a severe
consequence only if its arithmetic stays entirely inside the header's own
already-checksummed structure, as `nsblks` does. Every other row's
corruption instead changes the computed size (or requested read length) of
a *different* metadata block — the index block, in every case tested — and
that block's own independent verification (a checksum, an
address/size-vs-end-of-allocation bound, or the generic cache-load
length-sanity bound behind row #7) catches the mismatch before the bad
arithmetic ever gets a chance to misbehave for real. These are at least
three distinct, independently-confirmed incidental mechanisms, not one, and
none of them is a deliberate defense against this specific bug class —
`h5policy`'s own dedicated geometry check is the only *deliberate* one at
play here.

A separate, non-assert-masked finding (`max_idx_set`) was also found in this
area during the same sweep — see **Adjacent findings**, below.

## V2 B-trees (`H5B2*.c`, 344 asserts across 9 files — complete)

Three findings, all independently measured against a real fixture: two are
genuine `h5policy` coverage gaps (`merge_percent` thrashing; the by-index
descent pin leak), one is a real, bounded hazard that turns out to already
be covered (`node_size`). A fourth, differently-shaped finding —
`node_nrec` feeding a checksum-length computation with no bound against the
real buffer size — is covered separately under **Adjacent findings**,
below, since (like Extensible Arrays' `max_idx_set`) it is not literally
assert-masked: nothing guards it at all, not even an assert. Five of the
nine files (`H5B2internal.c`, `H5B2int.c`, `H5B2dbg.c`, `H5B2test.c`,
`H5B2stat.c`) reconcile entirely to write-path bookkeeping, debug-tool-only,
or test-only code, and contribute nothing.

`node_size` and `merge_percent`/`split_percent` share one root cause:
`H5B2__hdr_init` (`H5B2hdr.c:107-116`) asserts several properties of its
`cparam` argument — this function runs both at B-tree-creation time
(trusted caller) and directly from the deserialize path
(`H5B2cache.c:288`, right after `cparam.node_size`, `cparam.split_percent`
and `cparam.merge_percent` are decoded raw at `H5B2cache.c:261,270-271`
with no check at the decode site itself) — so its argument asserts are
genuine deserializer invariants, not just internal contracts.

| # | Invariant | Root cause | Guard site(s) | Consequence | `h5policy` |
|---|---|---|---|---|---|
| 1 | `node_size` sanity | `H5B2cache.c:261` (shared, see above) | `H5B2hdr.c:112` (`assert(cparam->node_size > 0)`) | **Measured: real, bounded resource spike.** Patched to the field's own on-disk maximum (`0xFFFFFFFF`, a fixed 4-byte field). `H5B2__hdr_init` eagerly `malloc`s and `memset`s a `node_size`-sized scratch buffer *before any node is ever read* — ~898MB peak RSS, ~1.1s delay opening a 15KB file, no crash. Caught afterward, incidentally, by an unrelated addr-vs-end-of-allocation check when the same corrupted value is later used as a leaf's read length | Confirmed: dedicated check (`H5_CORRUPT_V2_BTREE_NODE_SIZE`, `h5_btree2.pk:72 (node_size > file_size)`) — not a gap |
| 2 | `merge_percent < split_percent / 2` | `H5B2cache.c:270-271` (shared, see above) | `H5B2hdr.c:116` | **Measured: real tree-shape pathology, write-path only.** Violating the safety margin (`merge_percent=50` against `split_percent=100`) made both children of a fresh split land exactly on the corrupted merge threshold; the very next ordinary delete triggered a premature merge, collapsing a two-child, 46-record split straight back into one 45-record leaf. Every record stayed correctly tracked throughout — no data loss, no wrong content — just needless, repeated split-then-remerge churn on ordinary write traffic near the threshold | **None — confirmed coverage gap.** No pickle validates the header's own `split_percent`/`merge_percent` bytes at all (a same-named pair of fields elsewhere, in an unrelated message type, is checked, but not these) |
| 3 | Internal node's per-child `all_nrec` consistency (by-index descent) | `H5B2cache.c:672-678` — `node_ptrs[].all_nrec` decoded raw, no check at the decode site itself | `H5B2.c:826` (`assert(0 && "Index off end of tree??")`) — the only thing standing between a corrupted per-child count and a broken descent | **Measured: metadata-cache resource leak, not a crash.** The internal node's `H5AC_unprotect` call is only reached in the sibling branch, so a masked failure here leaves it permanently protected; the stale, un-advanced node pointer gets reprocessed at the wrong depth, eventually failing a checksum check against what should be a leaf. On `H5Fclose`, the leaked pin makes `H5C__flush_invalidate_ring` report `"Pinned entry count not decreasing"`, followed by the library's own `"infinite loop closing library"` diagnostic — a real, malformed-shutdown malfunction, not a true hang | **None — confirmed coverage gap.** Accepts the crafted file outright |

**Recommendation for finding 2, `merge_percent` (not implemented here):**
the same two-fix shape as SOHM's finding #5. On the libhdf5 side, the three
asserts on `cparam->split_percent`/`cparam->merge_percent`
(`H5B2hdr.c:114-116`) could be promoted to a real, always-on check at
header-deserialize time — safe to do unconditionally, since no legitimate
writer can ever produce a file violating these relationships (every real
client class hardcodes valid percentages at creation time). On the
`h5policy` side, that promotion alone adds nothing: there is no existing
check on the header's own `split_percent`/`merge_percent` bytes to
strengthen, so closing the gap needs a genuinely new check in
`h5policy/pickles/h5_btree2.pk` for these two fields and their
cross-relationship. Both left as recommendations, not changes, in this PR.

**Recommendation for finding 3, the index-off-end pin leak (not
implemented here):** on the libhdf5 side, the assert at `H5B2.c:826` could
become a real, always-on error — but the fix isn't just swapping `assert`
for `HGOTO_ERROR`: the branch would also need to release the
currently-protected internal node before returning, exactly as its sibling
branch already does, or the resource leak persists even with a clean error
path. On the `h5policy` side, `h5_btree2.pk` already has a related check
(`H5_CORRUPT_V2_BTREE_SUBTREE_COUNT`, `h5_btree2.pk:433 (child_total < child_nrec)`) — but it only catches a *local*
inconsistency, one child pointer's `all_nrec` being less than its own
`node_nrec` (confirmed by reading the check itself: `child_total <
child_nrec`, which our fixture's corruption — `all_nrec` reduced to 100
against a `node_nrec` of 12 — never triggers, since 100 is still greater
than 12). It does not check the *cross-sibling* sum this bug actually
depends on: whether a node's `node_ptrs[]` entries, taken together, sum to
what the level above expects. Closing this gap needs extending that
existing validation to the cross-sibling sum, not writing one from scratch.
Left as a recommendation, not a change, in this PR.

**Also checked, not a vulnerability:** `H5B2hdr.c:165`
(`assert(hdr->max_nrec_size <= H5B2_SIZEOF_RECORDS_PER_NODE)`) looked like a
candidate for the same shape of bug as row 3 — a silently-truncated width
misaligning every subsequent record decode — but tracing where
`max_nrec_size` is actually consumed shows the downcast that follows it
(`uint8_t`, range 0-255) has far more headroom than any real `node_size`
could ever need (at most 8 bytes, since `hsize_t` is 64-bit), and the value
is computed and used consistently on both the write and read side wherever
it appears. Skipping this assert most likely just lets an unusually large
node use a wider, still-correct encoding instead of tripping a
"bigger-than-expected" sanity check — reasoned through, not independently
fixture-tested, but not pursued further as a result.

**Also checked, and likewise not pursued:** `H5B2hdr.c:172`
(`assert(hdr->node_info[u].max_nrec <= hdr->node_info[u - 1].max_nrec)`),
checking that a deeper level's internal-node capacity never exceeds a
shallower level's. This one is closer to a proof than a search. A level's
capacity, `H5B2_NUM_INT_REC(h, d)` (`H5B2pkg.h:109-111`), is `node_size`
divided by a per-slot cost that includes `node_info[d-1].cum_max_nrec_size`
— the byte-width needed to encode the *cumulative* record count one level
down. That cumulative count is defined recursively,
`cum_max_nrec[d] = (max_nrec[d] + 1) * cum_max_nrec[d-1] + max_nrec[d]`,
which can only equal or exceed the level below it, never fall short — so
the byte-width needed to encode it, the per-slot cost, and therefore
capacity itself (a fixed `node_size` divided by a non-decreasing cost) are
all forced to move monotonically the right way, for any legal
`node_size`/`rrec_size`. Checked directly against the real numbers measured
on `dense_links_deep.h5` earlier in this document (`45`/`24`/`22` across
depths 0-2): the formula reproduces those exactly. What wasn't chased:
unlike the `max_nrec_size` item above, this conclusion rests on the
*triggering condition* being unreachable, not on tracing what would happen
downstream if it somehow were — a different, and here untested, kind of
"safe."

**Related, still-live hazard in this area — not this session's discovery,
partially re-verified where noted.** `H5G__obj_get_linfo` sizes a group's
in-memory link table directly from the v2 B-tree header's own declared
`total_nrec` (`hdr->root.all_nrec`, via `H5B2_get_nrec()`, no validation),
then `H5G__dense_build_table` fills that table by walking the tree for
real — a completely independent count. The two are supposed to always
agree, and only one direction of their disagreeing is actually guarded:

- **`total_nrec` understated** (declares `n-1`, tree really holds `n`): the
  table is allocated one slot short. `H5G__dense_build_table_cb`'s array
  write — `ltable->lnks[udata->curr_lnk]` — would run one slot past the
  allocation on the tree's last real record. The *only* thing standing in
  the way is `assert(udata->curr_lnk < udata->ltable->nlinks)`
  (`H5Gdense.c:716`) — masked under `-DNDEBUG`, at which point the
  out-of-bounds write happens for real, later surfacing as a `SIGABRT`
  (glibc's heap-corruption detector, on some later allocation).
- **`total_nrec` overstated** (`n+1` instead of `n`): the table gets one
  extra slot the walk never reaches, left at its zero-initialized `NULL`
  name. This direction has **no guard at all, not even this assert** — the
  crash happens later and elsewhere, when the table's own sort comparator
  (`H5G__link_cmp_name_inc`) dereferences that `NULL`, causing `SIGSEGV`.

Two of the three claims above are independently confirmed this session by
direct inspection; one is cited from prior work, not reproduced:

- **Confirmed by direct source read:** the guard is still exactly
  `assert(udata->curr_lnk < udata->ltable->nlinks)` at this exact commit
  (`4ee8adc29cd`) — the same one this whole catalog is measured against.
  Not fixed in libhdf5 itself, in either direction.
- **Confirmed by a live re-test:** `h5policy`, as it stands in the tree
  today, rejects a `total_nrec` off by `+1`, `-1`, or set to `0` — all three
  tested directly this session.
- **Not reproduced this session** — cited from
  `registry/cases/v2-btree-total-nrec-unchecked-in-name-walker.yml`: the
  actual crash behavior against a real, running libhdf5 build (the
  `SIGSEGV`/`SIGABRT` pair described above). That measurement predates this
  session; see the case file for its full history.

Net: a real, currently-live hazard in this exact area, on this exact
commit — closed on the `h5policy` side, still open in libhdf5 itself.

**Not chased further this session:** a companion assert on the same
by-index descent path, `H5B2.c:848` (`assert(idx < leaf->nrec)`, with a
write-side twin at `H5B2leaf.c:866`) — the final bound check once descent
reaches a leaf, rather than the internal-node "off end" check in row 3
above. Reaching it (rather than row 3's failure mode) would need a more
surgical corruption that stays checksum-valid at every level while still
landing a leaf with a too-large `idx` — real effort for what traces to a
likely lower ceiling (an in-bounds but garbage native-record read, not an
out-of-bounds one) than row 3's confirmed resource leak. Identified, not
fixture-tested.

## Free-space managers (`H5FS*.c`, 348 asserts across 7 files — complete)

Four findings, all independently measured against a real fixture: two are
genuine `h5policy` coverage gaps (`tot_sect_count`, understated direction;
`tot_space`), two are real, severe hazards that turn out to already be
covered — `node_count` (newly discovered this session) and `sect_size`
(pre-existing, discovered in a prior session). A fifth, differently-shaped
finding — `max_sect_addr` driving an unbounded per-section address width — is
covered separately under **Adjacent findings**, below, since (like
Extensible Arrays' `max_idx_set` and V2 B-trees' `node_nrec`) it is not
literally assert-masked: nothing guards it at all, not even an assert. Five
of the seven files (`H5FS.c`, `H5FSdbg.c`, `H5FSint.c`, `H5FStest.c`,
`H5FSstat.c`) reconcile entirely to lifecycle/API-contract bookkeeping,
debug-tool-only, or test-only code, and contribute nothing; the two that do
are `H5FScache.c` (the deserialize callbacks) and `H5FSsection.c` (the
in-memory section-info machinery `H5FS__sinfo_new` derives its per-section
address width from).

`tot_sect_count`, `serial_sect_count`, `ghost_sect_count`, and `tot_space`
are decoded together, with no validation at the decode site, in
`H5FS__cache_hdr_deserialize` (`H5FScache.c:258-265`).
`H5FS__cache_sinfo_deserialize` (`H5FScache.c:967-1051`) rebuilds all four by
walking the real section list, then only *checks* the header's original
claim against five back-to-back asserts (`H5FScache.c:1045-1050`) — every
one of which vanishes under `-DNDEBUG`.

| # | Invariant | Root cause | Guard site(s) | Consequence | `h5policy` |
|---|---|---|---|---|---|
| 1 | `tot_sect_count`/`serial_sect_count` vs. the real section-list walk | `H5FScache.c:258-265` (shared, see above) | `H5FScache.c:1045-1046` (`assert(old_tot_sect_count == fspace->tot_sect_count)`, `assert(old_serial_sect_count == ...)`) | **Measured, bidirectional.** Understated (3→2): the walk's own early-exit (`if (fspace->tot_sect_count == old_tot_sect_count) break;`) stops one real section short — a genuine, legitimately-free 4800-byte region silently vanishes from `h5stat -s`'s report, no crash, no error. Overstated (3→10): `h5policy` already catches this direction (see next column), but if it didn't, the same corrupted value would reach real applications first — `H5Fget_free_sections()`'s returned count (from `H5FS_sect_stats`, a bare accessor read *before* the correcting walk) decouples from how many entries it actually fills, observed as 7 zero-valued phantom sections via `h5stat -s`'s `calloc`-based buffer (a `malloc`-based caller would see stale heap contents instead) | **Understated: confirmed gap, accepts outright.** Overstated: **not a gap** — `h5policy_walk_fspace_sections` (`h5_messages.pk:1154 (while seen < serial_sect)`) also drives its own walk length from the header's declared count, but a *higher* declared count than the list actually holds runs the loop past the real records and trips `H5_CORRUPT_FSM_SECTION_OVERRUN` before it can finish — asymmetric coverage, not by design |
| 2 | `tot_space` vs. the real section-list walk | `H5FScache.c:255-256` (`H5F_DECODE_LENGTH`, no check) | `H5FScache.c:1050` (`assert(old_tot_space == fspace->tot_space)`) | **Measured: unconditional, un-self-correcting silent misreporting.** `H5MF_get_freespace()` → `H5FS_sect_stats(fs_man, &tot_space, NULL)` never requests the section list at all, so there is no path — self-correcting or otherwise — back to the true value. A single corrupted header field (12480 → 99999999) made `h5stat`'s summary report 100002348 bytes free, 301066.8% of the file's own size, with zero error or warning | **Confirmed gap.** `h5policy_walk_fspace_manager` (`h5_messages.pk:1241-1360 (h5policy_walk_fspace_manager)`) never even decodes `tot_space` — no variable, no check exists to strengthen |
| 3 | `node_count` (sections-per-size-group counter) | `H5FScache.c:995` (`UINT64DECODE_VAR`, no check) | `H5FScache.c:996` (`assert(node_count)`) — nonzero only, no upper bound | **Measured: CPU-exhaustion DoS.** One byte, 1→200, turned an instant `h5stat -s` into a 2:54+ CPU-pinned hang (99%+ CPU, flat ~3.8MB RSS) before being killed, with no sign of completing | **Not a gap.** `h5policy_walk_fspace_sections` (`h5_messages.pk:1168-1175 (node_count > serial_sect - seen)`) already bounds it relationally against the remaining declared count |
| 4 | `sect_size` (a section's own serialized size) | `H5FScache.c:998-1000` (`UINT64DECODE_VAR`, no check) | `H5FScache.c:1000` (`assert(sect_size)`) — nonzero only | Pre-existing, not newly discovered this session — see `registry/cases/fsm-section-bin-range.yml`. Re-verified this session: the consumer-side hazard (`H5FS__sinfo_new`'s `sinfo->nbins = H5VM_log2_gen(fspace->max_sect_size)` sizing an array later indexed by `H5VM_log2_gen(sect->size)` with no bound, `H5FSsection.c:764,934`) is unchanged at this commit | **Not a gap.** `h5policy_walk_fspace_sections` (`h5_messages.pk:1185-1188 (H5_CORRUPT_FSM_SECTION_SIZE_OVER_MAX)`) has a dedicated relational check, `H5_CORRUPT_FSM_SECTION_SIZE_OVER_MAX` |

**Recommendation for finding 1, `tot_sect_count` understated (not
implemented here):** `h5policy_walk_fspace_sections`
(`h5_messages.pk:1090-1235 (h5policy_walk_fspace_sections)`) drives its own walk length from the header's
declared `serial_sect` the same way libhdf5 does, and never checks
afterward that the walk actually reached the section list's checksum
boundary (`limit`, computed at line 1152). Closing the gap needs one added
check after the `while (seen < serial_sect)` loop: if `cur != limit`, the
section list contains more real, well-formed section records than the
header declared, and should be rejected the same way an *overstated* count
already is. This alone would also make the overstated/understated coverage
symmetric.

**Recommendation for finding 2, `tot_space` (not implemented here):** needs
a new check in `h5policy_walk_fspace_manager`/`h5policy_walk_fspace_sections`
(`h5_messages.pk`): decode the header's `tot_space` field (at
`hdr_addr#B + 6#B`, currently never extracted) and compare it against the
sum of each real section's `sect_size` accumulated during the walk,
rejecting a mismatch the same way libhdf5's own (masked) assert intends to,
but as a real, always-on check.

**Also checked, confirmed inert:** `ghost_sect_count`, the fourth field in
the same header cluster, decoded with equally zero validation. Patched 0→5
(leaving `tot_sect_count`/`serial_sect_count` and the real section list
untouched): `h5policy` rejects it via a different, already-existing
cross-field check (`H5_CORRUPT_FSM_SECTION_COUNT`,
`h5_messages.pk:1298 (serial_sect + ghost_sect != tot_sect)`, tripped even without touching the
other two fields), and the real build's `h5stat` output (default and `-s`)
was byte-for-byte identical to the valid seed's. Unlike its three siblings,
`ghost_sect_count` drives no loop-control condition and backs no
public-facing accessor — genuinely inert, not a finding.

## Metadata-cache images (`H5AC*.c`, `H5Cimage.c`, `H5Ocache_image.c`, 532 asserts across 6 files — complete)

Zero assert-masked findings in this area — a first for this catalog.
`H5AC.c` (116 asserts) is pure lifecycle/wrapper code around the generic
cache layer, with real, always-on checks (not asserts) guarding the one
application-supplied config struct it validates. `H5ACdbg.c` (16 asserts)
is debug-tool-only, most of its functions gated by `#ifndef NDEBUG` and not
even compiled into a release build. `H5ACmpio.c` (134 asserts) is entirely
wrapped in a single `#ifdef H5_HAVE_PARALLEL` from its first line to its
last — the whole file compiles to nothing outside an MPI-parallel build,
unreachable from an ordinary single-process open of an untrusted file.
`H5ACproxy_entry.c` (28 asserts) defines a pure in-memory placeholder
object — its own class registration sets `deserialize`/`verify_chksum`/
`get_initial_load_size` all to `NULL`, since it never touches disk.
`H5Ocache_image.c` (15 asserts) is the actual decode site for the cache
image's `addr`/`size` fields (reached from `H5Fsuper.c`; added to this
area's scope mid-sweep since it isn't named `H5AC*`) — its real
hazard-relevant checks turned out to be genuine, always-on `HGOTO_ERROR`s
(overflow and EOA-range checks), not masked asserts.

`H5Cimage.c` (223 asserts) holds the one real result from this area — but
it isn't assert-masked either, so it's written up under **Adjacent
findings**, below, rather than tabulated here: a deliberate design choice,
stated in the source's own comments, to skip checksum verification
entirely for metadata delivered via a cache image.

**Scope notes:** `H5Ocache_image.c` and the prefetched-entry-specific
portions of `H5Centry.c` (the consumer of the Adjacent finding below) were
added to this area's scope mid-sweep — both are genuinely part of the
cache-image feature's implementation, just not named `H5AC*`.
`H5Centry.c` in full (4,239 lines, mostly generic entry-lifecycle code
shared by every cache client in the library) was not swept — only its two
prefetched-entry-specific functions were read, the same exclusion applied
to `H5C.c` in every prior area.

## Fractal heaps (`H5HF*.c`, 919 asserts across 16 files — complete)

Five findings, all independently measured against real fixtures: two are
literally assert-masked and appear in the table below. The other three are
zero-guard — nothing checks them at all, not even an assert — and are
covered separately under **Adjacent findings**, below: an unbounded
row-lookup (`H5HF__dtable_lookup`), a write-only-reachable sibling in the
same shape (`H5HF__man_iter_start_offset`), and a position-dependent
heap-buffer-overflow in how "tiny" objects are stored inline in their own
heap ID. Of those three, only the latter two are actual `h5policy` gaps —
the row-lookup one turned out, on tracing it, to already be caught by
`h5policy`'s own independent reimplementation of the same row/column
arithmetic (see its entry below). Two further candidates were chased and
ruled out — see below, after the table. Ten of the sixteen files (`H5HFhdr.c`, `H5HFiblock.c`,
`H5HFman.c`, `H5HFdblock.c`, `H5HFspace.c`, `H5HFbtree2.c`, `H5HF.c`,
`H5HFdbg.c`, `H5HFtest.c`, `H5HFstat.c`) reconcile entirely to write-path
lifecycle management, the same generic ID-flags dispatch mechanism the
findings below already cover, debug-tool-only, or test-only code, and
contribute nothing new.

| # | Invariant | Root cause | Guard site(s) | Consequence | `h5policy` |
|---|---|---|---|---|---|
| 1 | A free-space section's class actually has a `deserialize` callback before it's called | `H5FScache.c:1013` — a section's on-disk type byte decoded raw; the real check that follows (`:1019-1020`) only confirms the value is *in-bounds*, not that the resulting class has a callback | `H5FScache.c:1024` (`assert(fspace->sect_cls[sect_type].deserialize)`) | **Measured: real crash, isolated to a single byte.** Fractal heap's `INDIRECT` free-space-section class is a valid, in-bounds registered class (index 3) whose `.deserialize` is `NULL` by design — its own comment states objects of this class "should never be in section manager." Nothing stops a corrupted file's section-type byte from claiming to be 3 anyway. One byte flipped (an existing section's type, `0→3`) on an otherwise-untouched real file: stock build `SIGSEGV`; the reused ASan build confirms a direct call through address 0 (pinned down without a debugger — attach is blocked at the OS level in this environment — by computing the address offset between the built binary and the running process from known symbols, then applying that offset to the crash's return-address register). Reachable via an ordinary write to the group (e.g. `H5Gcreate2`/`H5Lcreate` adding a link), when the heap's free-space manager is consulted for space and loads the on-disk section list — *not* via read/iterate (a read-only `H5Literate2`/`Group.keys()` over the same corrupted file completes cleanly, and `h5stat -s` never loads these sections; this corrects an earlier "reachable via read" phrasing). The sibling `NORMAL_ROW` class (index 2) has an equally `NULL` `.deserialize` slot, and the shared dispatch gives it no guard beyond the same in-bounds check, so a type byte of `2` reaches the identical masked `assert`. **Confirmed empirically (2026-10-06):** a one-byte fixture (an existing `SINGLE` section's type `0→2`, section-list checksum resealed) makes an asserts-live build abort at exactly `H5FScache.c:1024` (`H5FS__cache_sinfo_deserialize`, `Assertion 'fspace->sect_cls[sect_type].deserialize' failed`) on a link insert, while the same insert on the untouched seed exits 0; the type-`3` SIGSEGV above is the release-mode (`-DNDEBUG`) face of that same line, which type `2` reaches identically | **Confirmed gap.** The minimal, single-byte fixture is accepted with zero findings. Earlier rejections seen on more elaborate byte-surgery fixtures were confirmed *incidental* — an unrelated construction artifact, not real coverage — via a controlled isolation test (the identical recipe with a non-zero, still-nonsensical payload crashed identically) |
| 2 | An indirect free-space section's `nentries` must be positive before it drives a span-size computation | `H5HFsection.c:3730-3731` — `nentries` decoded raw via `UINT16DECODE`, zero validation at the decode site, not even an assert | `H5HFdtable.c:278` (`assert(num_entries > 0)`, inside `H5HF__dtable_span_size`) | **Measured: real heap-buffer-overflow.** `nentries=0` underflows `end_entry = (start_entry+nentries)-1` (unsigned) to `0xFFFFFFFF`; `H5HF__dtable_span_size`'s row-accumulation loop then reads `row_block_size[row]` far past the real, `max_root_rows`-sized array. ASan: `heap-buffer-overflow READ of size 8, 0 bytes after a 176-byte region`, `H5HFdtable.c:303`. Reachable via an ordinary write (`H5Dcreate2` adding a link) — but only when the corrupted section is typed `FIRST_ROW`; the identical payload under type `INDIRECT` hits finding 1's null-callback crash first, before this arithmetic is ever reached | **Confirmed gap.** Verified with a controlled A/B test: the identical construction recipe with a valid, non-underflowing `nentries=4` is rejected *identically* — proving the rejection has nothing to do with `nentries` itself |

**Recommendation for finding 1, the null-deserialize-callback dispatch (not
implemented here):** on the libhdf5 side, the assert at `H5FScache.c:1024`
could be promoted to a real, always-on check that rejects the file rather
than calling through a `NULL` callback — safe unconditionally, since no
legitimate writer ever serializes an `INDIRECT`-class section into a
section list in the first place. On the `h5policy` side, the section-record
loop in `h5policy_walk_frhp_fspace_sections`
(`h5policy/pickles/h5_frhp_fspace.pk:137-160 (no further payload)`) currently treats the
per-record `sect_type` byte as opaque and skips over it (`cur = cur + 1UL`,
line 152) on the strength of a comment claiming "H5HF's section classes
carry no further payload" — a claim that finding 2's own root cause (below)
already shows is false for at least two of the four classes. Closing this
gap needs decoding `sect_type` explicitly there and rejecting a value of 2
(`NORMAL_ROW`) or 3 (`INDIRECT`) outright, mirroring what real libhdf5's own
class table already knows: both classes' `deserialize` is intentionally
unreachable.

**Recommendation for finding 2, the `nentries=0` underflow (not implemented
here):** on the libhdf5 side, `H5HF__sect_indirect_deserialize`
(`H5HFsection.c:3731`, immediately after `UINT16DECODE(buf, nentries)`) is
the single site both `FIRST_ROW` and `INDIRECT` converge through —
`H5HF__sect_row_deserialize` (`H5HFsection.c:1604-1608`) is a pure forward
to the same function — so a `nentries == 0` check placed there, before
`end_entry` is ever computed, would close both variants with one fix,
rather than only patching the `assert(num_entries > 0)` deeper inside
`H5HF__dtable_span_size` (`H5HFdtable.c:278`). On the `h5policy` side, this
is the same blind spot as finding 1: the section-record loop
(`h5_frhp_fspace.pk:137-160 (no further payload)`) never decodes `iblock_off`/`start_row`/
`start_col`/`nentries` for `FIRST_ROW`/`NORMAL_ROW`/`INDIRECT`-typed
records at all (confirmed against `H5HFsection.c:3722-3731`, the actual
on-disk layout those classes serialize), so there is no existing check to
strengthen — closing the gap needs decoding those four fields when
`sect_type` warrants it and rejecting `nentries == 0` explicitly, the same
way the list-level `node_count == 0` case is already rejected one level up
(line 125). Both recommendations left undone in this PR.

**Also checked, ruled out — not independently exploitable.** Two further
candidates share the same root shape (a fractal-heap-header field decoded
raw with zero validation, feeding an unbounded computation) but neither
survived direct measurement:

- **`curr_root_rows`**, feeding an iblock read-size/malloc-size computation
  guarded only by `assert(nrows > 0)`. A real fixture (inflated 8→60,000)
  is rejected outright by `h5policy` (`H5_CORRUPT_LENGTH_OVERFLOW`, `h5_dense_links.pk:849-851 (fractal heap indirect block)`) — not a
  gap — and, measured directly at the libhdf5-C-API level (not just via
  h5py, where a SIGABRT reproduces but is a binding-layer issue out of this
  catalog's scope), a completely separate, generic, always-on check
  (`H5FD_read`'s address-vs-EOA bound) catches the resulting oversized read
  before any unsafe access occurs, in both a stock and an ASan build.
- **`id_len`**, mismatched against the fixed 7-byte ID buffer every real
  caller (`H5G_DENSE_FHEAP_ID_LEN`) allocates, driving an overread in
  `H5HF__huge_op_real`/`H5HF__huge_get_obj_len`/`_off`. Confirmed the
  overread is real (garbage values are genuinely produced), but on two
  separate attempts the garbage was caught by two different, generic,
  unrelated safety nets before any memory-safety violation occurred: an
  oversized `malloc` request (ASan: `allocation-size-too-big`, not a
  heap-buffer-overflow) on one attempt, and `H5FD_read`'s address-vs-EOA
  check (the same one that rules out `curr_root_rows`) on a second,
  deliberately-targeted attempt.

## Adjacent findings (not literally assert-masked, same danger shape)

### Extensible arrays — `max_idx_set` — unbounded loop, reachable via a public API, zero `h5policy` coverage

`hdr->stats.stored.max_idx_set` ("highest element index stored, +1") is one
of six *array-statistics* fields in the extensible-array header (a
different family from the six create-time `cparam` fields above) — decoded
raw at `H5EAcache.c:336` with zero validation. Unlike the findings above,
there is no assert or `#ifndef NDEBUG` block guarding it anywhere; it was
simply never checked, on any path, in any build configuration. It directly
bounds a loop with no upper sanity check:

```c
/* H5EA.c:985, H5EA_iterate() */
for (u = 0; u < ea->hdr->stats.stored.max_idx_set && ret_value == H5_ITER_CONT; u++) {
    H5EA_get(ea, u, elmt);
    (*op)(u, elmt, udata);
}
```

This is reachable via an ordinary, documented **public API** —
`H5Dchunk_iter()`, the chunk-introspection call used by h5repack and any
application enumerating a dataset's chunks — backed by
`H5D__earray_idx_iterate` (`H5Dearray.c:1370`), guarded only by
`max_idx_set > 0`.

**Measured:** one 8-byte field changed in a 300-chunk fixture, checksum
resealed. With `max_idx_set = 50,000,000` (bounded, for a clean
measurement), a minimal C reproducer calling `H5Dchunk_iter`:

```
count=300 (all real chunks correctly reported)
1.22s real, ~41 million iterations/second
peak memory footprint: ~5.8MB (flat -- no growth)
```

Pure CPU-time cost, linear in the field's value. Since it's a full 64-bit
field with no ceiling, this scales to an arbitrarily long hang — confirmed
directly with `max_idx_set = 2^35` (~3.4×10^10), which left the same
reproducer pinned at 100% CPU / ~4MB RSS for 1:45 with zero completion
before being stopped. No crash, no memory blowup — the cost is purely the
raw iteration count, since each out-of-range lookup bails out cheaply via an
address-undefined check.

**`h5policy` coverage: none.** `h5policy --profile untrusted-strict`
returns `"decision": "accept", "findings": []` outright on the crafted
file. Unlike every one of the six `cparam` fields above — which `h5policy`
already covers via its own deliberate geometry check — this is a genuine,
currently-undetected gap in this repo's own tooling, not just a masked
libhdf5 check. Traced the other five array-statistics fields
(`nsuper_blks`, `super_blk_size`, `ndata_blks`, `data_blk_size`, `nelmts`)
for comparable hazards: all five are equally unvalidated, but only reached
via write-path increments, debug-dump printing, or one plain addition
reported as a storage-size number — none feeds a loop bound, allocation
size, or array index, so none appears to share this specific hazard.

**Recommendation (not implemented here):** a follow-up `h5policy` check —
something like rejecting a `max_idx_set` that is wildly disproportionate to
what the array's own geometry (`max_nelmts_bits`, `data_blk_min_elmts`,
etc.) could plausibly have populated. This would be a new check in
`h5policy/pickles/h5_chunkindex.pk`, touching tracked repository files, and
is deliberately left as a recommendation rather than a change in this PR —
worth a maintainer decision on priority and exact shape before anyone
implements it.

**Not chased further this session:** whether a single very large targeted
index (rather than iterating up to it) can push `H5EA__dblock_sblk_idx`'s
`sblk_idx` (grows as `log2(idx)`) past `hdr->nsblks`, causing an actual
out-of-bounds heap *read* into `hdr->sblk_info[]` — a structurally
different, and potentially more serious, class of bug than the
CPU-exhaustion DoS above (a memory-safety issue rather than resource
exhaustion), *if* reachable. A bounded iteration test never reached that
threshold; a follow-up attempt via `H5Dget_chunk_info_by_coord()` to query
one index directly itself stalled unexpectedly for 30s+, likely a
different mechanism, not pursued further.

### V2 B-trees — `node_nrec` — checksum-length computation with no bound against the real buffer, already caught by `h5policy`

A node's own record count, `node_nrec`, is decoded raw with no validation
at all — at the header level (`H5B2cache.c:275`, the root's own count) and
at the internal-node level (`H5B2cache.c:672-673`, each child pointer's own
count). Unlike the findings in the V2 B-trees table above, there is no
assert anywhere in this path; it is simply unchecked, on any path, in any
build configuration. That count then sizes the **checksum computation**
that gates loading the *next* node down — not the actual allocated buffer:

```c
/* H5B2cache.c:970 (leaf) / :569-570 (internal) */
chk_size = H5B2_LEAF_PREFIX_SIZE + (udata->nrec * udata->hdr->rrec_size);
H5F_get_checksums(image, chk_size, &stored_chksum, &computed_chksum);
```

`image` is a buffer of exactly `hdr->node_size` bytes — fixed, and
unrelated to `nrec`, since `get_initial_load_size` always returns
`node_size` regardless of what `nrec` claims. `H5F_get_checksums`
(`H5Fio.c:511-539`) trusts `chk_size` completely and reads that many bytes
from the buffer with no bound of its own.

**Measured:** patched a single node's own `node_nrec` field (`0xFFFF`) in
two real fixtures — one where the root is directly a leaf, one where it's
an internal node — reseal the node's own header checksum, nothing else
touched. `h5policy --profile untrusted-strict` rejects both outright, with
a *dedicated* check (`H5_CORRUPT_V2_BTREE_NODE_SIZE`, "used node bytes
exceed its declared node size"; leaf: `h5_dense_links.pk:1412 (leaf_need > node_size)`, internal: `h5_dense_links.pk:2023 (node_need > node_size)`) — so the field itself is not an `h5policy`
gap. Reachable via ordinary group/link iteration
(`H5Literate2`/`h5py`'s `Group.keys()`). Real consequence:

- **Stock build** (no sanitizers): fails cleanly with `H5C__load_entry():
  incorrect metadata checksum after all read attempts` — consistent with,
  not proof against, an out-of-bounds read that happened to land on other
  valid heap memory this run.
- **Fresh ASan build** (`-fsanitize=address`, built specifically to settle
  this): **crashes**, both variants, at the exact predicted line:
  ```
  AddressSanitizer:DEADLYSIGNAL
  ERROR: AddressSanitizer: BUS on unknown address, caused by a READ
    #0 H5F_get_checksums              H5Fio.c:534
    #1 H5B2__cache_leaf_verify_chksum  H5B2cache.c:973   (or _int_verify_chksum, H5B2cache.c:573)
  ```
  A genuine out-of-bounds heap read — ~721KB requested against a ~512-byte
  real allocation — hard enough to hit an unmapped page rather than merely
  tripping a heap-buffer-overflow report. The unmodified seed, run through
  the identical reproducer, completes cleanly every time.

**Why this sits here and not in the main table:** `h5policy` already
independently rejects the corruption via a real, dedicated check on
`node_size`-vs-used-bytes — the *field* is fully covered. What's
uncatalogued is the *mechanism*: libhdf5's own checksum-verification step
is the thing that performs the unsafe read, with nothing — not even an
assert — standing between the raw `node_nrec` value and the read length it
drives. Same shape as `max_idx_set` above: a real, severe, currently-live
hazard in libhdf5 that a from-scratch reimplementation happens to defend
against, not a masked check that could be un-masked to fix it.

### Free-space managers — `max_sect_addr` — unbounded per-section address width, already caught by `h5policy`

`fspace->max_sect_addr` — "size of the address space free-space sections are
within (log2 of actual value)" — is decoded raw at `H5FScache.c:282`
(`UINT16DECODE`) with zero validation, not even an assert. `H5FS__sinfo_new`
(`H5FSsection.c:131`) uses it directly to compute the byte-width for *every*
section's address field for the life of the structure:

```c
sinfo->sect_off_size = (fspace->max_sect_addr + 7) / 8;
```

`H5FS__cache_sinfo_deserialize` (`H5FScache.c:1010`) then decodes each
section's address with `UINT64DECODE_VAR(image, sect_addr,
sinfo->sect_off_size)` — `DECODE_VAR` (`H5encode.h:192-201`) reads exactly
that many bytes with no cap of any kind:

```c
#define DECODE_VAR(p, n, l) \
    do { size_t _i; n = 0; (p) += l; \
         for (_i = 0; _i < l; _i++) n = (n << 8) | *(--p); \
         (p) += l; } while (0)
```

Since `max_sect_addr` is a raw `uint16_t`, it can reach 65535, making
`sect_off_size = 8192` — an 8192-byte read for a single address field,
against a real section-info buffer typically tens to low hundreds of bytes.

**Measured:** patched only `max_sect_addr` (header offset 619+44=663, 2
bytes) from 63 to `0xFFFF` in the same tracked seed used above, leaving the
section counts and list untouched.

- **`h5policy --profile untrusted-strict`: rejects outright** —
  `H5_CORRUPT_FSM_SECTION_OVERRUN` (`h5policy_walk_fspace_sections`,
  `h5_messages.pk:1192 (cur + off_size + 1UL > limit)`, whose own `off_size` is computed the same way, via
  `h5policy_bytes_for_bits(max_addr_bits)`). **Not a coverage gap.**
- **Stock build** (`h5stat -s`): does not crash, but produces visibly wrong
  output — 2 of 3 real sections in the corrupted manager replaced with
  garbage "size 0" phantom entries.
- **Fresh ASan build** (reused from the V2-B-tree area, unmodified): a
  minimal C reproducer calling `H5Fget_free_sections()` crashes at the exact
  predicted line:
  ```
  AddressSanitizer: heap-buffer-overflow H5FScache.c:1010
    in H5FS__cache_sinfo_deserialize
  0x... is located 8142 bytes after 71-byte region [...]
  ```
  matching the predicted ~8192-byte width almost exactly. The unmodified
  seed runs cleanly through the identical reproducer.

**Why the sibling computation, `sinfo->nbins`, is not similarly dangerous:**
`sinfo->nbins = H5VM_log2_gen(fspace->max_sect_size)` is self-limiting —
`log2` of even a full 64-bit value tops out around 64 — while
`sect_off_size`'s linear `(max_sect_addr+7)/8` formula has no such ceiling.

**Why this sits here and not in the main table:** same shape as
`max_idx_set`/`node_nrec` above — `h5policy` already independently rejects
the corruption via a real, dedicated check computed the identical way
libhdf5 computes the dangerous width, so the *field* is fully covered.
What's uncatalogued is the *mechanism*: nothing in libhdf5 itself — not even
an assert — stands between the raw value and the read length it drives.

**Not chased further:** the *low* end of `max_sect_addr` (e.g. 0, making
`sect_off_size = 0`) — plausible as a different kind of misalignment (every
subsequent address field silently collapsing to zero-width), not
fixture-tested this round.

### Metadata-cache images — prefetched-entry deserialization — checksum verification skipped entirely by design, already caught by `h5policy`

When a metadata cache image (MDCI) is loaded, each entry's raw bytes are
copied wholesale into an in-memory "prefetched" placeholder
(`H5C__reconstruct_cache_entry`, `H5Cimage.c:2700-2899`) — bounds-checked
against the cache-image block's own buffer (`H5_IS_BUFFER_OVERFLOW`, real,
not the finding here). When the application later touches that address,
`H5C__deserialize_prefetched_entry` (`H5Centry.c:1786`) converts the
placeholder into a real typed entry. Its own comment states the design
explicitly:

```c
/* Since the size of the on disk image is known exactly, there is
 * no need for either a call to the get_initial_load_size() callback,
 * or retries if the H5C__CLASS_SPECULATIVE_LOAD_FLAG flag is set.
 * Similarly, there is no need to clamp possible reads beyond
 * EOF.
 */
len = pf_entry_ptr->size;
if (NULL == (thing = type->deserialize(pf_entry_ptr->image_ptr, len, udata, &dirty)))
    ...
```

It calls `type->deserialize()` directly — skipping the `verify_chksum` step
a normal fresh on-disk load always runs first. This is not assert-masked;
there is no assert involved at all. It is a deliberate, commented design
choice to trust cache-image content as already validated — and, measured
directly (not assumed), that trust turns out to have no real boundary in
libhdf5's own read path at all.

Three separate checksum layers are involved here, worth distinguishing
precisely: (1) the MDCI *message* itself (the cache image's declared
`addr`/`size`) lives inside a normal v2 object-header chunk, whose own
checksum genuinely is verified, like any object header's; (2) the
cache-image *block*'s own trailing checksum, computed once over the whole
block at write time (`H5C__construct_cache_image_buffer`,
`H5Cimage.c:301-304`); and (3) each individual entry's own type-specific
internal checksum (the object-header test below). Grepping every
`H5_checksum_metadata` call in `H5Cimage.c` finds both occurrences confined
to the write path (one real, one inside a debug-only self-check) — **there
is no call to verify layer 2 anywhere in the read path**, confirmed
directly: corrupting the block's own trailing checksum, without resealing
it, opens exactly as cleanly as the inner-entry test below. So libhdf5's
own read path checks neither the block-level checksum nor any individual
entry's checksum — only layer 1 (the message's own container checksum) is
real, and it protects only the address/length declaration, not the
block's actual content.

**Measured, not assumed — with a direct control-vs-mutant contrast.** Used
the tracked seed `h5policy/tests/valid/cache_image.h5` (root group +
"indexed" group + "payload" dataset; cache image with 3 real entries, all
object headers).

- **Control** (a fresh, cache-image-free file, same shape,
  `libver="latest"` to force v2 object headers): flipped one bit in the
  root group's real, on-disk object header's own trailing Jenkins
  checksum. Opening it: `RuntimeError: Unable to get group info (incorrect
  metadata checksum after all read attempts)` — cleanly rejected, as a
  normal load always is.
- **Mutant (layer 3, inner entry)** (the same seed, cache image intact):
  flipped the identical bit in the identical checksum field, but inside
  the cache-image entry's copy of that header. Resealed only the cache
  image's own outer block checksum around it (Jenkins lookup3, not
  cryptographic — trivially attacker-computable, reused from `h5mutate`).
  Opening it: **succeeds completely silently** — `h5py.File(...)` opens
  without error, and every attribute/group/dataset reads back fine.
- **Mutant (layer 2, outer block)** (the same seed again): corrupted the
  cache-image block's own trailing checksum directly, one byte, with
  **no** resealing at all. Opening it: **also succeeds completely
  silently** — confirming layer 2 is never checked either.

**`h5policy` coverage: not a gap for either layer.** `--profile
untrusted-strict` correctly rejects both mutants — the inner-entry
corruption via `H5_CORRUPT_BAD_CHECKSUM`, "object-header checksum
mismatch," at offset 48, `h5_validate.pk:1166 (checksum != stored_checksum)`; the outer-block corruption via the same code,
"metadata cache image checksum mismatch," at offset 2766, `h5_messages.pk:1905 (image_checksum != stored_checksum)` — because
`h5policy`'s own cache-image handling independently computes and verifies
both the block's own checksum and each replayed entry's checksum against
its logical address (its README: "replays all validated cached entry
bodies through the ordinary bounded metadata decoder"). Same shape as
`node_nrec`/`max_sect_addr` above: real, severe, measured libhdf5 defects
that `h5policy` already independently defends against.

**Honest scope of the "attacker value" here.** Since Jenkins lookup3 is
not cryptographic, a fully-capable attacker constructing a file from
scratch can always compute a matching checksum for whatever bytes they
want — so this specific bypass mostly matters for *accidental* corruption
(bit-rot, torn writes, degraded storage media) rather than deliberate,
adversarial tampering. A real but different concern from "attacker injects
arbitrary content," and the two should not be conflated.

**Also checked, and retracted after review — not a finding:** swapping one
real, validly-checksummed cache-image entry's content into a *different*
entry's address slot (making the root group's cache-image entry actually
contain the "indexed" group's real content) also opens silently, and
`h5policy` also accepts it with zero findings. This was first reported as
a severe gap, but it doesn't hold up on scrutiny, for a simple reason: any
attacker who can write the file's bytes at all could get the exact same
result — a root group that directly contains what "indexed" used to
contain — just by writing an ordinary, non-cache-image file with the
honest HDF5 API. No trick, no bypass, and nothing about the result is
corrupt. So this test didn't show anything specific to how cache images
work; it only showed that an attacker who controls a file's bytes can make
the file say whatever they want, which is true of every file format and
isn't a bug on its own.

**Not chased further:** a second, independent code defect exists at
`H5Cimage.c:2820-2824` — `H5C__reconstruct_cache_entry`'s "Validate address
range" check references the entry's `size` field *before* it is decoded
three lines later (`H5Cimage.c:2829`), so it always checks against a stale
zero (`H5FL_CALLOC`-initialized) rather than the real size, meaning
`addr + size <= eoa` is never actually validated with the real size,
anywhere. Attempted to weaponize this into an EOF/EOA overrun for a
naturally-reachable entry: a naive size inflation was cleanly caught by a
*different*, correctly-implemented check (`H5_IS_BUFFER_OVERFLOW` against
the cache-image block's own buffer) in both `h5policy`
(`H5_CORRUPT_MDCI_ENTRY_OVERRUNS_IMAGE`, `h5_messages.pk:1826 (entry_span > image_size - cur)`) and the real build ("invalid
entry size"). Because the cache-image block is always allocated last in a
library-written file (at the then-current EOA), any naturally-reachable
entry's real address is inherently smaller than the cache-image block's
own address, so `entry.addr + entry.size <= entry.addr + image_len <
image_addr + image_len <= eoa` always holds structurally — the vacuous
check's absence cannot be exploited via the ordinary "natural placement"
path. Escaping that would need a hand-constructed file with the
cache-image block placed before a real object's address (not achievable
by patching a real seed), and even then the consequence is unclear, since
`addr`/`size` are just labels on an already-safe, fully-backed heap buffer
for a read-only scenario. Left as a documented, real code defect with no
demonstrated independent consequence.

### Fractal heaps — `H5HF__dtable_lookup` row overflow — libhdf5 unguarded, but `h5policy` independently bounds it

`H5HF__dtable_lookup` (`H5HFdtable.c:135-160`) computes a row/column pair
from a heap offset via `log2(off)`, with **no check of any kind** — not
even an assert — that the resulting row is `< dtable->max_root_rows`
before indexing `row_block_size[row]`:

```c
unsigned high_bit = H5VM_log2_gen(off);
*row = (high_bit - dtable->first_row_bits) + 1;
*col = (off - off_mask) / dtable->row_block_size[*row];   /* H5HFdtable.c:156 */
```

It's reached during an ordinary object lookup — `H5HF__man_op_real`
(`H5HFman.c:350`, and independently `H5HF__man_remove`, `H5HFman.c:575`,
via `H5Ldelete`) — whose only gate on the heap ID's `obj_off` is
`obj_off > hdr->man_size` (`H5HFman.c:324`), and `man_size` is itself
decoded raw with zero validation.

For a byte-aligned `max_index` (a multiple of 8, as every real writer
produces), this alone is harmless: the heap ID's own byte width
(`heap_off_size`, derived from the same `max_index`) mathematically caps
the maximum expressible offset at exactly `max_root_rows - 1`, with zero
slack. The hazard only opens up when `max_index` is *also* corrupted to a
**non-byte-aligned** value — `heap_off_size` rounds up to the next whole
byte (unchanged), but the logical row bound (`max_root_rows`, derived
straight from the smaller `max_index`) shrinks, creating slack a crafted
`obj_off` can exploit.

**Measured, with a clean two-step isolation.** Fixture:
`h5policy/tests/valid/dense_links_deep.h5`, `max_index` 32→25 and
`man_size`→`0xFFFFFFFFFFFFFFFF` in the header (checksum resealed), plus one
dense-link B-tree leaf record's `obj_off` field set to `0xFFFFFFFF` (leaf
checksum resealed). Triggered via ordinary `H5Literate2`.

- **Header corruption alone** (heap ID left untouched): `h5policy`
  accepts, real libhdf5 succeeds cleanly — confirming the header fields by
  themselves do nothing.
- **Header + corrupted heap ID**: `h5policy --profile untrusted-strict`
  rejects (`H5_CORRUPT_FRACTAL_HEAP_ID`, "cannot be resolved in file
  bounds", `h5_dense_links.pk:1356 (H5_CORRUPT_FRACTAL_HEAP_ID)`) — but see below. Real libhdf5: stock `SIGSEGV`; ASan confirms
  `heap-buffer-overflow READ of size 8` at `H5HF__dtable_lookup`
  (`H5HFdtable.c:156`), landing in the `row_block_size[]`/`row_block_off[]`
  region sized by the (shrunk) `max_root_rows`, via the exact predicted
  call chain (`H5Literate2 → ... → H5HF__man_dblock_locate →
  H5HF__dtable_lookup`).

**`h5policy` coverage: already covered — not a gap.** The rejection above
is a genuine, targeted catch of the corrupted heap ID, confirmed by the
header-only isolation test above accepting cleanly (ruling out an
incidental/artifactual rejection the way finding 2's `nentries` A/B test
did). Tracing *why* it's caught: `h5policy` never calls into libhdf5's
`H5HF__dtable_lookup` at all — it independently re-derives the same
row/column navigation arithmetic itself, in `h5policy_frhp_locate`
(`h5policy/pickles/h5_dense_links.pk:969-1062 (h5policy_frhp_locate)`), and that reimplementation
happens to include the exact bound libhdf5's own C code is missing:

```
if (row >= cur_nrows || col >= width) return 0xffffffffffffffffUL;   /* h5_dense_links.pk:1028 (row >= cur_nrows) */
```

That sentinel is what actually reaches the surface as
`H5_CORRUPT_FRACTAL_HEAP_ID` above — a real, deliberate check, just one
that happens to live on the `h5policy` side rather than in libhdf5 itself.
So unlike every other finding in this table, there is nothing to recommend
on the `h5policy` side here; the interesting direction runs the other way.

**Recommendation (not implemented here):** port `h5policy`'s own
`row >= max_root_rows`-equivalent bound into libhdf5's
`H5HF__dtable_lookup` itself (`H5HFdtable.c:135-160`), right after `*row`
is computed at line 156 and before it indexes `row_block_size[*row]` —
using `h5_dense_links.pk:1028 (row >= cur_nrows)` as the reference implementation for what
the check should look like, since `h5policy`'s version has already been
measured to catch exactly the corruption that crashes real libhdf5.

**Not chased further:** the same mechanism via
`H5HFiblock.c:1754`/`:1778` (`H5HF__man_iblock_parent_info`) — checked and
ruled out: its only caller passes an already-live, internally-trusted
in-memory section address, not anything freshly decoded from untrusted
bytes.

### Fractal heaps — `H5HF__man_iter_start_offset` row-search overflow — write-only reachable, outside `h5policy`'s own mandate

`H5HF__man_iter_start_offset` (`H5HFiter.c:105-249`) linearly searches all
`max_root_rows` rows for one whose range contains a given offset:

```c
for (row = 0; row < hdr->man_dtable.max_root_rows; row++)
    if ((offset >= hdr->man_dtable.row_block_off[row]) &&
        (offset < hdr->man_dtable.row_block_off[row] + (width * row_block_size[row])))
        break;

curr_offset = offset - hdr->man_dtable.row_block_off[row];   /* H5HFiter.c:159 */
```

If no row matches, the loop runs to completion without ever `break`ing,
leaving `row == max_root_rows` — one past the end of both
`row_block_off[]` and `row_block_size[]`. Nothing catches this, not even
an assert. Both callers (`H5HF__hdr_update_iter`, `H5HF__hdr_reverse_iter`)
pass `hdr->man_iter_off` — the heap's own "next allocation" bookkeeping
field, decoded raw with zero validation and, unlike `obj_off` above, with
no structural tie to `max_index`/heap-ID byte width at all: a single
corrupted 8-byte field is sufficient on its own.

**Measured.** Same seed, single field changed: `man_iter_off` (header
offset 5230) → `0xFFFFFFFFFFFFFFFF`, checksum resealed — nothing else
touched. Only reachable once the heap's existing free space is exhausted
and a genuinely new direct block must be allocated (the iterator is
otherwise never consulted): the *first* `H5Dcreate2` on the mutant
succeeded cleanly (existing free space absorbed it); 500 sequential
inserts exhausted it and reached the vulnerable path. `h5policy` accepts,
zero findings. Real libhdf5: stock `SIGSEGV`; ASan confirms
`heap-buffer-overflow READ of size 8, 0 bytes after a 176-byte region` at
`H5HF__man_iter_start_offset` (`H5HFiter.c:159`), via the exact predicted
call chain (`H5Dcreate2 → ... → H5HF__hdr_update_iter →
H5HF__man_iter_start_offset`). Control (500 inserts on the unmodified
seed): clean, exit 0.

**Why `h5policy`'s accept here is a different kind of thing than the
row-overflow finding above.** `h5policy` is an explicit, hard, read-only
boundary — no writes, by design. `man_iter_off` has zero bearing on reading
the file's existing, already-written content; it exists purely to answer
"where should the *next* write go," a question that only arises for a
consumer that writes, which `h5policy` by design never is. That makes this
accept structurally different from both neighbors: the row-overflow finding
above turned out not to be an accept at all (`h5policy` independently
rejects it), while this one is a genuine accept that isn't a gap either —
it's a question outside what a read-only preflight tool could ever be asked
to answer, closer in spirit to this project's own documented "known blind
spots" than to a missed check.

**Not chased further:** the `H5HF__hdr_reverse_iter` path (removing the
heap's highest direct block) — only the insert/`H5HF__hdr_update_iter`
path was fixture-tested.

### Fractal heaps — tiny-object extended-length overread — position-dependent heap-buffer-overflow, `h5policy` honestly declines rather than guesses

"Tiny" fractal-heap objects are stored inline in the heap ID itself,
length encoded directly in 1-2 flag-byte bits
(`H5HF__tiny_get_obj_len`, `H5HFtiny.c:179-205`). `hdr->tiny_len_extended`
(from `hdr->id_len`, decoded raw with zero validation) enables a 2-byte
length field nominally reaching 4095+1 bytes — capped in practice near 256
by a separate masking quirk (`H5HFtiny.c:199` ANDs a raw 8-bit flag byte
against `0x0F00`, whose bits can never be set in 8 bits, silently zeroing
the intended high-nibble contribution) — but even 256 is far larger than
the fixed 7-byte ID buffer any real caller allocates
(`H5G_DENSE_FHEAP_ID_LEN = 7`).

`H5HF__op_read` (`H5HF.c:86`) is an unconditional `memcpy` of the full
claimed length — a real, unguarded overread mechanism — but the callback
actually used for dense-link iteration
(`H5G__dense_iterate_fh_cb → H5O_msg_decode → H5O__link_decode`) checks a
version byte first and rejects immediately if it doesn't recognize it,
which is why a *naively* corrupted ID (garbage in the version-byte
position) never reaches the hazard in practice. Deliberately crafting a
*valid* version byte (`H5O_LINK_VERSION = 1`) lets decoding continue past
it, into further fields each individually guarded by a real
`H5_IS_BUFFER_OVERFLOW` check — but that check validates against the
*claimed* length (capped ~256 by the masking quirk above), not the real
underlying buffer.

**The decisive factor: an entire B-tree leaf's records decode into one
shared allocation.** `H5B2__iterate_node` (`H5B2int.c:1652`) calls
`H5FL_fac_malloc` once per leaf (measured: 540 bytes for a leaf of 35
records), not once per record. A corrupted record's "runway" before the
real edge of that allocation depends entirely on where it sits within the
leaf:

- **First record in the leaf**, deliberately-valid version byte, crafted
  name length up to ~220 bytes: real libhdf5 (stock and the reused ASan
  build) — **no crash, ASan reports nothing.** The overread lands on other
  records' own legitimate bytes, still inside the same 540-byte
  allocation.
- **Last record in the same leaf**, identical corruption, identical name
  length (220): **ASan confirms a real heap-buffer-overflow** —
  `READ of size 220`, `0 bytes after a 540-byte region`, at the link-name
  `memcpy` (`H5Olink.c:208`), via the exact predicted call chain
  (`H5Literate2 → ... → H5HF__tiny_op → H5G__dense_iterate_fh_cb →
  H5O__link_decode`). Stock build: does **not** crash — it silently copies
  adjacent heap memory into the returned link name (confirmed by diffing
  output against a control run: a real link's name is replaced by a
  bogus, empty-looking one) — an information-disclosure risk on an
  ordinary, unprotected build, not a crash. Control (unmodified seed, both
  builds): clean.

**`h5policy` coverage:** an honest `unsupported_coverage_gap` refusal
(exit 5, "dense link name index uses a non-managed fractal-heap ID") at
both record positions — not a false accept, and not a positive catch of
the specific overflow either.

**Not chased further:** dense attributes
(`H5A__dense_copy_fh_cb → H5O__attr_decode`) — confirmed by direct
code-reading to have the identical version-check-first structure
(`H5Oattr.c:147-149`), and very likely the same position-dependent
mechanism, but not independently fixture-tested; SOHM, not checked at
all; whether an even larger claimed length can be pushed past a genuinely
unmapped page rather than just past one ASan-tracked redzone.

## Status: remaining areas (not started)

| Area | libhdf5 source | Notes |
|---|---|---|
| Dataset chunk records | `H5Dchunk/btree/btree2/farray/earray/single/none.c` | `chunk-dim-product-64bit-overflow.yml` names one case directly |
