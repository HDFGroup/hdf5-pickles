# III.G. Disk Format: Level 1G - Fractal Heap

Fractal heaps store variable-length metadata objects for dense links,
dense attributes, shared messages, and other HDF5 structures that need
compact object IDs plus scalable lookup.

A heap stores objects in three broad forms:

- **Managed objects** live inside fractal-heap direct blocks. Their
  heap IDs encode a logical heap offset and length; the doubling table
  maps that logical offset to the containing direct block.
- **Huge objects** are stored separately in the file and indexed by a
  version 2 B-tree rooted at `huge_btree_addr_raw`.
- **Tiny objects** are embedded directly in the heap ID, so no heap
  block lookup is needed.

This pickle types the Fractal Heap header (signature 'FRHP') with its
embedded doubling-table parameters, the direct blocks (signature 'FHDB')
and indirect blocks (signature 'FHIB') that hold managed objects, the
indirect-block child entries, and the heap ID payload. Locating a
managed object requires the doubling-table geometry exposed by
`frhp_dtable`, which drives the offset arithmetic in
`frhp_managed_id_to_addr`.

**Layout: Fractal Heap Header**

<table class="format-layout">
  <thead><tr><th>byte</th><th>byte</th><th>byte</th><th>byte</th></tr></thead>
  <tbody>
    <tr><td colspan="4">Signature</td></tr>
    <tr><td>Version</td><td colspan="2">Heap ID Length</td><td>Filter Length (low byte)</td></tr>
    <tr><td>Filter Length (high byte)</td><td>Flags</td><td colspan="2">Maximum Managed Object Size</td></tr>
    <tr><td colspan="2">Maximum Managed Object Size (continued)</td><td colspan="2">Next Huge Object ID<sup>L</sup></td></tr>
    <tr><td colspan="4">Next Huge Object ID (continued)<sup>L</sup></td></tr>
    <tr><td colspan="4">Huge Object B-tree Address<sup>O</sup></td></tr>
    <tr><td colspan="4">Free Managed Space<sup>L</sup></td></tr>
    <tr><td colspan="4">Free-space Manager Address<sup>O</sup></td></tr>
    <tr><td colspan="4">Managed-space Statistics and Doubling Table</td></tr>
    <tr><td colspan="4">Optional Filter Information</td></tr>
    <tr><td colspan="4">Checksum</td></tr>
  </tbody>
</table>

Rows containing variable-width fields are schematic. `O` is the size of offsets; `L` is the size of lengths.

## `frhp_dtable`

Doubling-table geometry embedded in every fractal heap header. It describes how logical heap offsets are mapped onto root direct or indirect blocks, and how indirect block rows grow.

| Field | Description |
|-------|-------------|
| `table_width` | Number of block entries in each row of an indirect block. |
| `start_block_size_raw` | Starting direct block size, stored in `sizeof_lengths` bytes. Blocks in the first two rows use this size before later rows double. |
| `max_direct_size_raw` | Maximum size of any direct block in the heap, stored in `sizeof_lengths` bytes. |
| `max_heap_size_bits` | Maximum heap size, encoded as the number of bits needed to represent logical offsets in the heap address space. |
| `starting_root_rows` | Initial row count allocated for the root indirect block. |
| `root_addr_raw` | File address of the root block (`sizeof_offsets` bytes). The root is a direct block when `curr_root_rows == 0`, otherwise an indirect block. |
| `curr_root_rows` | Current number of rows in the root indirect block. A value of 0 means the root address points directly at a root direct block. |


## `fheap_hdr`

Fractal Heap header (signature 'FRHP'). Stores heap-wide counters, addresses for huge-object and free-space tracking, and the doubling-table parameters used to locate managed objects.

| Field | Description |
|-------|-------------|
| `signature` | 4-byte signature: 'F' 'R' 'H' 'P'. Must match exactly. |
| `version` | Header format version. Must be 0. |
| `heap_id_length` | Length in bytes of heap object IDs generated for this heap. |
| `filter_len` | Encoded byte length of the heap's I/O filter information. When this is zero, the filtered-root metadata fields are absent. |
| `flags` | Heap status flags. Bit 0 indicates that the huge-object ID counter has wrapped; bit 1 indicates that direct blocks in this heap carry checksums. Bits 2-7 are reserved. |
| `max_man_size` | Maximum object size, in bytes, that may be stored as a managed object inside direct blocks. Larger objects are huge objects. |
| `next_huge_id_raw` | Next huge-object ID value to allocate, stored in `sizeof_lengths` bytes. |
| `huge_btree_addr_raw` | File address of the version 2 B-tree that indexes huge objects for this heap (`sizeof_offsets` bytes). |
| `free_managed_space_raw` | Amount of free space currently available in managed direct blocks, stored in `sizeof_lengths` bytes. |
| `free_space_mgr_addr_raw` | File address of the free-space manager used for managed block free space (`sizeof_offsets` bytes). |
| `managed_space_raw` | Total logical managed heap space represented by allocated direct and indirect blocks, stored in `sizeof_lengths` bytes. |
| `alloc_managed_space_raw` | Total file space allocated for managed heap blocks, stored in `sizeof_lengths` bytes. |
| `managed_alloc_iter_raw` | Logical heap offset of the direct-block allocation iterator in managed space, stored in `sizeof_lengths` bytes. |
| `managed_obj_count_raw` | Number of managed objects stored in direct blocks, stored in `sizeof_lengths` bytes. |
| `huge_size_raw` | Total size in bytes of huge objects stored for this heap, stored in `sizeof_lengths` bytes. |
| `huge_count_raw` | Number of huge objects stored for this heap (`sizeof_lengths` bytes). |
| `tiny_size_raw` | Total size in bytes of tiny objects embedded in heap IDs, stored in `sizeof_lengths` bytes. |
| `tiny_count_raw` | Number of tiny objects stored for this heap (`sizeof_lengths` bytes). |
| `dtable` | Embedded `frhp_dtable` describing the managed-block doubling table. |
| `filtered_root_dblock_size_raw` | Size of the filtered root direct block, stored in `sizeof_lengths` bytes. Present only when `filter_len != 0`. _optional_ |
| `io_filter_mask` | Filter pipeline skip mask for the filtered root direct block. Present only when `filter_len != 0`. _optional_ |
| `io_filter_info` | Encoded I/O filter information bytes for root direct blocks. The array length is `filter_len`, and the field is present only when `filter_len != 0`. _optional_ |
| `chksum` | Jenkins lookup3 checksum of all preceding header bytes. |


