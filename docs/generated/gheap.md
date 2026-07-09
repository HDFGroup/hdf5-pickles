# III.E. Disk Format: Level 1E - Global Heaps

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

All fields are stored in little-endian byte order.

## `gheap_id`

Global Heap ID. Embedded in object header messages (for example a variable-length datatype) to reference one object inside a specific global heap collection. Total size is `sizeof_offsets + 4` bytes.

| Field | Description |
|-------|-------------|
| `collection_addr_raw` | File address of the global heap collection ('GCOL') holding the referenced object (`sizeof_offsets` bytes). |
| `obj_idx_raw` | 1-based index of the referenced object within the collection (4-byte unsigned integer). |


## `gheap_hdr`

Global heap collection header (signature 'GCOL'). Introduces a collection and gives its total on-disk size; the heap objects follow immediately, 8-byte aligned.

| Field | Description |
|-------|-------------|
| `signature` | 4-byte signature: 'G' 'C' 'O' 'L'. Must match exactly. |
| `version` | Collection version. Must be 1. |
| `reserved` | Reserved. Must be zero (3 bytes). |
| `coll_size_raw` | Total byte count of this collection, including the header and all objects (`sizeof_lengths` bytes). |


## `gheap_obj_hdr`

Per-object header within a collection. Followed by `data_size` bytes of object data (zero-padded to an 8-byte boundary) for objects with a nonzero index.

| Field | Description |
|-------|-------------|
| `idx_raw` | Object index (2-byte unsigned integer). Index 0 marks the free-space sentinel that terminates the used objects. |
| `ref_cnt_raw` | Reference count for this object (2-byte unsigned integer). |
| `reserved` | Reserved. Must be zero (4 bytes). |
| `data_size_raw` | For a nonzero index, the byte count of the object's data field. For the index-0 sentinel, the total span of the free region including this object header (`sizeof_lengths` bytes). |


