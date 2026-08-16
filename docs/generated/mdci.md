# III.J. Disk Format: Level 1J - Metadata Cache Image Block

<a id="subsec_fmt4_infra_mdci"></a>

Upstream: [HDF5 File Format Specification 4.0, section III.J](https://support.hdfgroup.org/documentation/hdf5/latest/_f_m_t4.html#subsec_fmt4_infra_mdci) · Coverage: **Covered**

The metadata cache image block is a serialized snapshot of the metadata
cache taken at file close, written when cache-image generation is enabled
for the file. It lets the library reconstruct the cache directly from
this block the next time the file is opened, instead of reconstructing
it by parsing the file's metadata. The block is named by the "Metadata
Cache Image" object header message (signature-less; see `oh_msg_mdci` in
`ohdr_msgs.pk`), which lives in the superblock extension and stores only
the block's address and size, not the block itself.

The block begins with a signature, version, flags, image data length,
and entry count, followed by one record for each metadata cache entry
captured in the image, and ends with a checksum for the block. Each
entry records the cache-client type, its flush-dependency and LRU
bookkeeping, its file address and length, an optional list of
flush-dependency parent addresses, and the entry's own image: a
byte-for-byte copy of the cached client's on-disk serialization (an
object header, B-tree node, or other cached metadata) as it would
otherwise appear at the entry's file address.

This pickle decodes the block's own container in full: its header and
every entry's fixed metadata. It does not decode each entry's image,
since that payload's format is the client's own on-disk structure, not
part of the cache-image container format itself.

The decoder verifies the block's lookup3 checksum before accepting the
container; individual entry images remain opaque client-owned payloads.

All fields are stored in little-endian byte order.

## Metadata Cache Image Block

Pickle type: `mdci_block`.

The metadata cache image block (signature 'MDCI'). Its `entries` field is sized directly from the on-disk entry count, so mapping this type over a file whose declared count does not fit the available bytes raises the ordinary poke mapping exception for the entry that overruns.

**Layout: Metadata Cache Image Block**

<table class="format-layout">
  <thead><tr><th>byte</th><th>byte</th><th>byte</th><th>byte</th></tr></thead>
  <tbody>
    <tr><td colspan="4">Signature</td></tr>
    <tr><td>Version</td><td>Flags</td><td colspan="2">Image Data Length<sup>L</sup></td></tr>
    <tr><td colspan="4">Image Data Length (continued)<sup>L</sup></td></tr>
    <tr><td colspan="4">Number of Entries</td></tr>
    <tr><td colspan="4">Image Entry #0</td></tr>
    <tr><td colspan="4">Image Entry #1</td></tr>
    <tr><td colspan="4">...</td></tr>
    <tr><td colspan="4">Image Entry #N-1</td></tr>
    <tr><td colspan="4">Checksum</td></tr>
  </tbody>
</table>

Rows containing variable-width fields are schematic. `O` is the size of offsets; `L` is the size of lengths.

**Fields: Metadata Cache Image Block**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Signature | `signature` | 4-byte signature: 'M' 'D' 'C' 'I'. Must match exactly. |
| Version | `version` | Block version. Must be 0. |
| Flags | `flags` | Header flags. Bit 0 set means adaptive-cache-resize status information follows the entries; the library does not currently generate that information, so this bit is always 0 in practice. Bits 1-7 are reserved. |
| Image Data Len Raw | `image_data_len_raw` | Total byte length of the whole block, including this header, every entry, and the trailing checksum (`sizeof_lengths` bytes). This is the same value stored as the block's size in the referencing "Metadata Cache Image" object-header message. |
| N Entries | `n_entries` | Number of metadata cache entry records that follow the header. Must be greater than 0. |
| Entries | `entries` | The `n_entries` metadata cache entry records captured in the image, one per entry resident in the metadata cache at file close, in file order. |
| Chksum | `chksum` | Jenkins lookup3 checksum over the header and all entries that precede it. |


## Image Entry

Pickle type: `mdci_entry`.

