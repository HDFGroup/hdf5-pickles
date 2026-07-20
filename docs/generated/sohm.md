# III.I. Disk Format: Level 1I - Shared Object Header Message Table and Lists

When several objects would carry identical header messages (a common
datatype, dataspace, fill value, filter pipeline, or attribute), HDF5 can
store one shared copy and have each object reference it. The Shared
Object Header Message (SOHM) machinery indexes those shared messages.

A file has one master table (signature 'SMTB') holding one entry per
index. Each index either stores its records as an unsorted list
(signature 'SMLI') or in a version 2 B-tree, and names the fractal heap
that holds the shared message bodies. A record in a list (`sohm_entry`)
identifies a message by a hash and a location: either in the fractal heap
(`sohm_heap_body`: reference count plus a fractal-heap ID) or in an
object header (`sohm_oh_body`: message type, creation index, and the
object header address).

The number of indexes is not stored in the table itself; call
`set_sohm_num_indexes(N)` (from h5debug or the superblock extension)
before mapping `sohm_table_raw`. Each list entry occupies a fixed
`H5SM_SOHM_ENTRY_SIZE = 5 + MAX(12, 4 + sizeof_offsets)` bytes, so
entries are padded to that width.

All fields are stored in little-endian byte order.

**Layout: Shared Message Master Table**

<table class="format-layout">
  <thead><tr><th>byte</th><th>byte</th><th>byte</th><th>byte</th></tr></thead>
  <tbody>
    <tr><td colspan="4">Signature</td></tr>
    <tr><td colspan="4">Index Entries (variable count)</td></tr>
    <tr><td colspan="4">Checksum</td></tr>
  </tbody>
</table>

**Layout: Shared Message Index Entry**

<table class="format-layout">
  <thead><tr><th>byte</th><th>byte</th><th>byte</th><th>byte</th></tr></thead>
  <tbody>
    <tr><td>Version</td><td>Index Type</td><td colspan="2">Message Types</td></tr>
    <tr><td colspan="4">Minimum Message Size</td></tr>
    <tr><td colspan="2">List Maximum</td><td colspan="2">B-tree Minimum</td></tr>
    <tr><td colspan="2">Number of Messages</td><td colspan="2">Index Address<sup>O</sup></td></tr>
    <tr><td colspan="4">Index Address (continued)<sup>O</sup></td></tr>
    <tr><td colspan="4">Fractal Heap Address<sup>O</sup></td></tr>
  </tbody>
</table>

Rows containing variable-width fields are schematic. `O` is the size of offsets.

## `sohm_index_entry`

One index descriptor within the master table. Describes a single shared-message index: which message types it covers, its list-to-B-tree conversion thresholds, its current message count, and the addresses of its index structure and backing fractal heap.

| Field | Description |
|-------|-------------|
| `version` | Index entry version. Must be 0. |
| `index_type` | Index storage: 0 = unsorted list ('SMLI'); 1 = version 2 B-tree. |
| `mesg_types` | Bit mask of the object header message types this index shares. Bit position equals the message type ID (e.g. bit 3 = Datatype, bit 12 = Attribute). |
| `min_mesg_size` | Minimum message size, in bytes, eligible to be shared in this index. |
| `list_max` | Maximum number of messages kept as a list; above this the index converts to a B-tree. |
| `btree_min` | Minimum number of messages for a B-tree; below this the index converts back to a list. |
| `num_messages` | Number of shared messages currently stored in this index. |
| `index_addr_raw` | File address of the index's list ('SMLI') or B-tree root (`sizeof_offsets` bytes). |
| `heap_addr_raw` | File address of the fractal heap holding the shared message bodies for this index (`sizeof_offsets` bytes). |


## `sohm_table_raw`

Shared Object Header Message master table (signature 'SMTB'). Holds `num_indexes` index descriptors followed by a checksum. Call `set_sohm_num_indexes(N)` before mapping so the `indexes` array is sized.

| Field | Description |
|-------|-------------|
| `signature` | 4-byte signature: 'S' 'M' 'T' 'B'. Must match exactly. |
| `indexes` | Array of `sohm_index_entry` descriptors, one per shared-message index (`global_sohm_num_indexes` entries). |
| `chksum` | Jenkins lookup3 checksum over the table. |


## `sohm_heap_body`

Body of a list entry whose message is stored in the fractal heap (`H5SM_IN_HEAP`, location 0).

| Field | Description |
|-------|-------------|
| `ref_count` | Number of objects sharing this message. |
| `fheap_id` | 8-byte fractal-heap ID locating the message body in the heap. |


## `sohm_oh_body`

Body of a list entry whose message lives in an object header (`H5SM_IN_OH`, location 1).

| Field | Description |
|-------|-------------|
| `reserved` | Reserved. Must be zero (1 byte). |
| `msg_type_id` | Object header message type ID of the shared message. |
| `creat_idx` | Creation index of the message within its object header. |
| `oh_addr_raw` | File address of the object header holding the message (`sizeof_offsets` bytes). |


## `sohm_entry`

One record in a Shared Message Record List. A location byte and a hash select and identify the message; a union then carries the location-specific body. Each entry is padded to `H5SM_SOHM_ENTRY_SIZE` bytes.

| Field | Description |
|-------|-------------|
| `location` | Where the message is stored: 0 = fractal heap (`sohm_heap_body`), 1 = object header (`sohm_oh_body`). |
| `hash` | Jenkins lookup3 hash of the shared message, used as the list key. |
| `u` | Location-specific body; see the variants below. |
| `pad` | Zero padding that fills the entry out to the fixed `H5SM_SOHM_ENTRY_SIZE` width. |

### `heap`

`sohm_heap_body` — present when `location == 0`.

### `oh`

`sohm_oh_body` — present when `location == 1`.

### `unknown`

12 raw bytes for any unrecognized location value.


## `sohm_list_raw`

Shared Message Record List (signature 'SMLI'). Holds exactly `num_messages` `sohm_entry` records followed by a checksum. Call `set_sohm_list(idx)` before mapping so the entry count and width are known. Trailing on-disk padding up to the list's maximum capacity is not mapped.

| Field | Description |
|-------|-------------|
| `signature` | 4-byte signature: 'S' 'M' 'L' 'I'. Must match exactly. |
| `entries` | Array of `sohm_entry` records, one per shared message in this index (`global_sohm_num_mesg` entries). |
| `chksum` | Jenkins lookup3 checksum over the list, immediately after the last entry. |
