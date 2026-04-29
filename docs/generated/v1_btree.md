# III.A.1. Disk Format: Level 1A1 – Version 1 B-tree Nodes and Symbol Table Nodes

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

## `bt1_key0`

Key for a type-0 (group symbol table) B-tree node. Bounds a range of link names by their offset in the group's local heap.

| Field | Description |
|-------|-------------|
| `name_off_raw` | Byte offset into the local heap of the first link name in the range covered by this key (`sizeof_lengths` bytes, little-endian). |


## `bt1_key1`

Key for a type-1 (raw-data chunk) B-tree node. Identifies the logical position of a chunk in dataset space and records its on-disk size.

| Field | Description |
|-------|-------------|
| `chunk_size` | Size in bytes of the chunk payload as stored on disk (after any filter pipeline). |
| `filter_mask` | Pipeline skip mask. Bit i set means filter i was not applied to this chunk (e.g. the chunk was already in the desired form). |
| `chunk_offsets` | Array of `global_bt1_ndims` uint64 logical dimension offsets (0-based) locating the chunk in dataset space. The last entry is always zero per the HDF5 specification and is used as a sentinel. |


## `bt1_pair0`

A single key/child pair for a type-0 (group) B-tree node. Each valid body slot is one of these; a trailing key follows the last pair.

| Field | Description |
|-------|-------------|
| `key` | The `bt1_key0` key bounding the left edge of this child's range. |
| `child_raw` | File address of the child (`sizeof_offsets` bytes). At `node_level == 0` this points to a Symbol Table Node (SNOD); at higher levels it points to another `v1_btree` node. |


## `bt1_pair1`

A single key/child pair for a type-1 (raw-data chunk) B-tree node.

| Field | Description |
|-------|-------------|
| `key` | The `bt1_key1` key identifying this chunk's logical position. |
| `child_raw` | File address of the child (`sizeof_offsets` bytes). At `node_level == 0` this is the file address of the chunk data payload; at higher levels it is another `v1_btree` node. |


## `v1_btree`

Version 1 B-tree node (signature 'TREE'). A single on-disk record that acts as either an internal node or a leaf, depending on `node_level`. Nodes at level 0 are leaves; their children are either chunk data (type 1) or Symbol Table Nodes (type 0). A third union arm `unknown` (six raw bytes) is a fallback for invalid node types and is never written by a conforming implementation.

| Field | Description |
|-------|-------------|
| `signature` | 4-byte signature: 'T' 'R' 'E' 'E'. Must match exactly. |
| `node_type` | Node type: 0 = group (symbol table), 1 = raw-data chunks. |
| `node_level` | Height of this node in the tree. 0 = leaf; children at level > 0 are also `v1_btree` nodes. The root node's level equals the height of the tree minus one. |
| `entries_used` | Number of valid key/child pairs stored in this node. Always ≤ `2 × K` where K is the relevant superblock B-tree K value. |
| `left_sib_raw` | File address of the left sibling node at the same tree level (`sizeof_offsets` bytes). HADDR_UNDEF if this is the leftmost node at this level. |
| `right_sib_raw` | File address of the right sibling node at the same level. HADDR_UNDEF if this is the rightmost node. |

### `type0`

Node body for a type-0 (group symbol table) node.

| Field | Description |
|-------|-------------|
| `pairs` | Array of `entries_used` `bt1_pair0` key/child pairs in ascending key order. |
| `final_key` | Trailing `bt1_key0` key bounding the right edge of the last child's range. |

### `type1`

Node body for a type-1 (raw-data chunk) node.

| Field | Description |
|-------|-------------|
| `pairs` | Array of `entries_used` `bt1_pair1` key/child pairs in ascending chunk-offset order. |
| `final_key` | Trailing `bt1_key1` key bounding the right edge of the last chunk. |


## `snod_node`

Symbol Table Node (signature 'SNOD'). Leaf node pointed to by the child pointers of a type-0 B-tree leaf. Each SNOD holds between 0 and `2 × stab_leaf_k` symbol table entries; `num_symbols` records how many are valid. The `stab_ent` type is defined in `superblock.pk`.

| Field | Description |
|-------|-------------|
| `signature` | 4-byte signature: 'S' 'N' 'O' 'D'. Must match exactly. |
| `version` | Symbol table node version. Must be 1. |
| `res` | Reserved. Must be zero. |
| `num_symbols` | Number of valid `stab_ent` entries in `entries`. |
| `entries` | Array of `num_symbols` symbol table entries of type `stab_ent` (see `superblock.pk`). Each entry records a link name offset, an object header address, a cache type, and a scratch-pad area. |