One metadata cache entry captured in the image: its cache-client type, flush-dependency and LRU bookkeeping, file address and length, an optional flush-dependency parent-address list, and the entry's own cached-client image.

**Layout: Image Entry**

<table class="format-layout">
  <thead><tr><th>byte</th><th>byte</th><th>byte</th><th>byte</th></tr></thead>
  <tbody>
    <tr><td>Type ID</td><td>Flags</td><td>Ring</td><td>Age</td></tr>
    <tr><td colspan="2">Flush Dependency Child Count</td><td colspan="2">Flush Dependency Dirty Child Count</td></tr>
    <tr><td colspan="2">Flush Dependency Parent Count</td><td colspan="2">LRU Rank</td></tr>
    <tr><td colspan="4">LRU Rank (continued)</td></tr>
    <tr><td colspan="4">Entry Offset<sup>O</sup></td></tr>
    <tr><td colspan="4">Entry Length<sup>L</sup></td></tr>
    <tr><td colspan="4">Flush Dependency Parent Addresses<sup>O</sup></td></tr>
    <tr><td colspan="4">Entry Image</td></tr>
  </tbody>
</table>

Flush Dependency Parent Addresses repeats once per Flush Dependency Parent Count and is present only when that count is nonzero; Entry Image is exactly Entry Length bytes.

**Fields: Image Entry**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Type ID | `type_id` | Internal, implementation-defined identifier for the type of metadata cache client (for example, superblock, object header, or B-tree node) that owns this entry. |
| Entry Flags | `entry_flags` | Entry flags. Bit 0 set means the entry was dirty (not yet written to the file) when the image was generated; bit 1 set means the entry was on the cache's LRU list, with `lru_rank_raw` giving its position; bit 2 set means the entry is a flush-dependency parent; bit 3 set means the entry is a flush-dependency child, so one or more parent addresses follow the fixed fields. Bits 4-7 are reserved. |
| Ring | `ring` | The flush-dependency "ring" the entry belongs to, constraining flush order relative to entries in other rings: 1 = user data (outermost, flushed first) through 5 = superblock (innermost, flushed last). |
| Age | `age` | Number of file opens and closes since the entry was last accessed by the application. |
| Fd Child Count | `fd_child_count` | Number of flush-dependency children for which this entry is the parent. Nonzero only when `entry_flags` bit 2 is set. |
| Fd Dirty Child Count | `fd_dirty_child_count` | Number of the flush-dependency children counted in `fd_child_count` that were dirty when the image was generated. |
| Fd Parent Count | `fd_parent_count` | Number of flush-dependency parents for which this entry is a child. Nonzero only when `entry_flags` bit 3 is set, in which case that many parent addresses follow the fixed fields. |
| Lru Rank Raw | `lru_rank_raw` | Position on the cache's LRU list when `entry_flags` bit 1 is set (lower values are more recently used); otherwise the all-ones sentinel (-1). |
| Entry Address Raw | `entry_addr_raw` | File address at which the entry's metadata is, or will be, stored (`sizeof_offsets` bytes). Base-relative like any other HDF5 file address. |
| Entry Length Raw | `entry_length_raw` | Byte length of `entry_image` (`sizeof_lengths` bytes). |
| Parents | `parents` | File addresses of this entry's flush-dependency parents, one per `fd_parent_count`. Present only when `entry_flags` bit 3 is set. |
| Entry Image | `entry_image` | Byte-for-byte copy of the entry's serialized on-disk image, as it would otherwise appear at `entry_addr_raw` in the file (for example, the disk format of an object header or B-tree node). Exactly `entry_length_raw` bytes; not decoded by this pickle. |


## Flush-Dependency Parent Address

Pickle type: `mdci_parent_addr`.

One flush-dependency parent's file address, repeated once per `fd_parent_count` in an entry whose `entry_flags` bit 3 is set.

**Fields: Flush-Dependency Parent Address**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Address Raw | `addr_raw` | File address of a flush-dependency parent (`sizeof_offsets` bytes). |
