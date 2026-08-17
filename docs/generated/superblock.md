# II.A. Disk Format: Level 0A - Format Signature and Superblock

<a id="subsec_fmt4_boot_super"></a>

Upstream: [HDF5 File Format Specification 4.0, section II.A](https://support.hdfgroup.org/documentation/hdf5/latest/_f_m_t4.html#subsec_fmt4_boot_super) · Coverage: **Covered**

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

Mapping a superblock records its declared end-of-file address as the
logical range for subsequent metadata decoding. Addresses and address/
size pairs checked by other pickles are rejected when they point at or
extend beyond that exclusive bound; this remains independent of any
surplus bytes exposed by a file driver.

## Superblock

Pickle type: `superblock`.

The root on-disk metadata structure of every HDF5 file.

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

**Fields: Superblock**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Signature | `signature` | 8-byte magic number: `0x89 'H' 'D' 'F' 0x0D 0x0A 0x1A 0x0A`. The leading `0x89` sets the high bit so that systems expecting plain ASCII will reject the file; the CR+LF pair detects newline translation; the `0x1A` stops output on MS-DOS `type`; and the final `0x0A` detects trailing newline suppression. |
| Superblock Version | `super_vers` | Superblock format version. Valid values: 0, 1, 2, 3. Versions 0 and 1 use the `v0_v1` layout; versions 2 and 3 use `v2_v3`. |

### Versions 0 and 1

Pickle union arm: `v0_v1`.

Layout for superblock versions 0 and 1. Version 1 extends version 0 by adding the `indexed_internal_k` and `res3` fields.

**Fields: Versions 0 and 1**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Free-space Info Version | `fs_info_vers` | Version of the file free-space storage format. Must be 0. |
| Root Symbol Table Version | `root_stab_vers` | Version of the root group symbol table entry format. Must be 0. |
| Reserved | `res1` | Reserved. Must be zero. |
| Shared Header Version | `shared_hdr_vers` | Version of the shared object header message format. Must be 0. |
| Size of Offsets | `sizeof_offsets` | Size in bytes of file addresses (offsets). Typical value: 8. Valid values are 2, 4, 8, 16, and 32; other widths are rejected before they can control later variable-width maps. Sets the global `sizeof_offsets` used by all subsequent address fields. |
| Size of Lengths | `sizeof_lengths` | Size in bytes of file lengths. Typical value: 8. Sets the global `sizeof_lengths` used by all length fields. Valid values are 2, 4, 8, 16, and 32. |
| Reserved | `res2` | Reserved. Must be zero. |
| Symbol Table Leaf K | `stab_leaf_k` | Half the rank of leaf nodes in the version 1 group B-tree. Must be greater than zero.  The maximum number of entries in a leaf node is `2 * stab_leaf_k`. |
| Symbol Table Internal K | `stab_internal_k` | Half the rank of internal nodes in the version 1 group B-tree. Must be greater than zero. |
| Status Flags | `status_flags` | File consistency flags. This field is unused in superblock versions 0 and 1 and should be ignored. |
| Indexed Internal K | `indexed_internal_k` | Half the rank of internal nodes in the version 1 B-tree used for indexed (chunked) storage. Present only in superblock version 1; must be greater than zero. |
| Reserved | `res3` | Reserved. Must be zero. Present only in superblock version 1, immediately following `indexed_internal_k`. |
| Base Address Raw | `base_addr_raw` | Absolute byte offset of the start of the HDF5 address space within the physical file. For newly created files this is constrained to the physical offset of the superblock signature, which may be 0, 512, 1024, 2048, and so on. Unless otherwise noted, stored file addresses are relative to this base. |
| Free-space Info Address Raw | `fs_info_addr_raw` | Address of the global free-space index. Persistent free-space management is not supported by superblock versions 0 and 1, so this field always contains HADDR_UNDEF (`0xFF…FF`). |
| End-of-file Address Raw | `eof_addr_raw` | File address of the first byte beyond all HDF5 data (the logical end-of-file). |
| Driver Info Address Raw | `drv_info_addr_raw` | File address of the driver information block, or HADDR_UNDEF if no driver information is present. |
| Root Symbol Table Ent | `root_stab_ent` | Symbol table entry for the root group (type `stab_ent`). |

### Versions 2 and 3

Pickle union arm: `v2_v3`.

Compact layout introduced in superblock version 2. Replaces the symbol-table root entry with a direct object header address and adds a checksum over all preceding superblock bytes. Version 3 restricts the consistency flags to bits 0–2 only.

**Fields: Versions 2 and 3**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Size of Offsets | `sizeof_offsets` | Size in bytes of file addresses. Typical value: 8. Sets the global `sizeof_offsets`. |
| Size of Lengths | `sizeof_lengths` | Size in bytes of file lengths. Typical value: 8. Sets the global `sizeof_lengths`. |
| Status Flags | `status_flags` | File consistency flags. In version 2 this field is unused and should be ignored. In version 3, bit 0 indicates that the file is open for write access, bit 1 is reserved, and bit 2 indicates that the file is open for single-writer/multiple-reader (SWMR) write access. Bits 3–7 are reserved and must be zero. |
| Base Address Raw | `base_addr_raw` | Absolute byte offset of the start of the HDF5 address space. |
| Ext Address Raw | `ext_addr_raw` | File address of the superblock extension object header, or HADDR_UNDEF if no extension is present. The extension carries optional metadata such as the driver information message. |
| End-of-file Address Raw | `eof_addr_raw` | File address of the first byte beyond all HDF5 data. |
| Root Object Address Raw | `root_obj_addr_raw` | File address of the root group object header. |
| Chksum | `chksum` | Jenkins lookup3 checksum computed over all preceding superblock bytes (from the signature through `root_obj_addr_raw`). The executable mapping verifies it before accepting the superblock. |
