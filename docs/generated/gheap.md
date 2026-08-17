# III.E. Disk Format: Level 1E - Global Heap

<a id="subsec_fmt4_infra_globalheap"></a>

Upstream: [HDF5 File Format Specification 4.0, section III.E](https://support.hdfgroup.org/documentation/hdf5/latest/_f_m_t4.html#subsec_fmt4_infra_globalheap) · Coverage: **Covered**

The global heap stores variable-length data that object headers
reference indirectly: variable-length strings, variable-length
datatypes, and object and region references. Data is grouped into
self-contained collections (signature 'GCOL'); a file may hold many
collections, and a single collection may hold many heap objects.

A collection begins with a fixed header giving the collection's total
byte size, followed by heap objects in file order. Each object has an
8-byte-aligned header (index, reference count, data size) and a
zero-padded data region. Object index 0 is the free-space sentinel: its
`data_size` records the total span of the trailing free region including
the sentinel header itself. Both the collection header and each object
header occupy `align8(8 + sizeof_lengths)` bytes on disk.

A global heap object is referenced from elsewhere by a Global Heap ID
(`gheap_id`): the collection's file address plus a 1-based object index.
Lookup rejects index 0, which is free space rather than reference data, and
reports the selected object's exact unpadded data size so reference decoders
can verify a separately encoded payload length before reading it.

All fields are stored in little-endian byte order.

## Global Heap Collection

Pickle type: `gheap_hdr`.

Global heap collection header (signature 'GCOL'). Introduces a collection and gives its total on-disk size; the heap objects follow immediately, 8-byte aligned.

**Layout: Global Heap Collection**

<table class="format-layout">
  <thead><tr><th>byte</th><th>byte</th><th>byte</th><th>byte</th></tr></thead>
  <tbody>
    <tr><td colspan="4">Signature</td></tr>
    <tr><td>Version</td><td colspan="3">Reserved</td></tr>
    <tr><td colspan="4">Collection Size<sup>L</sup></td></tr>
    <tr><td colspan="4">Global Heap Objects (variable size)</td></tr>
  </tbody>
</table>

`L` is the size of lengths.

**Fields: Global Heap Collection**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Signature | `signature` | 4-byte signature: 'G' 'C' 'O' 'L'. Must match exactly. |
| Version | `version` | Collection version. Must be 1. |
| Reserved | `reserved` | Reserved. Must be zero (3 bytes). |
| Coll Size Raw | `coll_size_raw` | Total byte count of this collection, including the header and all objects (`sizeof_lengths` bytes). |


## Global Heap Object

Pickle type: `gheap_obj_hdr`.

Per-object header within a collection. Followed by `data_size` bytes of object data (zero-padded to an 8-byte boundary) for objects with a nonzero index.

**Fields: Global Heap Object**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Index Raw | `idx_raw` | Object index (2-byte unsigned integer). Index 0 marks the free-space sentinel that terminates the used objects. |
| Ref Cnt Raw | `ref_cnt_raw` | Reference count for this object (2-byte unsigned integer). |
| Reserved | `reserved` | Reserved. Must be zero (4 bytes). |
| Data Size Raw | `data_size_raw` | For a nonzero index, the byte count of the object's data field. For the index-0 sentinel, the total span of the free region including this object header (`sizeof_lengths` bytes). |


## Global Heap ID

Pickle type: `gheap_id`.

Global Heap ID. Embedded in object header messages (for example a variable-length datatype) to reference one object inside a specific global heap collection. Total size is `sizeof_offsets + 4` bytes.

**Fields: Global Heap ID**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Collection Address Raw | `collection_addr_raw` | File address of the global heap collection ('GCOL') holding the referenced object (`sizeof_offsets` bytes). |
| Object Index Raw | `obj_idx_raw` | 1-based index of the referenced object within the collection (4-byte unsigned integer). |
