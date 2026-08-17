# III.A.2. Disk Format: Level 1A2 - Version 2 B-trees

<a id="subsubsec_fmt4_infra_btrees_v2"></a>

Upstream: [HDF5 File Format Specification 4.0, section III.A.2, VII.E](https://support.hdfgroup.org/documentation/hdf5/latest/_f_m_t4.html#subsubsec_fmt4_infra_btrees_v2) · Coverage: **Covered**

Version 2 B-trees are a self-describing, checksummed replacement for
the version 1 B-tree used for new indexing needs introduced in HDF5
1.8. Three on-disk structures are defined:

- **Header** (signature 'BTHD') — one per B-tree; records the record
  type, node geometry, depth, and root node address.
- **Leaf node** (signature 'BTLF') — stores up to the configured
  maximum records with no child pointers.
- **Internal node** (signature 'BTIN') — stores records interleaved
  with child pointers, each carrying the record count of the child
  node and, for nodes deeper than level 1, the total record count of
  the child's subtree.

Eleven record types are defined, covering: huge-object tracking
(types 1–4), indexed-group link names (types 5–6), shared object
header messages (type 7), indexed-attribute names and creation order
(types 8–9), and non-filtered and filtered dataset chunk addresses
(types 10–11).

The global variables `global_bt2_*` must be set correctly before
mapping any node. `print_v2_btree(addr#B)` handles this automatically
by reading the header first.

The decoder verifies the lookup3 metadata checksum on each header,
leaf, and internal node before accepting its fields.

## Version 2 B-tree Header

Pickle type: `bt2_hdr`.

Version 2 B-tree header (signature 'BTHD'). Describes the geometry of the entire B-tree. Mapping this struct sets the global parameters `global_bt2_type`, `global_bt2_record_size`, `global_bt2_node_size`, and `global_bt2_depth` via constraint side-effects, so subsequent node mappings require no additional setter calls.

**Layout: Version 2 B-tree Header**

<table class="format-layout">
  <thead><tr><th>byte</th><th>byte</th><th>byte</th><th>byte</th></tr></thead>
  <tbody>
    <tr><td colspan="4">Signature</td></tr>
    <tr><td>Version</td><td>Record Type</td><td colspan="2">Node Size</td></tr>
    <tr><td colspan="2">Node Size (continued)</td><td colspan="2">Record Size</td></tr>
    <tr><td colspan="2">Depth</td><td>Split Percent</td><td>Merge Percent</td></tr>
    <tr><td colspan="4">Root Node Address<sup>O</sup></td></tr>
    <tr><td colspan="2">Root Record Count</td><td colspan="2">Total Record Count<sup>L</sup></td></tr>
    <tr><td colspan="4">Total Record Count (continued)<sup>L</sup></td></tr>
    <tr><td colspan="4">Checksum</td></tr>
  </tbody>
</table>

Rows containing variable-width fields are schematic. `O` is the size of offsets; `L` is the size of lengths.

**Fields: Version 2 B-tree Header**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Signature | `signature` | 4-byte signature: 'B' 'T' 'H' 'D'. Must match exactly. |
| Version | `version` | Header format version. Must be 0. |
| Record Type | `record_type` | Record type identifier (1–11). Determines which `bt2_rec_type*` struct to use for records. |
| Node Size | `node_size` | Size in bytes of each B-tree node (leaf or internal). All nodes have the same size. |
| Record Size | `record_size` | Size in bytes of each record within a node. |
| Depth | `depth` | Tree depth. 0 means the root is a leaf node; > 0 means the root is an internal node. |
| Split Percent | `split_percent` | Node occupancy percentage above which a node is split (typically 100). |
| Merge Percent | `merge_percent` | Node occupancy percentage below which two sibling nodes are merged (typically 40). |
| Root Address Raw | `root_addr_raw` | File address of the root node (`sizeof_offsets` bytes). |
| Num Root Records | `num_root_records` | Number of records currently stored in the root node. |
| Total Number of Records Raw | `total_nrec_raw` | Total number of records across all nodes in the B-tree (`sizeof_lengths` bytes). |
| Chksum | `chksum` | Jenkins lookup3 checksum of all preceding header bytes. |


## Version 2 B-tree Internal Node

Pickle type: `bt2_internal`.

Version 2 B-tree internal node (signature 'BTIN'). Stores records interleaved with `global_bt2_nrec + 1` child pointers. The child- pointer layout depends on the node's depth: depth-1 nodes use `child_ptr_d1`; deeper nodes use `child_ptr_dn`. Before mapping, set `global_bt2_depth` and `global_bt2_nrec` to the values for this node.

**Fields: Version 2 B-tree Internal Node**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Signature | `signature` | 4-byte signature: 'B' 'T' 'I' 'N'. Must match exactly. |
| Version | `version` | Internal node format version. Must be 0. |
| Record Type | `record_type` | Record type identifier (mirrors `bt2_hdr.record_type`). |
| Records | `records` | Array of `global_bt2_nrec` raw records in ascending key order. |
| Children | `children` | Union of `global_bt2_nrec + 1` child pointers; layout selected by tree depth. |
| Chksum | `chksum` | Jenkins lookup3 checksum of all preceding node bytes. |

### D1

Pickle union arm: `d1`.

Child-pointer array for a depth-1 internal node (children are leaves). Each pointer is a `child_ptr_d1` carrying the child address and record count only.

### Dn

Pickle union arm: `dn`.

Child-pointer array for a depth > 1 internal node (children are internal nodes). Each pointer is a `child_ptr_dn` carrying the child address, node record count, and subtree record count.


## Version 2 B-tree Leaf Node

Pickle type: `bt2_leaf`.

Version 2 B-tree leaf node (signature 'BTLF'). Contains up to the configured maximum number of records and no child pointers. Before mapping, set `global_bt2_nrec` to the record count for this node (from `hdr.num_root_records` for the root, or from the parent's `nrec_in_child_raw` for non-root nodes).

**Fields: Version 2 B-tree Leaf Node**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Signature | `signature` | 4-byte signature: 'B' 'T' 'L' 'F'. Must match exactly. |
| Version | `version` | Leaf node format version. Must be 0. |
| Record Type | `record_type` | Record type identifier (mirrors `bt2_hdr.record_type`). |
| Records | `records` | Array of `global_bt2_nrec` raw records, each `global_bt2_record_size` bytes. Use `print_v2_btree_record_at` to decode individual records according to `record_type`. |
| Chksum | `chksum` | Jenkins lookup3 checksum of all preceding node bytes. |


## Depth-1 Child Pointer

Pickle type: `child_ptr_d1`.

Child pointer in a depth-1 internal node (one whose children are leaf nodes). Contains the child's file address and the number of records directly stored in that child. No subtree record count is needed because the child is a leaf.

**Fields: Depth-1 Child Pointer**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Child Address Raw | `child_addr_raw` | File address of the child node (`sizeof_offsets` bytes). |
| Number of Records In Child Raw | `nrec_in_child_raw` | Number of records stored in the child node (`global_bt2_nrec_in_node_bytes` bytes). Use `set_bt2_nrec_size_from_hdr` to compute the correct byte width from the header. |


## Depth-N Child Pointer

Pickle type: `child_ptr_dn`.

Child pointer in a depth > 1 internal node (one whose children are themselves internal nodes). Adds a subtree record count field that records the total number of records in the child's entire subtree.

**Fields: Depth-N Child Pointer**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Child Address Raw | `child_addr_raw` | File address of the child node (`sizeof_offsets` bytes). |
| Number of Records In Child Raw | `nrec_in_child_raw` | Number of records directly in the child node (`global_bt2_nrec_in_node_bytes` bytes). |
| Number of Records In Subtree Raw | `nrec_in_subtree_raw` | Total records in the child's subtree including all descendant nodes (`global_bt2_nrec_in_subtree_bytes` bytes). Use `set_bt2_nrec_subtree_size_from_hdr` to compute the correct byte width. |


## Version 2 B-tree Type 1 Record

Pickle type: `bt2_rec_type1`.

Record type 1 — indirectly accessed, non-filtered huge object. The object is tracked in the fractal heap and carries a unique object ID.

**Fields: Version 2 B-tree Type 1 Record**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Huge Object Address Raw | `huge_obj_addr_raw` | File address of the huge object (`sizeof_offsets` bytes). |
| Huge Object Len Raw | `huge_obj_len_raw` | Size in bytes of the huge object (`sizeof_lengths` bytes). |
| Huge Object ID Raw | `huge_obj_id_raw` | Unique huge-object ID assigned by the heap (`sizeof_lengths` bytes). |


## Version 2 B-tree Type 2 Record

Pickle type: `bt2_rec_type2`.

Record type 2 — indirectly accessed, filtered huge object. Like type 1 but the data has passed through the filter pipeline; carries the unfiltered size and a filter skip mask.

**Fields: Version 2 B-tree Type 2 Record**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Huge Object Address Raw | `huge_obj_addr_raw` | File address of the filtered huge object (`sizeof_offsets` bytes). |
| Huge Object Len Raw | `huge_obj_len_raw` | On-disk (filtered) size in bytes (`sizeof_lengths` bytes). |
| Filter Mask | `filter_mask` | Filter pipeline skip mask (same semantics as `bt1_key1.filter_mask`). |
| Huge Object Mem Size Raw | `huge_obj_mem_size_raw` | Unfiltered (in-memory) size in bytes (`sizeof_lengths` bytes). |
| Huge Object ID Raw | `huge_obj_id_raw` | Unique huge-object ID (`sizeof_lengths` bytes). |


## Version 2 B-tree Type 3 Record

Pickle type: `bt2_rec_type3`.

Record type 3 — directly accessed, non-filtered huge object. The object is accessed by file address without heap tracking, so there is no unique ID field.

**Fields: Version 2 B-tree Type 3 Record**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Huge Object Address Raw | `huge_obj_addr_raw` | File address of the huge object (`sizeof_offsets` bytes). |
| Huge Object Len Raw | `huge_obj_len_raw` | Size in bytes of the huge object (`sizeof_lengths` bytes). |


## Version 2 B-tree Type 4 Record

Pickle type: `bt2_rec_type4`.

Record type 4 — directly accessed, filtered huge object. Like type 3 but includes filter metadata; no unique ID field.

**Fields: Version 2 B-tree Type 4 Record**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Huge Object Address Raw | `huge_obj_addr_raw` | File address of the filtered huge object (`sizeof_offsets` bytes). |
| Huge Object Len Raw | `huge_obj_len_raw` | On-disk (filtered) size in bytes (`sizeof_lengths` bytes). |
| Filter Mask | `filter_mask` | Filter pipeline skip mask. |
| Huge Object Mem Size Raw | `huge_obj_mem_size_raw` | Unfiltered (in-memory) size in bytes (`sizeof_lengths` bytes). |


## Version 2 B-tree Type 5 Record

Pickle type: `bt2_rec_type5`.

Record type 5 — link name in a creation-name-ordered indexed group. Provides fast lookup of a link by the hash of its name.

**Fields: Version 2 B-tree Type 5 Record**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Name Hash | `name_hash` | Jenkins lookup3 hash of the link name (used as the B-tree key). |
| Heap ID Raw | `heap_id_raw` | 7-byte fractal heap object ID for the link record. |


## Version 2 B-tree Type 6 Record

Pickle type: `bt2_rec_type6`.

Record type 6 — link name in a creation-order-indexed group. Provides fast lookup of a link by its creation order value.

**Fields: Version 2 B-tree Type 6 Record**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Creation Order | `creation_order` | Link creation order value (B-tree key). |
| Heap ID Raw | `heap_id_raw` | 7-byte fractal heap object ID for the link record. |


## Version 2 B-tree Type 7 Record - Message in Heap

Pickle type: `bt2_rec_type7_sub0`.

Record type 7, sub-type 0 — shared message stored in the fractal heap. Identified at runtime by reading the first byte of the record: `message_location == 0` selects this sub-type.

**Fields: Version 2 B-tree Type 7 Record - Message in Heap**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Message Location | `message_location` | Storage location indicator. Must be 0 for this sub-type (message is in the fractal heap). |
| Hash | `hash` | Jenkins lookup3 hash of the shared message payload (B-tree key). |
| Reference Count | `reference_count` | Number of object headers that reference this shared message. |
| Heap ID Raw | `heap_id_raw` | 8-byte fractal heap object ID for the shared message. |


## Version 2 B-tree Type 7 Record - Message in Object Header

Pickle type: `bt2_rec_type7_sub1`.

Record type 7, sub-type 1 — shared message stored inline in an object header. Identified by `message_location == 1`.

**Fields: Version 2 B-tree Type 7 Record - Message in Object Header**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Message Location | `message_location` | Storage location indicator. Must be 1 for this sub-type (message is in an object header). |
| Hash | `hash` | Jenkins lookup3 hash of the shared message payload (B-tree key). |
| Reserved | `reserved` | Reserved byte between `hash` and `message_type`. Must be zero. |
| Message Type | `message_type` | Object header message type of the shared message. |
| Object Header Index | `obj_hdr_index` | Index of the message within its containing object header. |
| Object Header Address Raw | `obj_hdr_addr_raw` | File address of the object header containing the shared message (`sizeof_offsets` bytes). |


## Version 2 B-tree Type 8 Record

Pickle type: `bt2_rec_type8`.

Record type 8 — attribute name for name-ordered indexed attributes. Provides fast lookup of an attribute by name hash and creation order.

**Fields: Version 2 B-tree Type 8 Record**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Heap ID Raw | `heap_id_raw` | 8-byte fractal heap object ID for the attribute record. |
| Message Flags | `message_flags` | Object header message flags for this attribute (same bit definitions as `msg_prefix.msg_flags`). |
| Creation Order | `creation_order` | Attribute creation order value. |
| Name Hash | `name_hash` | Jenkins lookup3 hash of the attribute name (primary B-tree key). |


## Version 2 B-tree Type 9 Record

Pickle type: `bt2_rec_type9`.

Record type 9 — attribute name for creation-order-indexed attributes. Like type 8 but without the name hash; creation order is the key.

**Fields: Version 2 B-tree Type 9 Record**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Heap ID Raw | `heap_id_raw` | 8-byte fractal heap object ID for the attribute record. |
| Message Flags | `message_flags` | Object header message flags for this attribute. |
| Creation Order | `creation_order` | Attribute creation order value (B-tree key). |


## Version 2 B-tree Type 10 Record

Pickle type: `bt2_rec_type10`.

Record type 10 — non-filtered dataset chunk address. Used as the chunk index for datasets whose chunks pass through no filter pipeline. The number of `scaled_offsets` entries equals the dataset dimensionality; before mapping, set `global_bt2_ndims` accordingly or call `print_v2_btree` which derives it automatically.

**Fields: Version 2 B-tree Type 10 Record**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Chunk Address Raw | `chunk_addr_raw` | File address of the chunk data payload (`sizeof_offsets` bytes). |
| Scaled Offsets | `scaled_offsets` | Array of `global_bt2_ndims` uint64 scaled chunk position values. Each entry is the logical dimension offset divided by the chunk dimension size, giving the chunk's coordinates in chunk-index space (B-tree key). |


## Version 2 B-tree Type 11 Record

Pickle type: `bt2_rec_type11`.

Record type 11 — filtered dataset chunk address. Like type 10 but includes the on-disk (filtered) chunk size and a filter skip mask. HDF5 supplies layout context to the v2 B-tree callbacks; for layout version 4 the chunk-size field can be shorter than `sizeof_lengths`. Set `global_bt2_ndims` to the number of real dataset dimensions and `global_bt2_chunk_size_len` before mapping when that context is known.

**Fields: Version 2 B-tree Type 11 Record**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Chunk Address Raw | `chunk_addr_raw` | File address of the filtered chunk data payload (`sizeof_offsets` bytes). |
| Chunk Size Raw | `chunk_size_raw` | On-disk filtered chunk size, `global_bt2_chunk_size_len` bytes. |
| Filter Mask | `filter_mask` | Filter pipeline skip mask for this chunk. |
| Scaled Offsets | `scaled_offsets` | Array of `global_bt2_ndims` uint64 scaled chunk position values for real dataset dimensions only. |


## Unknown Version 2 B-tree Record

Pickle type: `bt2_raw_record`.

Generic fallback record used when the record type is unknown or unhandled. Stores the raw bytes of the record so they can be inspected without type-specific decoding.

**Fields: Unknown Version 2 B-tree Record**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Data | `data` | Raw record bytes (`global_bt2_record_size` bytes). |
