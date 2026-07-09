# Mapping HDF5 Binary Primitives onto an Object Store

**Assumption/Decision:** The linear address space is no longer required. Byte identity with any
ingested `.h5` file is explicitly sacrificed; **format compatibility** *is* retained via a canonical linearization (described below). Attestation moves to a canonical per-object level.

## Invariants

1. **Token-width preservation.** Size of Offsets stays 8 bytes; `haddr_t` fields are
reinterpreted as opaque object IDs (OIDs). Every structure encoding remains bit-compatible with the published format; no spec fork. The undefined address (all 1s) is the null key. Addresses identify structure starts only — no address arithmetic.
2. **Store semantics, derive access paths.** Persist only structures carrying user-visible content; regenerate all container/index structures at linearization time.
3. **Snapshot commits.** All visibility changes occur via copy-on-write manifest updates and an atomic root swap. This is SWMR's ordered-flush discipline transplanted.
4. **Canonical linearization.** Deterministic traversal, deterministic offset assignment, token substitution (OID → offset), checksum recomputation, synthesized free-space/EOA. Same graph in → identical `.h5` bytes out. `h5repack` is the existence proof and the compatibility precedent: it already rebuilds all container structures from records.

## Stored vs. derived

### Stored (semantic content)

- Object header message bodies
- Link records (name, target, creation order, charset)
- Attribute records (incl. creation order)
- Chunk records: (coords → digest, size, filter mask)
- VDS mappings (layout v4 virtual entries; user data)
- Committed datatype bodies
- External file lists / external link targets
- Per-dataset original index type (provenance enum)

### Derived at linearization (access path)

- v1 and v2 B-trees (all record types)
- Fractal heaps (`FRHP`/`FHDB`/`FHIB`) + heap IDs
- Fixed / Extensible array index blocks
- Symbol table nodes (`SNOD`), local heaps
- SOHM tables (re-deduplication)
- Free-space manager, aggregators, EOA
- Global heap collections (regenerated for VL data)
- Superblock (synthesized; version per profile)

**Key subtleties:** (a) Appendix C index-type selection is a deterministic function of dataspace properties (single fixed chunk → Single Chunk; fixed dims, no filters → Implicit; fixed → Fixed Array; one unlimited → Extensible Array; else v2 B-tree), so canonical linearization regenerates the correct index, not merely a valid one. (b) Fractal heap layout depends on insertion history; heap IDs are therefore regenerated (canonical insertion = creation order) and re-embedded in regenerated B-tree records — internally consistent, historically different. Creation-order values are stored record fields for exactly this reason. (c) Chunk filter masks are user-visible state recoverable from nowhere else; they are first-class manifest fields (they are, verbatim, the content of v2 B-tree record types 10/11).

## Keyspace

The keyspace splits along the mutation grain of the format itself:

**Metadata plane:** keyed by OID, overwritten in place. Object headers, B-tree nodes, fractal heap blocks, group symbol-table nodes, local heaps, global heap collections, SOHM tables. These are exactly the structures the library's metadata cache already treats as unit-of-dirty; a PUT per evicted cache entry is the natural write path.

**Payload plane:** keyed by content hash, immutable, deduplicating. Dataset chunks (filtered bytes as-written), contiguous data bodies, and optionally committed-datatype message bodies. Chunk indexes then store the OID of a small chunk stub — or, better, the index record's address field holds an OID that the OID map resolves to a hash key (see below), so the on-disk index encoding is untouched.

```text
{c}                                   container (one HDF5 "file"); bucket or prefix

{c}/root                              commit pointer: tiny object naming the current
                                      superblock OID + OID-map generation + Merkle root

{c}/sb/{gen}                          superblock + superblock-extension OH, synthesized superblock
                                      parameters per generation (profile, K values), versioned

{c}/map/{shard}/{gen}                 OID map shards: oid → (key, size, class, hash) record 
                                      manifests, COW-sharded: object-header stubs, link records,
                                      attribute records, chunk records, dtype bodies (small bodies
                                      inline, large by digest reference)

{c}/h/{algo}/{digest}                 payload plane: immutable, content-addressed, deduplicating :
                                      chunk bytes (post-filter), contiguous data bodies, large
                                      message bodies

{c}/ext/{name}                        external-reference table: EFL filenames, external
                                      link targets, VDS source files → container IDs/URIs

{c}/att/{gen}                         attestation manifest, attestation objects: signed Merkle
                                      roots; ingest records
```

