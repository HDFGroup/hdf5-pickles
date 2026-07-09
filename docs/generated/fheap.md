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

This pickle currently types the Fractal Heap header (signature 'FRHP')
and the embedded doubling-table parameters. Direct blocks (signature
'FHDB'), indirect blocks (signature 'FHIB'), and heap ID payloads are
decoded by callers with explicit offset arithmetic using the geometry
exposed by `frhp_dtable`.

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


