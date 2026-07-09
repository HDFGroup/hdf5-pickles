# III.A.2. Disk Format: Level 1B – Symbol Table Nodes and Entries

The legacy (version 1) group format stores a group's members in a
symbol table: a version 1 B-tree of node type 0 whose leaf children are
Symbol Table Nodes (signature 'SNOD'). Each node holds an array of
Symbol Table Entries, one per link.

A Symbol Table Entry (`stab_ent`) also appears directly in versions 0
and 1 of the superblock, as the root group entry. Each entry records
the object header address of the linked object, a cache type, and a
scratch-pad area whose meaning depends on the cache type.

All fields are stored in little-endian byte order.

## `stab_ent`

Symbol table entry. Appears in the version 0/1 superblock root group entry and in every SNOD leaf node. Each entry records the object header address, a cache type, and a scratch-pad area whose meaning depends on the cache type.

| Field | Description |
|-------|-------------|
| `lnk_nm_off_raw` | Byte offset of the link name within the group's local heap data segment. For the superblock root entry this field is not meaningful and is typically zero. |
| `ohdr_addr_raw` | File address of the object header for the linked object. |
| `cache_type` | Indicates what is cached in the scratch-pad space. 0 = no cache; 1 = group (B-tree address and heap address are cached); 2 = symbolic link (soft-link target offset is cached). Values 3 and above are reserved. |
| `res` | Reserved. Must be zero. |
| `scratch_pad` | 16-byte scratch-pad area. Interpretation is determined by `cache_type`. See variants below. |

### `obj_info`

Present when `cache_type == 1`. Caches the group's B-tree and local heap addresses so that the symbol table can be traversed without first mapping the object header.

| Field | Description |
|-------|-------------|
| `btree_addr_raw` | File address of the root B-tree node for the group's symbol table. |
| `heap_addr_raw` | File address of the local heap containing link names for the group. |

### `slink`

Present when `cache_type == 2`. Stores the byte offset of the symbolic-link target string within the local heap.

### `pad`

Present when `cache_type == 0`. The 16 bytes are undefined and should be ignored. Reserved cache type values cannot select this arm because `stab_ent` constrains `cache_type` to values 0–2.


## `stab_node`

Symbol Table Node (signature 'SNOD'). Leaf node pointed to by the child pointers of a type-0 version 1 B-tree leaf. Each SNOD holds between 0 and `2 × stab_leaf_k` symbol table entries; `num_symbols` records how many are valid.

| Field | Description |
|-------|-------------|
| `signature` | 4-byte signature: 'S' 'N' 'O' 'D'. Must match exactly. |
| `version` | Symbol table node version. Must be 1. |
| `res` | Reserved. Must be zero. |
| `num_symbols` | Number of valid `stab_ent` entries in `entries`. |
| `entries` | Array of `num_symbols` symbol table entries of type `stab_ent`. Each entry records a link name offset, an object header address, a cache type, and a scratch-pad area. |


