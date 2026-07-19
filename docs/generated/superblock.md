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

**Layout: Superblock (Versions 0 and 1)**

<table class="format-layout">
  <thead><tr><th>byte</th><th>byte</th><th>byte</th><th>byte</th></tr></thead>
  <tbody>
    <tr><td colspan="4">Format Signature (8 bytes)</td></tr>
    <tr><td colspan="4">Format Signature (continued)</td></tr>
    <tr><td>Superblock Version</td><td>Free-space Version</td><td>Root Group Symbol Table Version</td><td>Reserved</td></tr>
    <tr><td>Shared Header Version</td><td>Size of Offsets</td><td>Size of Lengths</td><td>Reserved</td></tr>
    <tr><td colspan="2">Group Leaf Node K</td><td colspan="2">Group Internal Node K</td></tr>
    <tr><td colspan="4">File Consistency Flags</td></tr>
    <tr><td colspan="4">Version 1 B-tree K and Reserved (version 1 only)</td></tr>
    <tr><td colspan="4">Base Address<sup>O</sup></td></tr>
    <tr><td colspan="4">Free-space Info Address<sup>O</sup></td></tr>
    <tr><td colspan="4">End-of-file Address<sup>O</sup></td></tr>
    <tr><td colspan="4">Driver Information Address<sup>O</sup></td></tr>
    <tr><td colspan="4">Root Group Symbol Table Entry</td></tr>
  </tbody>
</table>

**Layout: Superblock (Versions 2 and 3)**

<table class="format-layout">
  <thead><tr><th>byte</th><th>byte</th><th>byte</th><th>byte</th></tr></thead>
  <tbody>
    <tr><td colspan="4">Format Signature (8 bytes)</td></tr>
    <tr><td colspan="4">Format Signature (continued)</td></tr>
    <tr><td>Superblock Version</td><td>Size of Offsets</td><td>Size of Lengths</td><td>File Consistency Flags</td></tr>
    <tr><td colspan="4">Base Address<sup>O</sup></td></tr>
    <tr><td colspan="4">Superblock Extension Address<sup>O</sup></td></tr>
    <tr><td colspan="4">End-of-file Address<sup>O</sup></td></tr>
    <tr><td colspan="4">Root Group Object Header Address<sup>O</sup></td></tr>
    <tr><td colspan="4">Checksum</td></tr>
  </tbody>
</table>

`O` is the size of offsets. Fields whose width is `L` elsewhere in the format use the Size of Lengths declared here.

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
| `status_flags` | File consistency flags. This field is unused in superblock versions 0 and 1 and should be ignored. |
| `indexed_internal_k` | Half the rank of internal nodes in the version 1 B-tree used for indexed (chunked) storage. Present only in superblock version 1; must be greater than zero. |
| `res3` | Reserved. Must be zero. Present only in superblock version 1, immediately following `indexed_internal_k`. |
| `base_addr_raw` | Absolute byte offset of the start of the HDF5 address space within the physical file. For newly created files this is constrained to the physical offset of the superblock signature, which may be 0, 512, 1024, 2048, and so on. Unless otherwise noted, stored file addresses are relative to this base. |
| `fs_info_addr_raw` | Address of the global free-space index. Persistent free-space management is not supported by superblock versions 0 and 1, so this field always contains HADDR_UNDEF (`0xFF…FF`). |
| `eof_addr_raw` | File address of the first byte beyond all HDF5 data (the logical end-of-file). |
| `drv_info_addr_raw` | File address of the driver information block, or HADDR_UNDEF if no driver information is present. |
| `root_stab_ent` | Symbol table entry for the root group (type `stab_ent`). |

### `v2_v3`

Compact layout introduced in superblock version 2. Replaces the symbol-table root entry with a direct object header address and adds a checksum over all preceding superblock bytes. Version 3 restricts the consistency flags to bits 0–2 only.

| Field | Description |
|-------|-------------|
| `sizeof_offsets` | Size in bytes of file addresses. Typical value: 8. Sets the global `sizeof_offsets`. |
| `sizeof_lengths` | Size in bytes of file lengths. Typical value: 8. Sets the global `sizeof_lengths`. |
| `status_flags` | File consistency flags. In version 2 this field is unused and should be ignored. In version 3, bit 0 indicates that the file is open for write access, bit 1 is reserved, and bit 2 indicates that the file is open for single-writer/multiple-reader (SWMR) write access. Bits 3–7 are reserved and must be zero. |
| `base_addr_raw` | Absolute byte offset of the start of the HDF5 address space. |
| `ext_addr_raw` | File address of the superblock extension object header, or HADDR_UNDEF if no extension is present. The extension carries optional metadata such as the driver information message. |
| `eof_addr_raw` | File address of the first byte beyond all HDF5 data. |
| `root_obj_addr_raw` | File address of the root group object header. |
| `chksum` | Jenkins lookup3 checksum computed over all preceding superblock bytes (from the signature through `root_obj_addr_raw`). |