The payload plane is conflict-free by construction: content-addressed `PUTs` are idempotent, so any number of uncoordinated producers may write it. All coordination concentrates in `{c}/map` and `{c}/root`.

### The OID map is the load-bearing structure

Naïvely, OID-keyed mutable objects give us last-write-wins with torn readers. The fix is the same trick the format has used since the superblock extension: one level of indirection. The OID map — sharded by OID range, each shard a small immutable object, each generation copy-on-write — resolves OID → current object key. A commit is: PUT new payload/metadata objects → `PUT` changed map shards at `{gen+1}` → atomically swap `{c}/root`. That's SWMR's ordered-flush discipline transplanted verbatim; readers pin a root and see a consistent snapshot, time travel falls out for free, and GC is "delete objects unreachable from retained roots." Hot-path cost is one extra small `GET` per cold OID, amortized by caching shards — and note the map shard *is* morally a fixed-array index block, so the format already taught us how to build it.

For write-hot metadata we can cheat: allow selected classes (v2 B-tree leaves under active append) to bypass the map and be overwritten at their OID key directly, accepting torn-read risk only within an uncommitted epoch. That's a tuning knob, not an architecture change.

## Commit model

- **Compatibility bar:** HDF5 defines no concurrent-mutation semantics (SWMR is
  single-writer; parallel HDF5 is one logical writer). Base profile therefore: **N uncoordinated payload writers, one committer**. Producers stream content-addressed chunks and hand `(coords, digest, size, filter-mask)` tuples to a sequencer, which batches COW manifest-shard updates and swaps `{c}/root`.
