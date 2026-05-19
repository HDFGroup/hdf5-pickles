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

This pickle types the Fractal Heap header (signature 'FRHP'), the
embedded doubling-table parameters, indirect blocks (signature 'FHIB'),
direct blocks (signature 'FHDB'), and heap ID payloads. Mapping a header
populates the global geometry used by the block and ID decoders.

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


## `frhp_dir_entry`

Direct-block child entry for an unfiltered heap indirect block. The entry contains only the child direct block's file address.

| Field | Description |
|-------|-------------|
| `addr_raw` | File address of the child direct block (`sizeof_offsets` bytes). HADDR_UNDEF indicates that the child block has not been allocated. |


## `frhp_dir_entry_filt`

Direct-block child entry for a filtered heap indirect block. In addition to the child address, the entry stores the filtered direct block's on-disk size and filter skip mask.

| Field | Description |
|-------|-------------|
| `addr_raw` | File address of the child direct block (`sizeof_offsets` bytes). HADDR_UNDEF indicates that the child block has not been allocated. |
| `filtered_size_raw` | On-disk size of the filtered child direct block, stored in `sizeof_lengths` bytes. |
| `filter_mask` | Filter pipeline skip mask for this filtered direct block. |


## `frhp_iblock_dir_entry`

Dispatch union for a direct-block child entry inside an indirect block. The filtered arm is selected when the heap has a nonzero `filter_len`; otherwise the unfiltered address-only form is used.

### `filtered`

Active when `global_frhp_filter_len > 0`. Wraps `frhp_dir_entry_filt`.

### `unfiltered`

Active when `global_frhp_filter_len == 0`. Wraps `frhp_dir_entry`.


## `frhp_hdr`

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


## `frhp_iblock`

Fractal Heap indirect block (signature 'FHIB'). Map only after calling `set_frhp_iblock(nrows)`, which derives the direct and indirect child entry counts for this block.

| Field | Description |
|-------|-------------|
| `signature` | 4-byte signature: 'F' 'H' 'I' 'B'. Must match exactly. |
| `version` | Indirect block format version. Must be 0. |
| `hdr_addr_raw` | Back-pointer: file address of the Fractal Heap header (`sizeof_offsets` bytes). |
| `block_off_raw` | Logical heap offset of this indirect block in the managed heap address space (`global_frhp_heap_off_size` bytes). |
| `dir_entries` | Array of direct-block child entries. The count is `global_frhp_iblock_ndir_entries`, and each entry uses `frhp_iblock_dir_entry`. |
| `indir_addrs` | Array of child indirect-block addresses for rows beyond the direct-block rows. The count is `global_frhp_iblock_nindir_entries`; each address is `sizeof_offsets` bytes. |
| `chksum` | Jenkins lookup3 checksum of all preceding indirect block bytes. |


## `frhp_dblock`

Fractal Heap direct block (signature 'FHDB'). Map only after calling `set_frhp_dblock(block_size)`, which derives the payload byte count from the block size and heap header geometry.

| Field | Description |
|-------|-------------|
| `signature` | 4-byte signature: 'F' 'H' 'D' 'B'. Must match exactly. |
| `version` | Direct block format version. Must be 0. |
| `hdr_addr_raw` | Back-pointer: file address of the Fractal Heap header (`sizeof_offsets` bytes). |
| `block_off_raw` | Logical heap offset of this direct block in the managed heap address space (`global_frhp_heap_off_size` bytes). |
| `chksum` | Jenkins lookup3 checksum for the entire direct block, computed with this field zeroed. Present only when the heap header's checksum-direct-blocks flag is set. _optional_ |
| `data` | Managed object payload bytes. The array length is `global_frhp_dblock_data_size`. |


## `frhp_heap_id`

Raw Fractal Heap object ID. Map only after the corresponding `frhp_hdr`, so `global_frhp_id_len` and the derived managed, huge, and tiny ID widths are available. The first byte encodes version bits, object type bits, and, for tiny objects, part of the inline object length.

| Field | Description |
|-------|-------------|
| `raw` | `global_frhp_id_len` bytes containing a managed, huge, or tiny heap ID. Managed IDs encode a logical heap offset and object length; huge IDs encode either an inline address/size tuple or a version 2 B-tree key; tiny IDs embed the object bytes inline. |


