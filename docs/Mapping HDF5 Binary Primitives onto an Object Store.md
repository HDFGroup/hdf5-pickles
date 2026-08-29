# Mapping HDF5 Binary Primitives onto an Object Store

> **Status: design proposal.** This repository does not currently implement the
> importer, exporter, or object-store representation described below. The
> document defines a prospective preservation and reconstruction contract.

## Summary

The compatibility bridge is not an OID-shaped substitute for every file
address. It is a relocation-aware object representation:

```text
HDF5 bytes
    -> preserved atoms + typed relocations + semantic index records
    -> key/value snapshot
    -> deterministic allocation + regenerated indexes + relocation patching
    -> conforming HDF5 bytes
```

The first and last byte strings may differ. Their non-indexing atoms agree
byte-for-byte outside declared patch sites, their references resolve to the same
logical targets, and their reachable HDF5 graphs have the same modeled meaning.
After the first canonical export, the loop reaches a byte-identical fixed point.

Where to look:

- **What is the claim, exactly?** [Round-trip
  contract](#round-trip-contract), and [Atom
  correspondence](#atom-correspondence) for what makes it checkable rather than
  merely stated.
- **Which bytes survive, and which are rebuilt?** [Byte ownership
  model](#byte-ownership-model) and [Stored records and derived
  structures](#stored-records-and-derived-structures).
- **What does one file actually look like?** [A worked
  example](#a-worked-example).
- **What would it cost to build here?** [Relationship to this
  repository](#relationship-to-this-repository) and [Staged
  implementation](#staged-implementation).
- **What is still unresolved?** [Open questions](#open-questions) and
  [Non-goals](#non-goals).

## Why an object store

HDF5's container is a single linear address space with an internal allocator.
That assumes a mutable file with cheap small writes at arbitrary offsets. An
object store offers the opposite: immutable objects, no in-place update,
conditional-write and listing primitives instead of an allocator, and a latency
floor that makes a pointer chase expensive.

The usual responses each give something up:

- **Store the `.h5` file as one object.** Everything about HDF5 keeps working
  and nothing about the store does — no deduplication, no snapshot, no partial
  update, and every writer serializes on the whole artifact.
- **Store a sidecar index into byte ranges of that object.** Reads become
  cheap; writes, provenance, and any structural change do not, and the file
  remains the unit of truth.
- **Convert to a store-native format.** Reads and writes become cheap, and the
  HDF5 artifact is gone, taking with it the datatype model, the attribute
  model, and any claim that what comes back is what went in.

This design takes a fourth option: decompose the container so the store holds
what the HDF5 file *means* — content atoms, typed relocations, and semantic
index records — and regenerate the linearization machinery on demand. The
artifact becomes reproducible rather than retained. The store gets immutable
content-addressed objects, deduplication, snapshot isolation, and many
uncoordinated producers; an export is still a conforming HDF5 file that
preserves the original's non-indexing bytes.

The cost is the exporter. Rebuilding indexes correctly is the whole of the
work, and the [round-trip contract](#round-trip-contract) exists to say
precisely what a rebuild is allowed to change.

The scope is the round trip: file in, file out. Serving HDF5 reads directly out
of the store without an export is a plausible extension and is not specified
here; see [Non-goals](#non-goals).

## Prior art

| Approach | What it does | Why it is not this |
| --- | --- | --- |
| HSDS and the `h5pyd` sharded schema | Decomposes an HDF5 domain into per-object metadata and per-chunk objects in a store, served through a REST API. | The closest neighbour, and evidence that the decomposition is practical at scale. Its unit of truth is its own schema rather than the source bytes: no byte-preservation claim, no relocation model, and a round trip back to a file is a re-write, not a reconstruction. |
| kerchunk and VirtualiZarr reference sets | Record byte ranges of existing HDF5 files so an array client can read chunks directly. | The file stays authoritative and the reference set is a read accelerator over it. Nothing is preserved, rebuilt, or attested, and metadata that is not chunk-addressable is out of scope. |
| Zarr and comparable store-native array formats | One object per chunk, metadata as store objects. | Solves the storage problem by not being HDF5. There is no object header, link, shared-message, or reference encoding to preserve, so the question this document answers does not arise. |
| The `ros3` driver, page buffering, paged aggregation | Read an unmodified HDF5 file from object storage, with page-aligned allocation to make the reads coarse. | Byte-preserving by construction, because the file is untouched, and correspondingly without deduplication, snapshots, partial update, or concurrent producers. Complementary rather than alternative: paged aggregation is a good export-profile setting. |
| `h5repack` | Rebuilds a conforming HDF5 container from decoded records, changing layout, filters, and index families. | Engineering precedent that the rebuild is possible, and an exporter in miniature. It is not evidence of byte preservation or canonical determinism: it preserves no atom bytes by contract, pins nothing, and emits no manifest. Those properties come from this export contract and its verification. |

## Design goal

This design maps a reachable HDF5 object graph into a key/value store without
preserving the input file's allocation history. It separates bytes that carry
content from bytes that provide indexing, addressing, allocation, or other
linearization machinery.

Import partitions an HDF5 file into three things:

1. **Preserved atoms:** byte strings that carry non-indexing content.
2. **Relocations:** typed fields inside otherwise preserved atoms whose encoded
   values depend on file placement or a regenerated container.
3. **Derived structures:** indexes and allocation structures that can be
   reproduced from records in the first two classes.

An **atom** is a contiguous span of source bytes that the design treats as one
unit of preservation: a message body, a link name, a heap value, a raw-data
extent. The term is unrelated to libhdf5's historical use of *atom* for an
`hid_t` identifier.

Throughout this document, **profile** without a qualifier means an *export
profile* — the pinned set of byte-affecting choices defined under [Export
profiles](#export-profiles). It is a different thing from the `h5policy`
validation profiles used elsewhere in this repository; see the
[glossary](GLOSSARY.md).

The key/value representation stores preserved atoms and relocation records. It
stores the semantic fields found in index records, but not the index topology or
block layout. Export allocates the atoms, resolves the relocations, and rebuilds
the derived structures under an explicit export profile.

The resulting file is a conforming HDF5 file, but it is not expected to be the
same byte string as the input. The intended preservation property is defined
below; this document does not use the ambiguous term "byte-equivalent" without
that definition.

In this document, **binary compatibility for non-indexing data** means exact
encoded bytes for `exact` atoms and exact non-patch bytes for
`relocation-normalized` atoms. It is a file-format preservation claim, not an
application binary-interface claim.

## Round-trip contract

Let `I` be import, `E_p` be export under export profile `p`, and `H` be an
input HDF5 file accepted by that profile:

```text
K  = I(H)
H' = E_p(K)

Certified_p(H -> H')
```

`Certified_p(H -> H')` is a **directed verdict** on an ordered pair, not a
symmetric relation: it says that `H'` is a certified export of `H` under `p`.
The only symmetric relation here is logical equivalence, clause 3 below; the
byte-level clauses and the status gate in clause 6 are one-way obligations on
the export. `H ≈p H'` is shorthand for that verdict and never denotes an
equivalence class.

### Atom correspondence

The byte-level clauses compare atoms, so the verdict is meaningful only
relative to a stated correspondence between the atoms of `H` and those of
`H'`. Export does not preserve carriers. Regenerated sharing decisions can move
a message body between an object header and a shared-message heap; the
profile's compact and dense thresholds can move a link record between a symbol
table and a fractal heap, or a payload between a compact layout message and a
contiguous extent. In each case the content survives and the atom does not.

Every export profile therefore defines a total function

```text
match_p : atoms(H) -> atoms(H') | re-homed(atoms(H')) | dropped
```

subject to:

- **Injective.** No two source atoms correspond to one exported atom.
- **Same carrier:** `match_p(a) = a'` where `a` and `a'` sit in the same
  container class. Clauses 1 and 2 apply to the atom as written.
- **Re-homed:** `match_p(a) = re-homed(a')` where the profile deliberately
  changes the carrier. The atom's *body* bytes must still satisfy clause 1; its
  framing — message header, heap-ID stub, layout class, and the length fields
  that describe it — is derived and excluded from the comparison. Being
  re-homed is not by itself a downgrade: a re-homed atom keeps its preservation
  status.
- **Dropped:** `match_p(a) = dropped` is permitted only where `a` is classified
  `derived`, `padding`, or `provenance-only`. Dropping any other atom refuses
  the verdict.

Every atom of `H'` outside the image of `match_p` must be `derived`. An
implementation reports `match_p` next to the byte-ownership manifest; a verdict
quoted without it is not checkable, because the reader cannot tell which
comparison was performed.

Under `match_p`, the verdict requires:

1. Every preserved atom has identical bytes outside its declared relocation,
   other derived, and checksum fields, and outside the framing excluded for a
   re-homed atom.
2. Every relocated field in `H'` resolves to the same logical object, heap
   value, raw-data extent, or external target as it did in `H`.
3. The reachable object graphs are isomorphic: hard-link identity, link and
   attribute values, datatypes, dataspaces, dataset values, creation-order
   values, references, and other modeled content agree.
4. Every regenerated index is complete, internally consistent, and reachable
   from its owner.
5. `H'` is valid for the HDF5 format and reader bounds named by `p`.
6. **Status gate.** Every reachable non-indexing atom is either `exact` or
   `relocation-normalized`. A `re-encoded` or `pass-through` atom limits the
   result to logical equivalence with explicit exclusions; it does not receive
   the whole-file verdict. An `unsupported` atom prevents certified export.

This separates four claims that must not be conflated:

- **HDF5 format compatibility:** an ordinary HDF5 reader can read the export.
- **Logical equivalence:** the reachable HDF5 object graphs have the same
  modeled meaning.
- **Relocation-normalized byte equivalence:** non-indexing atom bytes are
  preserved except at declared patch sites.
- **Canonical determinism:** the same modeled graph and export profile produce
  the same exported byte string.

For a canonical profile, the first export must also be a fixed point. More
strongly, export must be idempotent over every snapshot, not only over
snapshots that were imported from a file:

```text
H' = E_p(I(H))

E_p(I(H'))     = H'             the first export is a fixed point
E_p(I(E_p(K))) = E_p(K)         export is idempotent, for every snapshot K
```

Both equalities are byte identity. Storage-local object IDs and ingest
provenance may differ after re-import, but they must not affect the canonical
serialization.

The second form is the one to test. The first is its special case at
`K = I(H)`, and only the general form rules out an exporter whose output
depends on how the store was populated — for example one that follows record
insertion order where the profile's canonical traversal should decide.

### Determinism under a preservation profile

A preservation profile consumes the source format census — original structure
versions and index families — as an export input (see [Stored
content](#stored-content)). That is a deliberate exception to "provenance does
not affect serialization" and must be stated as one: under a preservation
profile the census is authoritative content, not ingest metadata, and the
[keyspace](#keyspace) stores it in the record rather than in the attestation.

The determinism claim is correspondingly conditional:

- **Determinism.** Two exports of one snapshot under one preservation profile
  agree byte-for-byte, given the same census.
- **Fixed point.** `E_p(I(H')) = H'` holds only where `I(H')` records a census
  equal to the one `E_p` consumed. An exporter that reproduces the recorded
  index family satisfies this by construction. One that falls back — because
  the recorded family is unsupported, or because the profile's reader bounds
  forbid it — does not.
- A preservation profile that cannot reproduce the recorded census for an
  object exports that object under the canonical rules, records the
  substitution in the manifest, and withholds the fixed-point claim. It must
  not report a fixed point it did not reach.

## Byte ownership model

Classification is performed at the field or atom level, not merely by
structure signature. A B-tree record can contain both a derived child address
and a semantic chunk filter mask. A fractal heap contains derived allocation
machinery as well as link or attribute values that must be retained.

| Class | Examples | Import representation | Export treatment |
| --- | --- | --- | --- |
| Preserved atom | Address-free datatype and dataspace encodings, link names, attribute values, position-independent raw data | Exact bytes plus type and encoding metadata | Copy byte-for-byte |
| Relocatable atom | Hard-link targets, data-layout addresses, shared-message references, VL heap IDs, object and region references | Exact bytes plus typed relocation sidecar | Copy, then patch declared fields |
| Semantic index record | Chunk coordinates and filter mask; link or attribute name and creation order | Logical record independent of node or heap placement | Supply to a deterministic index builder |
| Derived structure | B-tree topology, array index blocks, heap headers and free lists, object-header continuation layout, free-space indexes, checksums and padding | Not retained as content | Rebuild under the export profile |
| Pass-through or provenance | User block, driver information, original layout census, unallocated or trailing bytes | Exact bytes or digest plus a declared policy | Preserve, omit, or reject as the profile specifies |

### Byte-ownership manifest

Each import produces a byte-ownership manifest for the source artifact. Every
input span belongs to exactly one of these classes:

```text
preserved | relocation | semantic-index-field | derived | padding |
pass-through | provenance-only | unsupported
```

The manifest records the source span, owning atom or record, encoding version,
preservation status, and digest. Together with the profile's `match_p` (see
[Atom correspondence](#atom-correspondence)), which names each source atom's
counterpart in the export, it is the basis of the round-trip comparator.
Spans within a relocatable atom are split at patch boundaries, so the atom's
preserved fragments and relocation fields do not overlap in the manifest.
Overlapping reachable structures, unbounded records, or unexplained gaps do not
receive a certified equivalence verdict. Unallocated ranges may be recorded as
provenance without becoming part of logical equivalence.

Preservation status is one of:

- `exact`: all atom bytes are copied unchanged;
- `relocation-normalized`: only declared patch fields change;
- `re-encoded`: content is retained but its byte encoding may change;
- `pass-through`: bytes are retained without a claim about their meaning;
- `unsupported`: certified export is refused.

## Invariants

1. **No OIDs in preserved encodings.** An HDF5 file address is represented in
   the store by a typed relocation, not by writing an object ID into the raw
   field. This retains the original bytes, supports the file's actual field
   width, and keeps object identity separate from file placement.
2. **Typed targets.** A relocation names an object, heap value, byte extent,
   external target, or target-plus-addend as allowed by the source encoding.
   The design does not assume that every address names only a metadata-structure
   start.
3. **Store records, derive access paths.** Index topology, allocator state,
   cache images, free-space state, and container packing are never authoritative
   content. Semantic fields carried by those structures are authoritative.
4. **Stable object identity.** OIDs distinguish HDF5 objects, including
   distinct objects with equal content. Content hashes identify immutable byte
   payloads. Hard links refer to OIDs and therefore retain alias identity.
5. **Snapshot commits.** A committed root names immutable records, payloads,
   manifest shards, and an export profile. Visibility changes by copy-on-write
   publication followed by one conditional root swap.
6. **Profiled linearization.** Offset and length widths, container versions,
   index-selection rules, allocation order, padding, filter implementations,
   and every other byte-affecting choice are inputs to export, not ambient
   library defaults.

## Stored records and derived structures

### Stored content

- Object-header message type, flags, creation order, encoding version, and raw
  body, with relocation fields described separately.
- Link records: raw name, target, link type, creation order, and character set.
- Attribute records: raw name, datatype, dataspace, value, character set, and
  creation order.
- Dataset layout semantics, including dimensions and chunk shape, without a
  physical data or index address.
- Chunk records: coordinates, payload digest, and filter mask. Source stored
  size is retained as provenance and checked against the payload; export derives
  the encoded size from the output payload. **A chunk's absence is content.** An
  unallocated chunk reads as the fill value, so the set of chunk records is
  itself semantic: an index builder that materializes a record for every chunk
  in the dataspace changes what a reader sees, under both the fill-value and
  space-allocation-time settings. Those settings, and the fill value, are stored
  content.
- Compact, contiguous, and chunk payload atoms, subject to the VL, reference,
  and filter rules below.
- Virtual-dataset mappings, committed datatype bodies, fill values, external
  file lists, and external-link targets.
- The semantic payloads extracted from local, global, fractal, and shared
  message heaps.
- Profile inputs and source provenance, including original structure versions
  and index families.

### Derived at export

- Version 1 and version 2 B-tree nodes and child topology.
- Fixed-array and extensible-array index blocks.
- Fractal-heap headers, direct and indirect blocks, managed offsets, free lists,
  and heap IDs.
- Local-heap headers and free lists; symbol-table nodes and cached scratch-pad
  values.
- Global-heap collections, object indexes, packing, and free-space tails.
- Shared-message indexes and deduplication placement. Dereferenced shared
  message bodies remain stored content.
- Object-header chunk packing, NIL messages, continuations, container padding,
  and container checksums. Semantic header fields such as timestamps and phase
  change thresholds remain stored content or explicit profile inputs.
- Metadata cache images, free-space managers, aggregators, allocation gaps, and
  end-of-address markers.
- Superblock address fields and checksums. Offset and length widths and other
  compatibility settings come from the export profile.

An index builder consumes semantic records, not previously serialized nodes.
For example, a chunk index consumes `(coordinates, payload target, stored size,
filter mask)` records. A dense-group builder consumes link records. Rebuilding a
heap is permitted to change heap IDs, but every reference to a heap value is a
declared relocation and is patched consistently.

## Record and relocation representation

A preserved atom is stored with its original bytes. Patch sites live in a
sidecar rather than being overwritten with OIDs:

```yaml
oid: object-42
record_class: object-header-message
encoding_version: 3
raw_bytes: <immutable byte string>
relocations:
  - offset: 16
    width: 8
    kind: object_address
    target: object-17
derived_fields:
  - offset: 60
    width: 4
    kind: checksum
preservation: relocation-normalized
```

Compound references may have more than one patch component. A global-heap ID,
for example, can require both a regenerated collection address and a regenerated
object index. The descriptor records the complete compound encoding rather than
pretending it is a single `haddr_t`.

Record hashes cover the record class, original bytes with patch fields
normalized, the typed relocation descriptors and targets, and relevant encoding
metadata. Payload hashes cover the exact stored payload representation. OIDs are
storage-local identities and are not embedded into an exported HDF5 file.

## A worked example

Take `ex.h5`: a group `/g`, a deflate-filtered dataset `/g/d` of shape
`(4, 4)` with chunk shape `(2, 2)` and only two of its four chunks written, and
one variable-length string attribute `note` on that dataset.

Every span, field offset, and digest below was read off such a file rather than
sketched. They are illustrative, not normative: another writer, or another
library version, places the same structures elsewhere, which is exactly the
property this design refuses to preserve. The structural regime — version 2
object headers, a version 4 chunked layout with a fixed-array index, a
global-heap-backed variable-length attribute — is what the example is really
about, and that regime is what a generator must assert it produced.

The file is generated, not hand-built. `tools/h5policy-gencorpus` writes it to
`h5policy/tests/valid/objectstore_mapping_example.h5` and asserts the regime
above; `tools/check_objectstore_example.py` reads the spans, values, digests,
and byte counts below back out of this document and compares them against a
freshly written copy, so a writer change fails a check here rather than quietly
making this section fiction. The file is not tracked, and cannot be: its group
object headers carry wall-clock timestamps, so two runs a second apart differ.

### Import: the byte-ownership manifest

Every span belongs to exactly one class, and spans split at patch boundaries,
so an atom's preserved fragments never overlap its relocation fields:

| Span | Structure | Class | Status |
| --- | --- | --- | --- |
| `0..48` | Superblock v3: 8-byte offsets and lengths, EOA `6182`, root header at `48` | derived | — |
| `48..195` | Root group object header, version 2 | (classified per message, as below) | — |
| `195..342` | `/g` object header, version 2 | (classified per message) | — |
| `342..354` | `/g/d` object-header prefix, chunk 0 | derived | — |
| `354..390` | Dataspace message body: rank 2, `{4, 4}` | preserved | `exact` |
| `394..406` | Datatype message body: `H5T_STD_I32LE` | preserved | `exact` |
| `410..412` | Fill-value message body: incremental allocation, fill-if-set | preserved | `exact` |
| `416..428` | Filter-pipeline message body: deflate, one `cd_value` of `4` | preserved | `exact` |
| `432..442` | Layout message body: version 4, chunked, `{2, 2, 4}`, fixed-array | preserved | `relocation-normalized` |
| `442..450` | — its chunk-index address, value `610` | relocation | — |
| `454..472` | Attribute-info message body | preserved | `exact` |
| `476..518` | Attribute message body: name `note`, vlen UTF-8 string, scalar dataspace, and the 4-byte sequence length | preserved | `relocation-normalized` |
| `518..526` | — global-heap collection address, value `2048` | relocation, component 1 | — |
| `526..530` | — global-heap object index, value `1` | relocation, component 2 | — |
| `534..606` | NIL message: 72 bytes of reserved header space | padding | — |
| `606..610` | Object-header chunk checksum | derived | — |
| `610..638` | Fixed-array index header, `FAHD` | derived | — |
| `638..712` | Fixed-array data block, `FADB` | derived | — |
| `638..712` | — the per-chunk address, stored size, and filter mask inside it | semantic-index-field | — |
| `712..2048` | Allocation gap, all zero | padding | — |
| `2048..2080` | Global-heap collection header and object header, `GCOL`, 4096 bytes allocated | derived | — |
| `2080..2089` | — the heap object body, `"some note"` | preserved | `exact` |
| `2089..6144` | Remainder of the collection: packing and free tail | derived | — |
| `6144..6163` | Chunk `(0,0)` post-filter bytes, filter mask `0` | preserved | `exact` |
| `6163..6182` | Chunk `(2,0)` post-filter bytes, filter mask `0` | preserved | `exact` |

The `FADB` row appears twice on purpose, and it is the one place the "exactly
one class per span" rule needs care: the block's bytes are derived, while the
chunk addresses, stored sizes, and filter masks *encoded in* those bytes are
semantic. The manifest resolves this by classifying the span as derived and
recording the extracted fields against the chunk records, not by giving one
span two owners.

Four things in that table carry the whole design:

- The two unwritten chunks have no record anywhere, and that absence is
  content: they read as fill. An index builder that invents records for them
  changes what a reader sees.
- The layout message is preserved *and* patched. Its version, dimensions, chunk
  shape, and index-type byte survive byte-for-byte; ten of its eighteen bytes
  are copied and the last eight are rewritten.
- The attribute's heap ID is compound: an 8-byte collection address and a
  4-byte object index, at `518` and `526`, patched together or not at all.
- The chunk payloads are post-filter bytes and stay `exact`. The codec is never
  invoked, because nothing inside those chunks needs to change. Had the dataset
  held variable-length or reference data, the same chunks would have to be
  decoded, patched, and re-filtered, and would drop to `re-encoded`.

A manifest row carries more than the table shows. In full, the layout message's
two rows are:

```yaml
- span: [432, 442]
  owner: object-7/message/layout
  encoding_version: 4
  class: preserved
  preservation: relocation-normalized
  digest: sha256:...            # of these ten bytes
- span: [442, 450]
  owner: object-7/message/layout
  class: relocation
  kind: chunk_index_root
  source_value: 610             # provenance only; never an export input
  target: index-of(object-7)
```

### Import: records and keys

The dataset's record stores the message bodies as raw atoms, with every address
in a sidecar. The offsets are into the message body, not the file:

```yaml
oid: object-7                        # /g/d
record_class: object-header
census:                              # preservation-profile input
  header_version: 2
  layout_version: 4
  chunk_index: fixed-array
messages:
  - type: layout
    encoding_version: 4
    raw_bytes: 0402000301020204030a6202000000000000
    relocations:
      - offset: 10
        width: 8
        kind: chunk_index_root
        target: index-of(object-7)
    preservation: relocation-normalized
  - type: attribute
    encoding_version: 3
    raw_bytes: <54 bytes>
    relocations:
      - kind: global_heap_id
        target: heapvalue-9
        components:
          - offset: 42
            width: 8
            part: collection_address
          - offset: 50
            width: 4
            part: object_index
    preservation: relocation-normalized
chunks:
  - coordinates: [0, 0]
    filter_mask: 0
    payload: sha256:3b0e6a04066c1b16...
    source_stored_size: 19           # provenance; export recomputes it
  - coordinates: [2, 0]
    filter_mask: 0
    payload: sha256:9a8977eaeda1a5f9...
    source_stored_size: 19
```

Note what the raw layout bytes show: `04` version, `02` chunked, `00` flags,
`03` dimensionality, `01` encoded-length, `02 02 04` the dimensions, `03`
fixed-array, `0a` page bits — then `6202000000000000`, the little-endian `610`
that the sidecar owns. Ten bytes of content, eight bytes of placement, in one
message.

Importing the file writes:

```text
{c}/h/sha256/3b0e6a04...   chunk (0,0) payload, 19 bytes
{c}/h/sha256/9a8977ea...   chunk (2,0) payload, 19 bytes
{c}/h/sha256/052bad54...   heap value "some note", 9 bytes
{c}/o/object-1/1           root group record
{c}/o/object-4/1           /g record
{c}/o/object-7/1           /g/d record, above
{c}/map/0/1                OID -> record key, class, size, status, digest
{c}/man/0/1                the manifest shard, and match_p
{c}/att/1                  source digest, manifest digest, census, tool identities
{c}/root                   -> generation 1, profile canonical-v1, Merkle root
```

Nothing in that list corresponds to the superblock, either object-header
checksum, the `FAHD`, the `FADB`, the collection framing and its 4055 bytes of
packing, the NIL message, or the 1336-byte allocation gap.

Counting only the spans enumerated above, `/g/d`'s preserved content is 179
bytes: 141 of metadata and heap value, 38 of chunk payload. The file carrying
it is 6182 bytes. Do not read a compression ratio into that — this file is
dominated by one 4096-byte collection and a 1336-byte gap, both of which are
fixed costs that a real file amortizes over far more content. The number worth
taking from it is the 179, which is what has to round-trip byte-for-byte.

### Export: the trace

The eight steps of [Export and canonical
linearization](#export-and-canonical-linearization), against this snapshot:

1. **Validate.** Three payload digests resolve; the layout relocation names an
   index the builder will create; the attribute relocation names `heapvalue-9`;
   deflate is available at the pinned implementation and version.
2. **Choose index families.** The canonical profile's rule — fixed maximum
   dimensions, filtered, more than one chunk — selects fixed array. The census
   agrees, but the choice came from the profile; agreement is a coincidence to
   be verified, not an input.
3. **Order.** Root, then `/g`, then `/g/d`, by raw link-name bytes. Chunk
   records sort by coordinates: `(0,0)` before `(2,0)`.
4. **Build.** A fixed-array header and one data block sized for four elements,
   two of them undefined; a global-heap collection at the profile's collection
   size, holding one 9-byte object.
5. **Allocate.** Superblock, headers, index, heap, and chunk payloads in the
   profile's allocation order and alignment.
6. **Copy and patch.** The dataspace, datatype, fill-value, pipeline, and
   attribute-info bodies are copied verbatim. The layout body is copied and its
   final eight bytes set to the new `FAHD` address. The attribute body is
   copied and both heap-ID components set to the new collection address and
   object index.
7. **Recompute.** Both object-header checksums, the index and collection
   checksums, the superblock, and the EOA.
8. **Reject** on any unresolved relocation or status violation.

If the profile's allocation order happens to match the source writer's, some
addresses will coincide. Nothing requires it, and a test that depends on it is
testing the wrong property.

### `match_p` for this file

| Source atom | Atom in `H'` | Kind |
| --- | --- | --- |
| Dataspace, datatype, fill-value, pipeline, attribute-info bodies | The same bodies, relocated in the file | same carrier, `exact` |
| Layout body `432..450` | Layout body, index address rewritten | same carrier, `relocation-normalized` |
| Attribute body `476..530` | Attribute body, both heap-ID components rewritten | same carrier, `relocation-normalized` |
| Heap object body `2080..2089` | Heap object body, at a new collection address and possibly a new object index | same carrier, `exact` |
| Chunk payloads `6144..6182` | The same two payloads | same carrier, `exact` |
| NIL message `534..606`, gap `712..2048` | none | `dropped` (padding) |
| Superblock, checksums, `FAHD`, `FADB`, collection framing | none | `dropped` (derived) |
| — | Rebuilt superblock, index, collection, checksums | not in the image; `derived` |

This file has no re-homed atom: nothing moves carrier. Had the profile's
shared-message policy shared the datatype, the datatype body would map to
`re-homed(a')` — body bytes still `exact`, its object-header message framing
replaced by a shared-message stub and excluded from the comparison. That case
is why the rule exists, and it is worth a fixture precisely because this
example does not exercise it.

### Verification

For this fixture, the [verification contract](#verification-contract) reduces
to something concrete:

1. The manifest covers `0..6182` with no overlap and no unclassified span. The
   four-byte runs between the message bodies are derived message framing, the
   collection tail is derived packing, and the only padding is the NIL message
   and the allocation gap.
2. Every preserved atom compares equal outside its patch mask — including
   the ten non-address bytes of the layout message and the 42 non-heap-ID bytes
   of the attribute message, which are the two comparisons a naive
   whole-message diff would get wrong in opposite directions.
3. Three relocations resolve: the index address reaches the dataset's chunk
   index, and the two heap-ID components together reach the value `"some
   note"`.
4. The API-level graph compares equal: `/g`, `/g/d`, its datatype and
   dataspace, `d[0:2,0:2]` and `d[2:4,0:2]` as written, `d[0:2,2:4]` and
   `d[2:4,2:4]` as fill, and `note` reading back as `"some note"`.
5. The fixed array yields exactly two records, each reachable once, and the two
   unwritten chunks are still absent — a rebuilt index that reports four chunks
   fails here even though every byte it stored was correct.
6. `H'` opens under the newest available libhdf5, and the version is read off
   that build.
7. Re-import and re-export `H'`; the whole-file digest is identical.
8. Excluded throughout: every derived span, the NIL message, and the allocation
   gap.

## Keyspace

The keyspace separates immutable payload bytes, immutable semantic records, and
the mutable name of the current snapshot:

```text
{c}                                   one logical HDF5 container

{c}/root                              conditional commit pointer naming the current
                                      map generation, profile, and Merkle root

{c}/profile/{id}                      immutable export profile and compatibility bounds

{c}/map/{shard}/{gen}                 immutable COW shard: OID -> current record key,
                                      class, size, preservation status, and digest

{c}/o/{oid}/{gen}                     immutable normalized semantic record, raw atom,
                                      and relocation descriptors

{c}/h/{algo}/{digest}                 immutable content-addressed payload atom or large
                                      message body

{c}/ext/{oid}/{gen}                   external file, external link, and VDS target records

{c}/man/{shard}/{gen}                 immutable byte-ownership manifest shard for one
                                      ingested artifact, and the export's match_p

{c}/att/{gen}                         ingest provenance and optional signed snapshot root
```

Derived HDF5 nodes and heaps do not appear in the keyspace. A metadata-cache
eviction is therefore not automatically a key/value `PUT`; the persistence
grain is the normalized record or payload atom.

Content-addressed payload writes are idempotent. Metadata updates create new
record objects and copy-on-write map shards. No committed record is overwritten
in place.

### Requirements on the object store

The design is portable only to the extent that it names what it needs:

- **Immutable objects.** A committed key is never overwritten, and
  content-addressed payload writes are idempotent, so a retried `PUT` is
  harmless.
- **One conditional write.** Publication is a compare-and-swap on `{c}/root`
  alone — replace if the current generation is the one the committer read.
  Every other write creates a fresh key unconditionally. A store may expose
  this as a conditional `PUT`, as a precondition on a generation number, or
  through an external lock; the design needs exactly one such primitive and no
  transactions.
- **Read-after-write consistency for new keys**, so a reader that has resolved
  `{c}/root` can read everything that root names.
- **No dependency on listing.** Reachability comes from the root and the map
  shards, never from enumerating a prefix. Listing may be eventually consistent
  without affecting correctness; garbage collection is its only consumer and
  must tolerate a stale view.

It does not require multi-key transactions, an ordered keyspace, range queries,
compare-and-swap across more than one key, or object append.

### Scale and cost

The persistence grain is the record or the payload atom, which bounds key count
at roughly one key per object plus one per allocated chunk. That is
unremarkable at 10^4 objects and is the design's principal unsolved problem at
10^8 chunks, where per-chunk keys make ingest a small-object write storm and
export a wide fan-out read.

Deliberately unspecified, because the equivalence contract does not depend on
the answers and an implementation may choose them without changing an exported
byte:

- **Record packing.** Small records — links, attributes, chunk records — should
  be batched into larger immutable objects with an intra-object offset held in
  the map. Packing is byte-affecting for the *store*, not for the exported
  file, so it belongs to a store-side profile and not to the export profile.
- **Map-shard granularity**, and how a shard splits as a container grows.
- **Read amplification for export:** how many round trips a full export costs,
  and how much can be prefetched from the map alone.
- **Store limits.** Maximum object size, minimum efficient part size, and
  per-prefix request-rate limits all bear on the packing rule.

## Import

Import proceeds from the superblock and the reachable object graph:

1. Read the format widths, version bounds, driver information, and root object
   from the source artifact itself.
2. Traverse links and references in a deterministic order, retaining hard-link
   identity and detecting cycles. Objects reachable only through references are
   included. Unreachable allocated bytes are provenance, not logical content.
3. Parse every supported object-header message, raw-data layout, index, and heap.
   Extract semantic index records while classifying their physical container
   bytes as derived.
4. Store each non-indexing atom in its original encoding. Replace no bytes;
   describe address-, heap-, size-, and checksum-dependent fields in sidecars.
5. Store position-independent payloads by content digest. Normalize
   position-dependent VL and reference payloads as described below.
6. Emit and validate the byte-ownership manifest, including preservation status
   and a reason for every non-exact atom.
7. Publish the records, manifest shards, profile, and ingest provenance with one
   root commit.

The importer may use source addresses to detect aliasing and cycles while
reading, but source addresses are not persistent object identities.

### Import is a hostile-input parser

Import decodes untrusted metadata by definition: an artifact whose structure
could be trusted would not need a manifest. Every bound that applies to a
validating reader applies here, and then some, because import eagerly walks
structures that a reader would touch only lazily or not at all.

- A **certified** import requires a prior accept verdict from a bounded
  validator at a named validation profile, recorded with the ingest provenance.
  An import that cannot name one still produces a snapshot; it does not produce
  a certified one.
- Import must be bounded in the terms of [bounded raw
  decode](What%20is%20bounded%20raw%20decode.md): bound every extent before
  mapping it, bound every count before multiplying by it, cap recursion depth,
  and size no allocation from an unvalidated field.
- Overlap detection is not an optimization. The manifest's "exactly one class
  per span" property is what turns aliasing — two structures claiming one span
  — into a rejection rather than a silent last-writer-wins, and aliasing is a
  live corruption class rather than a theoretical one.
- Rejection is the default for anything unmodeled. `unsupported` is a status
  the design already carries; reaching for `pass-through` to get past a parse
  failure converts an unparsed structure into an unfalsifiable claim.

## Export and canonical linearization

Export is a deterministic linker and index builder:

1. Validate the snapshot graph, relocation targets, profile, and required
   codecs before allocating output.
2. Choose each index family according to the selected profile.
3. Order objects and semantic records using the profile's canonical traversal
   and tie-breaking rules. Storage OID values must not affect this order.
4. Build heap and index structures from sorted semantic records, using pinned
   node capacities, split rules, heap growth parameters, and padding values.
5. Assign offsets in the profile's allocation order and with its alignment
   rules.
6. Copy preserved atom bytes and patch only declared relocation and derived
   fields.
7. Recompute container checksums, free-space state, superblock fields, and EOA.
8. Reject the export if any relocation remains unresolved or any atom's
   preservation status violates the requested profile.

Canonical traversal must be specified independently of incidental OID values.
A root-first graph traversal ordered by raw link-name bytes is sufficient for
named objects; references are visited in containing-object and logical element
order. The profile must define deterministic tie breakers for reference-only
and otherwise anonymous objects.

## Export profiles

An **export profile** is the complete set of byte-affecting choices that export
consumes. Nothing that affects the output bytes may come from an ambient
library default; that is invariant 6. A profile is immutable and is named by
the snapshot root, so a stored file always records which contract produced it.

Index provenance and index policy are distinct:

- A **preservation profile** rebuilds the original index family and retains
  source encoding widths and versions wherever the format permits.
- A **canonical profile** applies a pinned index-selection policy and canonical
  container versions. It still preserves atom bytes except where the profile
  explicitly classifies a field or atom as re-encoded.

At minimum, a profile pins:

- size of offsets and size of lengths;
- superblock, object-header, message, heap, and index version policy;
- dataset chunk-index selection rules;
- group and attribute compact/dense thresholds;
- B-tree node sizes, split and merge policy, and record ordering;
- object-header message ordering and chunk assignment, which are byte-affecting
  and have no semantic anchor in the format;
- file-space strategy, free-space threshold, and page size. The free-space
  *sections* are derived, but the strategy and page size are creation
  properties recorded in the superblock extension, and paged aggregation is the
  single largest determinant of read performance for the exported file;
- the shard boundary rule and threshold for contiguous payloads (see [Other
  boundary cases](#other-boundary-cases)), without which two conforming
  exporters disagree;
- heap growth, collection sizing, alignment, allocation order, and padding;
- user-block and driver-info handling;
- filter identifiers, parameters, implementation identity, and version;
- external-target policy and minimum/maximum reader bounds.

Changing a profile creates a different serialization contract. A claim that the
same graph yields the same file bytes is meaningful only when the profile is
also the same.

## Position-dependent payloads

### Variable-length data

VL data embeds global-heap IDs in otherwise raw dataset storage. Import stores a
normalized fixed part plus the semantic heap values:

- The fixed element array retains its original encoding except that each global
  heap ID is a declared compound relocation.
- Heap element byte strings are stored in logical element scan order. Nested VL
  values recurse according to the stored datatype encoding.
- Individually large values may be separate content-addressed payloads without
  changing their logical order.
- Export builds global-heap collections, assigns indexes, and patches every
  compound heap-ID relocation.

The heap collection layout and object indexes are derived. The unpadded heap
object content is semantic and is preserved according to its own relocation
status.

### References

Legacy object references, legacy region references, revised references, and
reference blobs are relocatable atoms. Import resolves each reference to an OID
or external target while retaining the original non-relocation bytes. Region
selections and attribute names are semantic content. Export reconstructs any
required heap blobs and encodes the new address, token, heap address, and heap
index fields.

Null references remain null and do not acquire targets.

### Filters

An address-free filtered chunk can be stored and reproduced as the exact
post-filter byte string; export need not invoke the codec. Its filter mask is a
first-class chunk-record field.

A filtered chunk containing VL or reference relocations must be decoded,
patched, and re-filtered. Such an atom is `re-encoded`, not `exact` or merely
`relocation-normalized`. Canonical output requires the profile to pin the filter
implementation and version as well as its identifier and parameters.
The exporter recomputes the chunk's stored size from the re-filtered bytes.

If a required filter is unavailable, lossy, nondeterministic, or cannot be
safely decoded, certified export is refused. The design never treats successful
opaque copying as sufficient when an embedded relocation must change.

## Other boundary cases

| Case | Handling |
| --- | --- |
| Compact data | Treat the inline payload as an atom inside the layout message; patch nested VL or reference fields as needed. |
| Contiguous data | Store one exact extent or checksum-addressed shards above a profile threshold; regenerate only its layout address and extent placement. |
| Object-header continuations | Preserve semantic messages and their ordering fields; regenerate continuation blocks, NIL space, lengths, and checksums. |
| Dense links and attributes | Preserve logical records and raw values; regenerate fractal heaps, heap IDs, and B-tree indexes. |
| Shared object-header messages | Preserve dereferenced message bodies; regenerate sharing decisions and SOHM indexes under the profile. |
| Symbol-table scratch pads | Treat cached addresses as derived; preserve the link record they accelerate. |
| VDS mappings and external links | Preserve target strings, selections, and flags; keep foreign content outside the equivalence claim. |
| External file lists | Preserve the list and offsets as metadata; external raw bytes are not part of the container snapshot. |
| User block | Preserve exact bytes by default; omission is an explicit profile choice that prevents whole-artifact relocation equivalence. |
| Driver information | Preserve only for a compatible driver profile; otherwise retain as provenance or reject. Multi-file physical layouts require a separate profile. |
| Unknown object-header message | Certified relocation equivalence requires proof that the payload is address-free. Otherwise reject, or retain as `pass-through` without a semantic claim. The message-header flags are part of the decision, not decoration: *fail-if-unknown* (always, and when open for write) determines whether the export is readable at all, *shareable* interacts with regenerated sharing decisions, and the *modified-by-unaware-software* bit records that a writer rewrote the object. An exporter that rebuilds the header must decide, per profile, whether it is such a writer and set that bit accordingly. |
| Metadata cache image | Treat as derived and omit or regenerate; it is never authoritative content. |

## Commit model

The base profile permits any number of uncoordinated payload producers and one
snapshot committer. Producers write immutable content-addressed payloads and
submit semantic records such as `(coordinates, digest, stored size, filter
mask)`. The committer writes new normalized records and map shards, then
conditionally replaces `{c}/root`.

Readers pin one root and observe a consistent snapshot. Objects written but not
reachable from a committed root are invisible and eligible for garbage
collection. Retained or attested roots pin everything reachable from them.

True concurrent mutation of the same logical HDF5 graph requires merge
semantics that HDF5 does not define. It is outside the base equivalence contract
and must be a separately named extension profile.

## Attestation

The current OID map and normalized records form a Merkle graph. A record digest
covers normalized atom bytes, relocation descriptors, semantic index fields,
and referenced payload digests. Map shards hash into the committed root, which
may be signed and retained under `{c}/att/{gen}`.

The ingest record separately retains the source file digest, byte-ownership
manifest digest, format census, and tool/build identities. It attests the input
artifact without pretending that its allocation history is content.

The canonical exported file has its own whole-file digest. That digest attests
`E_p(K)`, including profile `p`; it is not the digest of the ingested file.

## Relationship to this repository

Nothing described here is implemented, but most of it has a starting point in
this repository, and the design is better read as an extension of that work
than as a greenfield proposal.

| Design element | Existing starting point |
| --- | --- |
| The format model that fixes atom boundaries, field widths, and version rules | `pickles/*.pk`, the executable structure definitions. `docs/spec/index.yml` records which upstream specification sections are `covered`, `partial`, or `not-covered`; the `not-covered` set is the initial `unsupported` set. |
| Byte-ownership manifest | `h5policy/pickles/h5_walk.pk` already keeps a half-open interval registry over decoded metadata and raw-data extents, and rejects self, alias, and partial overlap. The manifest is an emitter over that bookkeeping plus a gap analysis, not a second parser. |
| "No unexplained overlaps", verification item 1 | The same registry, reported today as `H5_CORRUPT_RAW_DATA_OVERLAPS_DATA` and `H5_CORRUPT_RAW_DATA_OVERLAPS_METADATA`. |
| Bounded import | The `h5policy` validation profiles and finding classes, and [bounded raw decode](What%20is%20bounded%20raw%20decode.md). |
| Verification corpus | `tools/h5policy-gencorpus` already generates the regression corpus under `h5policy/tests`, already follows the "assert that the intended structural regime was produced" rule, and already covers most of the storage regimes listed below. |
| Clause 5, the export's own validity | Run `H'` back through the validator at the profile's reader bounds. A certified export that its own validator rejects is a contradiction, and the cheapest one to test. |
| No aliased extents in the export | Two datasets sharing one content-addressed payload must not share an extent in `H'`. That aliasing is already a finding, so the check exists before the exporter does. |

Two consequences are worth stating plainly. The first implementation milestone
is not an exporter. And the manifest is useful on its own, as a forensic
artifact for the CVE workflow, whether or not the exporter is ever built.

## Verification contract

An implementation must make the design claims measurable with fixtures that
cover legacy and current format versions and every supported storage regime.
For each fixture, verification must:

1. Prove that the byte-ownership manifest covers the input without unexplained
   overlaps or gaps.
2. Export and compare every preserved atom outside its declared patch mask.
3. Resolve each original and exported relocation and compare its logical target.
4. Compare the reachable graphs through both a structural walker and the public
   HDF5 API, including hard-link aliasing, creation order, dataset values, VL
   nesting, and references.
5. Exercise every regenerated index family and verify all records are reachable
   exactly once through the owning index.
6. Open and exercise the export with the newest available libhdf5 build, reading
   the version from that build's artifact and recording it with the result.
7. Re-import and re-export the canonical file and require an identical
   whole-file digest.
8. Check negative fixtures for unknown messages, missing filters, unresolved
   external targets, corrupt indexes, overlapping extents, and unsupported
   driver layouts; none may receive a certified equivalence verdict.

The corpus must include compact, contiguous, and every chunk-index regime;
compact and dense groups and attributes; local, global, fractal, and shared
message heaps; filtered and unfiltered data; nested VL; legacy and revised
references; nonzero base addresses; user blocks; object-header continuations;
and reference-only objects. Generators must assert that the intended structural
regime was actually produced.

## Staged implementation

Each stage produces something checkable on its own, and none of them requires
the next one to exist.

1. **Manifest only.** Emit a byte-ownership manifest from the existing walk for
   every corpus fixture. Success is total span coverage with no overlap and an
   explanation for every gap. This measures how much of the corpus is
   classifiable today, which nothing currently reports.
2. **Classification review.** For each class, record which structures reach it
   and why. The `unsupported` set that falls out is the honest scope statement
   for every stage after it.
3. **Import to a local store.** Records, payloads, and relocation sidecars; no
   export. Verified by re-deriving the manifest from the store and comparing it
   with the one emitted in stage 1.
4. **Export, one regime.** One profile, one index family, no filters and no
   variable-length data — enough to exercise allocation, relocation patching,
   and a single index builder end to end.
5. **Export, canonical profile.** The remaining index families, heaps,
   references, and filters, then the fixed-point and idempotence checks.
6. **Preservation profile.** The census-driven variant and its conditional
   determinism claim, which only becomes meaningful once canonical determinism
   holds.

## Open questions

None of these is resolved by asserting the contract more firmly:

- **Small-record packing and map-shard granularity**, per [Scale and
  cost](#scale-and-cost). The design is untested above roughly 10^6 keys.
- **Garbage-collection safety.** Unreachable objects are collectable, but the
  design does not say how collection races a producer that has written payloads
  and not yet submitted records. A grace period keyed on ingest generation is
  the obvious answer and is not specified.
- **Reading without exporting.** If the store can serve reads directly, the
  export becomes an archival operation rather than the only access path — which
  changes which structures are worth deriving eagerly. Deliberately out of
  scope here, but it is the question that decides whether this is a storage
  format or a transport format.
- **Partial and incremental export.** Exporting one group, or re-exporting only
  what changed since a prior root, is undefined; the fixed-point property is
  stated for whole files.
- **Filter implementation identity.** Pinning implementation and version is
  necessary and may not be sufficient, because a codec's output can depend on
  build flags and on runtime strategy selection. Whether a canonical profile
  can pin a codec tightly enough to be reproducible across platforms is an
  empirical question. The honest fallback is already in the contract: classify
  a chunk that must be re-filtered as `re-encoded` and exclude it from the byte
  claim.
- **Whether the exact-atom bar is the right bar for every deployment.** It is
  what makes the design auditable and it is expensive. A profile claiming only
  logical equivalence for raw data may be the more useful default for some
  users; if so it must be a named profile, never an undocumented relaxation of
  this one.

## Non-goals

- Reproducing the input file's original offsets, allocation gaps, free-space
  history, B-tree split history, heap packing history, or cache image.
- Claiming byte identity between the input and first export.
- Assigning logical meaning to unsupported opaque records.
- Defining distributed merge semantics for concurrent HDF5 mutations.
- Attesting the contents of external files merely because their names appear in
  the container.
- Serving HDF5 reads directly from the store. The specified access path is
  export; a native reader over the keyspace is a possible extension and has no
  contract here.
- Partial, incremental, or subsetting export. The contract is stated for whole
  files.