## `frhp_dir_entry`

Direct-block child entry in an indirect block, unfiltered heap. Rows below `max_direct_rows` hold direct-block entries; this variant is used when the heap has no I/O filter pipeline.

| Field | Description |
|-------|-------------|
| `addr_raw` | File address of the child direct block (`sizeof_offsets` bytes). An all-ones (undefined) address marks an unallocated entry. |


## `frhp_dir_entry_filt`

Direct-block child entry in an indirect block, filtered heap. Used in place of `frhp_dir_entry` when `filter_len != 0`, adding the stored (filtered) block size and the filter skip mask.

| Field | Description |
|-------|-------------|
| `addr_raw` | File address of the child direct block (`sizeof_offsets` bytes). An all-ones (undefined) address marks an unallocated entry. |
| `filtered_size_raw` | On-disk size of the filtered direct block, stored in `sizeof_lengths` bytes. |
| `filter_mask` | Bit mask of filters skipped for this direct block, matching the filter pipeline convention (1 = filter not applied). |


## `frhp_iblock_dir_entry`

Direct-block child entry, selecting the filtered layout when the heap carries an I/O filter pipeline (`filter_len > 0`) and the plain address-only layout otherwise.

### `filtered`

`frhp_dir_entry_filt` — chosen when `filter_len > 0`.

### `unfiltered`

`frhp_dir_entry` — chosen when the heap is unfiltered.


## `fheap_iblock`

Fractal Heap indirect block (signature 'FHIB'). Holds the child entries for one node of the doubling table: direct-block entries for rows below `max_direct_rows`, followed by indirect-block addresses for the remaining rows. Call `set_frhp_iblock(nrows)` before mapping.

| Field | Description |
|-------|-------------|
| `signature` | 4-byte signature: 'F' 'H' 'I' 'B'. Must match exactly. |
| `version` | Indirect block format version. Must be 0. |
| `hdr_addr_raw` | File address of the fractal heap header that owns this block (`sizeof_offsets` bytes). |
| `block_off_raw` | Logical heap offset of the first object mapped by this block, stored in `heap_off_size` bytes. |
| `dir_entries` | Array of direct-block child entries (`frhp_iblock_dir_entry`), one per direct-block slot in this block's rows. |
| `indir_addrs` | Array of child indirect-block file addresses (`sizeof_offsets` bytes each) for rows at or above `max_direct_rows`. |
| `chksum` | Jenkins lookup3 checksum over the indirect block. |


## `fheap_dblock`

Fractal Heap direct block (signature 'FHDB'). Stores the managed objects themselves in its `data` region. Call `set_frhp_dblock(block_size)` before mapping so the data length can be derived from the block size.

| Field | Description |
|-------|-------------|
| `signature` | 4-byte signature: 'F' 'H' 'D' 'B'. Must match exactly. |
| `version` | Direct block format version. Must be 0. |
| `hdr_addr_raw` | File address of the fractal heap header that owns this block (`sizeof_offsets` bytes). |
| `block_off_raw` | Logical heap offset of the first object in this block, stored in `heap_off_size` bytes. |
| `chksum` | Jenkins lookup3 checksum over the entire block (computed with this field zeroed). Present only when the header's checksum-direct-blocks flag is set. _optional_ |
| `data` | Managed object data region, `block_size` minus the block overhead bytes long. Objects are packed at heap-offset positions decoded from their heap IDs. |


## `frhp_heap_id`

Fractal Heap ID (`heap_id_length` bytes). The first byte's type bits select one of three payload forms: managed (offset/length into the heap's direct blocks), huge (direct address or v2 B-tree key), or tiny (object bytes embedded in the ID). `fheap_hdr` must be mapped first so the derived geometry globals are set.

| Field | Description |
|-------|-------------|
| `raw` | The raw ID bytes (`heap_id_length` long). The `_print` method decodes the flags byte and the form-specific fields. |