- **Epoch granularity:** is a batching parameter bounded below by root-key churn, GC pressure, and signing cost (practical floor ≈ 1–10 Hz) and above by reader staleness and crash-replay window. SWMR-replacement workloads: 100 ms–1 s. Bulk ingest: seconds–minutes, size-triggered. Adaptive commit-on-max(interval, dirty-shard-count) recommended.
- **Crash semantics:** uncommitted objects are invisible garbage (GC'd); no torn-file state is observable — strictly better than the linear format's failure modes.
- **Multi-writer extension (off by default):** optimistic CAS on root with disjoint-shard merge; same-shard conflict → rebase/retry. Explicitly new semantics (`git`-style) not sanctioned by the format; quarantined as an extension profile so the compatibility claim stays crisp.
- **GC × attestation interaction:** retention must pin all objects reachable from signed roots; otherwise the Merkle history develops holes precisely where an auditor would look.

## Attestation

- Manifest shards carry per-record content hashes; shards hash up to a **Merkle root per commit** stored in `{c}/root` and signed into `{c}/att/{gen}`. Per-object granularity, diff-able between commits; strictly stronger than a whole-file hash.
- **Ingest record:** because container structures are derived (not stored), the ingested file's layout fingerprint, signature census, per-dataset index types, superblock version, the minimum-writer bound from the matrix above, is captured at ingest as an immutable `{c}/att/` object. Layout history is provenance, not content.
- **File-level attestation** is recovered via canonical linearization: the stable hash attests the canonical serialization (format-semantic content), not accidental layout history.

### Attestation and the linearization contract

Since we're moving attestation per-object: the natural manifest is the OID map itself, enriched — each entry carries the content hash of the object's **encoded structure bytes with address fields normalized** (OIDs are already stable, so no normalization is even needed within the store; only linearized offsets vary). The map shards hash up to the root pointer, giving us a Merkle root per commit: sign that, and we've attested the entire object graph with per-object granularity — stronger than any whole-file hash, and diff-able between commits, which is precisely the provenance story for our audit framework.

Format compatibility is then a *canonical linearization*: deterministic traversal (say, ascending OID), deterministic offset assignment, token substitution, checksum recomputation, synthesized free-space/EOA. Same graph in → identical `.h5` bytes out, every time. So we recover a stable file-level hash too - not of the original ingested file, but of the canonical serialization, which is arguably the more defensible attestation object anyway (it's the format-semantic content, not accidental layout history).

## Exceptions

| Case | Handling |
| ------ | ---------- |
| Contiguous layouts (address + size, arbitrary extent) | Single payload object; shard as `{digest}/{n}` extents above threshold; `(address,size)` regenerated at pack time |
| v1 object-header continuations (unsignatured extents) | Coalesced into parent record set; valid continuation messages re-emitted at pack time |
| Symbol-table-entry scratch pads (cached addresses) | Not stored; regenerated or cache-type-zeroed at pack time |
| External file lists / external links / VDS sources | Quarantined in `{c}/ext/`; inherently foreign byte ranges / URIs |
| User block, driver-info block | Ingest-side provenance only; re-emitted on request at pack time |

## Commit-epoch granularity under concurrent writers

We don't want to invent a distributed database. The current format has no concurrent-mutation semantics: SWMR is single-writer with ordered visibility; parallel HDF5 is many processes forming one logical writer via collective MPI-IO. So the compatibility bar is single-writer commits — anything beyond that is new semantics we choose to define, and should be quarantined as such.

Within that bar, the derived-index decision does most of the work. The payload plane is content-addressed and immutable, so concurrent chunk *production* is conflict-free by construction: any number of producers can `PUT {c}/h/{algo}/{digest}` objects with no coordination whatsoever, because a content-addressed `PUT` is idempotent. All contention concentrates at exactly two points: manifest-shard updates and the root swap. That gives us the natural deployment shape for your actual workloads (detector/instrument ingest): **N uncoordinated payload writers, one committer**. Producers stream chunks and hand `(coords, digest, size, filter mask)` tuples to a sequencer; the sequencer batches manifest-shard COW updates and swaps the root. No locks, no CAS storms, and HDF5 semantics preserved exactly.

Epoch granularity then becomes a batching parameter, not a correctness question, and it's bounded on both sides by concrete numbers. Lower bound: the root is a single hot key, and object stores throttle per-prefix request rates (S3 on the order of a few thousand `PUT`/s per prefix, but a *single key* with read-after-write consistency wants far less churn than that), plus every epoch generates map-shard garbage for GC and, if you sign roots, an attestation cost. Practical floor: don't swap faster than ~1–10 Hz. Upper bound: epoch length is the reader-staleness window (SWMR VFD...) and the crash-replay window: uncommitted objects after a crash are invisible garbage (a genuinely better failure mode than the linear format's torn-file corruption; there is no "partial epoch" state a reader can observe). For SWMR-replacement use cases, epochs of 100 ms–1 s replicate the flush cadence applications already expect; for bulk ingest, seconds to minutes with size-triggered commits. We can make it adaptive: commit on max(interval, dirty-shard count), and it's a tuning knob per container.

If we later want true multi-writer, the COW shard structure gives us optimistic concurrency almost for free: writers prepare disjoint shard deltas and CAS the root; disjoint-shard commits merge trivially (different datasets → different shards), same-shard conflicts retry with rebase. This is `git` semantics grafted onto HDF5, with merge rules HDF5 never defined (two writers appending to the same unlimited dimension have no format-sanctioned outcome). We need to specify this as an explicit extension profile, off by default, so the base design's compatibility claim stays intact and crisp. Finally: signed roots and GC are in tension. The retention policy must treat attested roots as pinned, or the Merkle history develops holes exactly where an auditor would look.

## Summary

The design needs exactly three inventions: the OID map, the root-swap commit, and the canonical pack order. Everything else is the 1998 graph wearing different edge labels.

This design keeps the **binary record encodings** and the HDF5 file format's type system while adopting Zarr's storage economics (content-addressed immutable chunks), `git`'s commit model (COW manifests, root swap, Merkle attestation), and `h5repack`'s regeneration discipline as the compatibility bridge. Net inventions required: the record manifest, the root-swap commit, and the canonical pack order.
