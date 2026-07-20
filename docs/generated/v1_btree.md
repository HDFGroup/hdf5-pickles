# III.A.1. Disk Format: Level 1A1 – Version 1 B-tree Nodes

Version 1 B-trees (on-disk signature 'TREE') are the original indexing
structure in HDF5. Two node types are defined:

- **Node type 0** — group (symbol table) B-tree. Used to index the
  members of a group stored in the legacy symbol-table format. Leaf
  children are Symbol Table Nodes (signature 'SNOD').
- **Node type 1** — raw-data chunk B-tree. Used to index the chunks
  of a chunked dataset. At level 0 each child pointer addresses a
  chunk payload directly.

The on-disk key/child layout for a node with `entries_used = n` is:

```
K_0  C_0  K_1  C_1  ...  K_{n-1}  C_{n-1}  K_n
```

Each node is sized to hold up to `2K` entries (where K is the relevant
B-tree K value from the superblock). Only the first `entries_used` pairs
are valid; unused capacity beyond that is not mapped by these pickles.

Before mapping a type-1 node, call `set_bt1_ndims(n)` where n is the
dataset dimensionality plus one. Use `print_v1_btree(addr#B, 0)` to
recursively print the full tree.

**Layout: Version 1 B-tree Node**

<table class="format-layout">
  <thead><tr><th>byte</th><th>byte</th><th>byte</th><th>byte</th></tr></thead>
  <tbody>
    <tr><td colspan="4">Signature</td></tr>
    <tr><td>Node Type</td><td>Node Level</td><td colspan="2">Entries Used</td></tr>
    <tr><td colspan="4">Left Sibling Address<sup>O</sup></td></tr>
    <tr><td colspan="4">Right Sibling Address<sup>O</sup></td></tr>
    <tr><td colspan="4">Key 1 (variable size)</td></tr>
    <tr><td colspan="4">Child 1 Address<sup>O</sup></td></tr>
    <tr><td colspan="4">…</td></tr>
    <tr><td colspan="4">Final Key (variable size)</td></tr>
  </tbody>
</table>

`O` is the size of offsets. Type 0 keys have width `L`, where `L` is the size of lengths.

## `key0`

Key for a type-0 (group symbol table) B-tree node. Bounds a range of link names by their offset in the group's local heap.

| Field | Description |
|-------|-------------|
| `name_off_raw` | Byte offset into the local heap of the first link name in the range covered by this key (`sizeof_lengths` bytes, little-endian). |


## `key1`

Key for a type-1 (raw-data chunk) B-tree node. Identifies the logical position of a chunk in dataset space and records its on-disk size.

| Field | Description |
|-------|-------------|
| `chunk_size` | Size in bytes of the chunk payload as stored on disk (after any filter pipeline). |
| `filter_mask` | Pipeline skip mask. Bit i set means filter i was not applied to this chunk (e.g. the chunk was already in the desired form). |
| `chunk_offsets` | Array of `global_bt1_ndims` uint64 logical dimension offsets (0-based) locating the chunk in dataset space. The last entry is always zero per the HDF5 specification and is used as a sentinel. |


## `pair0`

A single key/child pair for a type-0 (group) B-tree node. Each valid body slot is one of these; a trailing key follows the last pair.

| Field | Description |
|-------|-------------|
| `key` | The `key0` key bounding the left edge of this child's range. |
| `child_raw` | File address of the child (`sizeof_offsets` bytes). At `node_level == 0` this points to a Symbol Table Node (SNOD); at higher levels it points to another `bt1_hdr` node. |


## `pair1`

A single key/child pair for a type-1 (raw-data chunk) B-tree node.

| Field | Description |
|-------|-------------|
| `key` | The `key1` key identifying this chunk's logical position. |
| `child_raw` | File address of the child (`sizeof_offsets` bytes). At `node_level == 0` this is the file address of the chunk data payload; at higher levels it is another `bt1_hdr` node. |


## `bt1_hdr`

Version 1 B-tree node (signature 'TREE'). A single on-disk record that acts as either an internal node or a leaf, depending on `node_level`. Nodes at level 0 are leaves; their children are either chunk data (type 1) or Symbol Table Nodes (type 0). A third union arm `unknown` (six raw bytes) is a fallback for invalid node types and is never written by a conforming implementation.

| Field | Description |
|-------|-------------|
| `signature` | 4-byte signature: 'T' 'R' 'E' 'E'. Must match exactly. |
| `node_type` | Node type: 0 = group (symbol table), 1 = raw-data chunks. |
| `node_level` | Height of this node in the tree. 0 = leaf; children at level > 0 are also `bt1_hdr` nodes. The root node's level equals the height of the tree minus one. |
| `entries_used` | Number of valid key/child pairs stored in this node. Always ≤ `2 × K` where K is the relevant superblock B-tree K value. |
| `left_sib_raw` | File address of the left sibling node at the same tree level (`sizeof_offsets` bytes). HADDR_UNDEF if this is the leftmost node at this level. |
| `right_sib_raw` | File address of the right sibling node at the same level. HADDR_UNDEF if this is the rightmost node. |

### `type0`

Node body for a type-0 (group symbol table) node.

| Field | Description |
|-------|-------------|
| `pairs` | Array of `entries_used` `pair0` key/child pairs in ascending key order. |
| `final_key` | Trailing `key0` key bounding the right edge of the last child's range. |

### `type1`

Node body for a type-1 (raw-data chunk) node.

| Field | Description |
|-------|-------------|
| `pairs` | Array of `entries_used` `pair1` key/child pairs in ascending chunk-offset order. |
| `final_key` | Trailing `key1` key bounding the right edge of the last chunk. |
