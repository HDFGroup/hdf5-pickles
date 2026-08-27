# Mapping HDF5 Binary Primitives onto an Object Store

> **Status: design proposal.** This repository does not currently implement the
> importer, exporter, or object-store representation described below. The
> document defines a prospective preservation and reconstruction contract.

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

Let `I` be import, `E_p` be export under profile `p`, and `H` be an input HDF5
file accepted by that profile:

```text
K  = I(H)
H' = E_p(K)

H ≈p H'
```

`H ≈p H'` means that `H` and `H'` are **relocation-normalized byte
equivalent** under profile `p`:

1. Every preserved atom has identical bytes outside its declared relocation,
   other derived, and checksum fields.
2. Every relocated field in `H'` resolves to the same logical object, heap
   value, raw-data extent, or external target as it did in `H`.
3. The reachable object graphs are isomorphic: hard-link identity, link and
   attribute values, datatypes, dataspaces, dataset values, creation-order
   values, references, and other modeled content agree.
4. Every regenerated index is complete, internally consistent, and reachable
   from its owner.
5. `H'` is valid for the HDF5 format and reader bounds named by `p`.
6. Every reachable non-indexing atom is either `exact` or
   `relocation-normalized`. A `re-encoded` or `pass-through` atom limits the
   result to logical equivalence with explicit exclusions; it does not receive
   the whole-file `H ≈p H'` verdict. An `unsupported` atom prevents certified
   export.

For a canonical profile, the first export must also be a fixed point:

```text
H' = E_p(I(H))
E_p(I(H')) = H'
```

The second equality is byte identity. Storage-local object IDs and ingest
provenance may differ after re-import, but they must not affect the canonical
serialization.

This separates four claims that must not be conflated:

- **HDF5 format compatibility:** an ordinary HDF5 reader can read the export.
- **Logical equivalence:** the reachable HDF5 object graphs have the same
  modeled meaning.
- **Relocation-normalized byte equivalence:** non-indexing atom bytes are
  preserved except at declared patch sites.
- **Canonical determinism:** the same modeled graph and export profile produce
  the same exported byte string.

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
preservation status, and digest. It is the basis of the round-trip comparator.
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
  the encoded size from the output payload.
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

{c}/att/{gen}                         ingest provenance and optional signed snapshot root
```

Derived HDF5 nodes and heaps do not appear in the keyspace. A metadata-cache
eviction is therefore not automatically a key/value `PUT`; the persistence
grain is the normalized record or payload atom.

Content-addressed payload writes are idempotent. Metadata updates create new
record objects and copy-on-write map shards. No committed record is overwritten
in place.

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

`h5repack` is an engineering precedent for rebuilding HDF5 container
structures from decoded records. It is not proof of byte preservation or
canonical determinism; those properties come from this export contract and its
verification.

## Export profiles

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
| Unknown object-header message | Certified relocation equivalence requires proof that the payload is address-free. Otherwise reject, or retain as `pass-through` without a semantic claim. |
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

## Non-goals

- Reproducing the input file's original offsets, allocation gaps, free-space
  history, B-tree split history, heap packing history, or cache image.
- Claiming byte identity between the input and first export.
- Assigning logical meaning to unsupported opaque records.
- Defining distributed merge semantics for concurrent HDF5 mutations.
- Attesting the contents of external files merely because their names appear in
  the container.

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
