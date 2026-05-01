# IV.A.1. Disk Format: Level 0A – File Signatures and Superblock

The superblock contains the information needed to access all other
HDF5 data structures. It must begin at address 0 within the HDF5 file,
or at one of the following powers-of-two offsets: 512, 1024, 2048, …
bytes from the beginning of the file. Libraries that do not write the
superblock at offset zero must scan those candidate offsets for the
8-byte signature to locate it.

Four superblock versions are defined. Versions 0 and 1 share the same
basic layout but version 1 adds a field for the indexed-storage
internal-node K value. Versions 2 and 3 use a more compact layout that
replaces the symbol-table root group entry with a plain object header
address and adds a checksum. Version 3 additionally restricts which
bits of the consistency flags field may be set.

## `stab_ent`

Symbol table entry for the root group object, embedded directly in superblock versions 0 and 1. Each entry records the object header address, a cache type, and a scratch-pad area whose meaning depends on the cache type.

| Field | Description |
|-------|-------------|
| `lnk_nm_off_raw` | Byte offset of the link name within the root local heap's data segment. For the root entry this field is not meaningful and is typically zero. |
| `ohdr_addr_raw` | File address of the object header for the root group. |
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

Present when `cache_type == 0`. The 16 bytes are undefined and should be ignored.


## `superblock`

The root on-disk metadata structure of every HDF5 file.

| Field | Description |
|-------|-------------|
| `signature` | 8-byte magic number: `0x89 'H' 'D' 'F' 0x0D 0x0A 0x1A 0x0A`. The leading `0x89` sets the high bit so that systems expecting plain ASCII will reject the file; the CR+LF pair detects newline translation; the `0x1A` stops output on MS-DOS `type`; and the final `0x0A` detects trailing newline suppression. |
| `super_vers` | Superblock format version. Valid values: 0, 1, 2, 3. Versions 0 and 1 use the `v0_v1` layout; versions 2 and 3 use `v2_v3`. |

### `v0_v1`

Layout for superblock versions 0 and 1. Version 1 extends version 0 by adding the `indexed_internal_k` and `res3` fields.

| Field | Description |
|-------|-------------|
| `fs_info_vers` | Version of the file free-space storage format. Must be 0. |
| `root_stab_vers` | Version of the root group symbol table entry format. Must be 0. |
| `res1` | Reserved. Must be zero. |
| `shared_hdr_vers` | Version of the shared object header message format. Must be 0. |
| `sizeof_offsets` | Size in bytes of file addresses (offsets). Typical value: 8. Sets the global `sizeof_offsets` used by all subsequent address fields. |
| `sizeof_lengths` | Size in bytes of file lengths. Typical value: 8. Sets the global `sizeof_lengths` used by all length fields. |
| `res2` | Reserved. Must be zero. |
| `stab_leaf_k` | Half the rank of leaf nodes in the version 1 group B-tree. Must be greater than zero.  The maximum number of entries in a leaf node is `2 * stab_leaf_k`. |
| `stab_internal_k` | Half the rank of internal nodes in the version 1 group B-tree. Must be greater than zero. |
| `status_flags` | File consistency flags. Bit 0: file is open for write access and may be inconsistent. Bit 1: file has been verified as consistently closed. |
| `indexed_internal_k` | Half the rank of internal nodes in the version 1 B-tree used for indexed (chunked) storage. Present only in superblock version 1; must be greater than zero. |
| `res3` | Reserved. Must be zero. Present only in superblock version 1, immediately following `indexed_internal_k`. |
| `base_addr_raw` | Absolute byte offset of the start of the HDF5 address space within the physical file. Usually 0. All stored addresses are relative to this base. |
| `fs_info_addr_raw` | File address of the free-space manager information block, or HADDR_UNDEF (`0xFF…FF`) if free space is not tracked. |
| `eof_addr_raw` | File address of the first byte beyond all HDF5 data (the logical end-of-file). |
| `drv_info_addr_raw` | File address of the driver information block, or HADDR_UNDEF if no driver information is present. |
| `root_stab_ent` | Symbol table entry for the root group (type `stab_ent`). |

### `v2_v3`

Compact layout introduced in superblock version 2. Replaces the symbol-table root entry with a direct object header address and adds a checksum over all preceding superblock bytes. Version 3 restricts the consistency flags to bits 0–2 only.

| Field | Description |
|-------|-------------|
| `sizeof_offsets` | Size in bytes of file addresses. Typical value: 8. Sets the global `sizeof_offsets`. |
| `sizeof_lengths` | Size in bytes of file lengths. Typical value: 8. Sets the global `sizeof_lengths`. |
| `status_flags` | File consistency flags. In version 2, any bit may be set. In version 3, only bits 0–2 are defined; bits 3–7 must be zero. |
| `base_addr_raw` | Absolute byte offset of the start of the HDF5 address space. |
| `ext_addr_raw` | File address of the superblock extension object header, or HADDR_UNDEF if no extension is present. The extension carries optional metadata such as the driver information message. |
| `eof_addr_raw` | File address of the first byte beyond all HDF5 data. |
| `root_obj_addr_raw` | File address of the root group object header. |
| `chksum` | Jenkins lookup3 checksum computed over all preceding superblock bytes (from the signature through `root_obj_addr_raw`). |


