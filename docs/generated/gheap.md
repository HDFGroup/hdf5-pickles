# III.E. Disk Format: Level 1E - Global Heap

Global heaps store variable-length data that is referenced indirectly
from object header messages, including variable-length datatype data
and references. A file may contain multiple global heap collections;
each collection is self-contained and begins with a `GCOL` header.

A global heap collection contains a sequence of object records. Each
nonzero object index identifies one stored data object, while object
index 0 is the free-space sentinel. The collection size in the header
bounds the object sequence, and object records and payloads are padded
to 8-byte alignment.

Global Heap IDs embedded elsewhere in the file identify an object by
combining the file address of its collection with the object's index
inside that collection.

## `gheap_id`

Global Heap Object Identifier embedded in other HDF5 metadata. It points to one object inside a specific global heap collection.

| Field | Description |
|-------|-------------|
| `collection_addr_raw` | File address of the Global Heap Collection (`sizeof_offsets` bytes). |
| `obj_idx_raw` | Object index within the collection, stored as a 4-byte little-endian integer. Valid references use a nonzero index. |


## `gheap_hdr`

Global Heap Collection header (signature 'GCOL'). It records the total byte span of this collection before the object records that follow in file order.

| Field | Description |
|-------|-------------|
| `signature` | 4-byte signature: 'G' 'C' 'O' 'L'. Must match exactly. |
| `version` | Collection header format version. Must be 1. |
| `reserved` | Reserved three-byte field. Must be zero. |
| `coll_size_raw` | Total size in bytes of this global heap collection, including the header, object records, object payloads, and padding (`sizeof_lengths` bytes). |


## `gheap_obj_hdr`

Per-object header inside a Global Heap Collection. Nonzero object indexes are followed by `data_size_raw` bytes of payload padded to 8-byte alignment. Object index 0 marks free space.

| Field | Description |
|-------|-------------|
| `idx_raw` | Object index, stored as a 2-byte little-endian integer. Index 0 is the free-space sentinel; nonzero indexes identify stored heap objects. |
| `ref_cnt_raw` | Reference count for this heap object, stored as a 2-byte little-endian integer. |
| `reserved` | Reserved four-byte field. Must be zero. |
| `data_size_raw` | For nonzero object indexes, the byte length of the following object data. For object index 0, the total free-space span measured from the start of this object header (`sizeof_lengths` bytes). |


