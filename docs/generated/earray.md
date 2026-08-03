# VII.D. The Extensible Array Index

<a id="subsec_fmt4_appendixc_extarr"></a>

Upstream: [HDF5 File Format Specification 4.0, section VII.D](https://support.hdfgroup.org/documentation/hdf5/latest/_f_m_t4.html#subsec_fmt4_appendixc_extarr) · Coverage: **Covered**

The Extensible Array (EA) is a chunk index used for datasets with
exactly one unlimited dimension.  Unlike the Fixed Array it can grow
in one direction without rebuilding the entire index.

The structure is a four-level hierarchy:

```
Header (EAHD)
  └─ Index Block (EAIB)
       ├─ direct elements          (first idx_blk_elmts chunks)
       ├─ direct data block addresses   (first iblk_nsblks secondary groups)
       └─ secondary block addresses     (remaining secondary groups)
            └─ Secondary Block (EASB)
                 └─ Data Block addresses
                      └─ Data Block (EADB)
                           └─ [Data Block Pages]  (when paged)
```

Data blocks are organised into *secondary block groups* indexed by u = 0, 1, 2, …:

| Group u | Data blocks in group | Elements per data block         |
|---------|----------------------|---------------------------------|
| u       | 2^(u/2)              | 2^((u+1)/2) × data_blk_min_elmts |

The first `iblk_nsblks = 2 × log2(sup_blk_min_data_ptrs)` secondary
block groups have their data block addresses stored directly in the
index block.  The remaining groups are managed via separate Secondary
Block structures.

**Paging:** when a data block's element count exceeds
`2^max_dblk_page_nelmts_bits`, elements are stored in separate data
block pages appended immediately after the data block prefix in the
file.  All pages within one data block hold the same number of elements.

**Client IDs:**

| ID | Name                   | Element layout                                         |
|----|------------------------|--------------------------------------------------------|
| 0  | H5EA_CLS_CHUNK_ID      | `sizeof_offsets`-byte chunk file address               |
| 1  | H5EA_CLS_FILT_CHUNK_ID | chunk address + filtered size + 4-byte filter mask    |

Use `print_ea(addr#B)` to map the header, print it and the index block,
and recursively walk all reachable data blocks and secondary blocks.

## Extensible Array Header

Pickle type: `ea_hdr`.

Extensible Array header (signature 'EAHD'). Stores the element type and all structural parameters of the array. Mapping this struct sets all `global_ea_*` parameters via constraint side-effects, including the derived counts `iblk_nsblks`, `ndblk_addrs`, `nsblk_addrs`, `arr_off_size`, and `dblk_page_nelmts`.

**Layout: Extensible Array Header**

<table class="format-layout">
  <thead><tr><th>byte</th><th>byte</th><th>byte</th><th>byte</th></tr></thead>
  <tbody>
    <tr><td colspan="4">Signature</td></tr>
    <tr><td>Version</td><td>Client ID</td><td>Element Size</td><td>Max. Elements Bits</td></tr>
    <tr><td>Index Block Elements</td><td>Min. Data Block Elements</td><td>Min. Secondary Block Pointers</td><td>Max. Page Elements Bits</td></tr>
    <tr><td colspan="4">Number of Secondary Blocks<sup>L</sup></td></tr>
    <tr><td colspan="4">Secondary Block Size<sup>L</sup></td></tr>
    <tr><td colspan="4">Number of Data Blocks<sup>L</sup></td></tr>
    <tr><td colspan="4">Data Block Size<sup>L</sup></td></tr>
    <tr><td colspan="4">Maximum Index Set<sup>L</sup></td></tr>
    <tr><td colspan="4">Number of Elements<sup>L</sup></td></tr>
    <tr><td colspan="4">Index Block Address<sup>O</sup></td></tr>
    <tr><td colspan="4">Checksum</td></tr>
  </tbody>
</table>

`O` is the size of offsets; `L` is the size of lengths.

**Fields: Extensible Array Header**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Signature | `signature` | 4-byte signature: 'E' 'A' 'H' 'D'. Must match exactly. |
| Version | `version` | Header format version. Must be 0. |
| Client ID | `client_id` | Element class: 0 = non-filtered chunk addresses, 1 = filtered chunk addresses. |
| Raw Elmt Size | `raw_elmt_size` | On-disk size in bytes of each array element. |
| Max Nelmts Bits | `max_nelmts_bits` | Log₂ of the maximum number of elements the array can hold. Determines `arr_off_size = ⌈max_nelmts_bits / 8⌉`, the byte width used to encode array element offsets. |
| Index Blk Elmts | `idx_blk_elmts` | Number of elements stored directly in the index block (the lowest-index chunks are stored here to avoid allocating data blocks for small datasets). |
| Data Blk Min Elmts | `data_blk_min_elmts` | Minimum number of elements per data block (must be a power of two). Controls the element count per data block via `dblk_nelmts[u] = 2^((u+1)/2) × data_blk_min_elmts`. |
| Sup Blk Min Data Ptrs | `sup_blk_min_data_ptrs` | Minimum number of data block pointers in a secondary block (must be a power of two). Controls the layout of the index block via `iblk_nsblks = 2 × log2(sup_blk_min_data_ptrs)`. |
| Max Dblk Page Nelmts Bits | `max_dblk_page_nelmts_bits` | Log₂ of the maximum number of elements per data block page. 0 means paging is disabled. |
| Nsuper Blks Raw | `nsuper_blks_raw` | Total number of secondary blocks allocated (`sizeof_lengths` bytes). |
| Superblock Blk Size Raw | `super_blk_size_raw` | Total bytes consumed by all secondary blocks (`sizeof_lengths` bytes). |
| Ndata Blks Raw | `ndata_blks_raw` | Total number of data blocks allocated (`sizeof_lengths` bytes). |
| Data Blk Size Raw | `data_blk_size_raw` | Total bytes consumed by all data blocks (`sizeof_lengths` bytes). |
| Max Index Set Raw | `max_idx_set_raw` | Highest element index that has been set (`sizeof_lengths` bytes). |
| Nelmts Raw | `nelmts_raw` | Total number of elements currently stored in the array (`sizeof_lengths` bytes). |
| Index Blk Address Raw | `idx_blk_addr_raw` | File address of the index block (`sizeof_offsets` bytes). |
| Chksum | `chksum` | Jenkins lookup3 checksum of all preceding header bytes. |


## Extensible Array Index Block

Pickle type: `ea_iblock`.

Extensible Array index block (signature 'EAIB'). Central dispatch structure. Holds the first `idx_blk_elmts` elements directly, then `ndblk_addrs` data block addresses for the first `iblk_nsblks` secondary block groups, then `nsblk_addrs` secondary block addresses for the remaining groups.

**Fields: Extensible Array Index Block**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Signature | `signature` | 4-byte signature: 'E' 'A' 'I' 'B'. Must match exactly. |
| Version | `version` | Index block format version. Must be 0. |
| Client ID | `client_id` | Element class (mirrors `ea_hdr.client_id`). |
| Header Address Raw | `hdr_addr_raw` | Back-pointer: file address of the Extensible Array header (`sizeof_offsets` bytes). |
| Elements | `elements` | Array of `global_ea_idx_blk_elmts` elements stored inline (type `eadb_element`). These are the lowest-index chunks and are accessed without following any data block pointer. |
| Dblk Addrs | `dblk_addrs` | `global_ea_ndblk_addrs × sizeof_offsets` byte array of data block file addresses. Entries are grouped by secondary block group u; within group u there are `2^(u/2)` addresses. HADDR_UNDEF entries indicate unallocated data blocks. |
| Sblk Addrs | `sblk_addrs` | `global_ea_nsblk_addrs × sizeof_offsets` byte array of secondary block file addresses for groups u = iblk_nsblks … nsblks−1. HADDR_UNDEF entries indicate unallocated secondary blocks. |
| Chksum | `chksum` | Jenkins lookup3 checksum of all preceding index block bytes. |


## Extensible Array Secondary Block

Pickle type: `ea_sblock`.

Extensible Array secondary block (signature 'EASB'). Manages the data blocks for one secondary block group u. Before mapping, call `set_ea_sblock_idx(u)` to configure `global_ea_sblk_ndblks`, `global_ea_sblk_dblk_nelmts`, `global_ea_sblk_dblk_npages`, and `global_ea_sblk_total_page_init_size`.

**Fields: Extensible Array Secondary Block**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Signature | `signature` | 4-byte signature: 'E' 'A' 'S' 'B'. Must match exactly. |
| Version | `version` | Secondary block format version. Must be 0. |
| Client ID | `client_id` | Element class (mirrors `ea_hdr.client_id`). |
| Header Address Raw | `hdr_addr_raw` | Back-pointer: file address of the Extensible Array header (`sizeof_offsets` bytes). |
| Block Off Raw | `block_off_raw` | Array-element offset of the first element reachable via this secondary block (`global_ea_arr_off_size` bytes = ⌈max_nelmts_bits / 8⌉). |
| Page Init Flags | `page_init_flags` | Page-initialisation bitmask for the data blocks managed by this secondary block (`global_ea_sblk_total_page_init_size` bytes = `ndblks × ⌈dblk_npages / 8⌉`). Zero-length when the data blocks in this group are not paged. |
| Dblk Addrs | `dblk_addrs` | `global_ea_sblk_ndblks × sizeof_offsets` byte array of data block file addresses for this secondary block group. HADDR_UNDEF entries indicate unallocated data blocks. |
| Chksum | `chksum` | Jenkins lookup3 checksum of all preceding secondary block bytes. |


## Extensible Array Data Block

Pickle type: `ea_dblock`.

Top-level Extensible Array data block dispatch union (signature 'EADB'). Selects `eadb_paged` when `global_ea_dblk_npages > 0`, otherwise `eadb_nopaged`. Map with `set_ea_dblock(nelmts)` then `var db = ea_dblock @ addr#B`.

### Paged

Pickle union arm: `paged`.

Paged prefix layout. Active when `global_ea_dblk_npages > 0`.

### Nopaged

Pickle union arm: `nopaged`.

Inline element layout. Active when `global_ea_dblk_npages == 0`.


## Non-paged Extensible Array Data Block

Pickle type: `eadb_nopaged`.

Extensible Array data block, non-paged layout (signature 'EADB'). Used when `global_ea_dblk_npages == 0`. All `global_ea_dblk_nelmts` elements are stored inline after the block header. Before mapping, call `set_ea_dblock(nelmts)` with the element count for this particular data block.

**Fields: Non-paged Extensible Array Data Block**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Signature | `signature` | 4-byte signature: 'E' 'A' 'D' 'B'. Must match exactly. |
| Version | `version` | Data block format version. Must be 0. |
| Client ID | `client_id` | Element class (mirrors `ea_hdr.client_id`). |
| Header Address Raw | `hdr_addr_raw` | Back-pointer: file address of the Extensible Array header (`sizeof_offsets` bytes). |
| Block Off Raw | `block_off_raw` | Array-element offset of the first element in this data block (`global_ea_arr_off_size` bytes). |
| Elements | `elements` | Array of `global_ea_dblk_nelmts` inline elements (type `eadb_element`). |
| Chksum | `chksum` | Jenkins lookup3 checksum of all preceding data block bytes. |


## Paged Extensible Array Data Block

Pickle type: `eadb_paged`.

Extensible Array data block, paged layout (signature 'EADB'). Used when `global_ea_dblk_npages > 0`. Captures only the block prefix; elements are in `ea_dblk_page` records that follow the prefix consecutively in the file. Before mapping, call `set_ea_dblock(nelmts)`.

**Fields: Paged Extensible Array Data Block**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Signature | `signature` | 4-byte signature: 'E' 'A' 'D' 'B'. Must match exactly. |
| Version | `version` | Data block format version. Must be 0. |
| Client ID | `client_id` | Element class (mirrors `ea_hdr.client_id`). |
| Header Address Raw | `hdr_addr_raw` | Back-pointer: file address of the Extensible Array header (`sizeof_offsets` bytes). |
| Block Off Raw | `block_off_raw` | Array-element offset of the first element in this data block (`global_ea_arr_off_size` bytes). |
| Chksum | `chksum` | Jenkins lookup3 checksum of all bytes from `signature` through `block_off_raw`. |


## Extensible Array Data Block Page

Pickle type: `ea_dblk_page`.

Extensible Array data block page. No on-disk signature; pages are appended consecutively to a paged data block prefix. Every page within one data block holds exactly `global_ea_dblk_page_nelmts` elements (data block sizes always divide evenly into pages). Map with `var pg = ea_dblk_page @ page_offset#B`.

**Fields: Extensible Array Data Block Page**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Elements | `elements` | Array of `global_ea_dblk_page_nelmts` elements (type `eadb_element`). |
| Chksum | `chksum` | Jenkins lookup3 checksum of all preceding page bytes. |


## Extensible Array Data Block Element

Pickle type: `eadb_element`.

Dispatch union that resolves to the correct element layout based on `global_ea_client_id` at mapping time.

### Non Filtered

Pickle union arm: `non_filtered`.

Active when `global_ea_client_id == 0`. Wraps `eadb_chunk_elem`.

### Filtered

Pickle union arm: `filtered`.

Active when `global_ea_client_id == 1`. Wraps `eadb_filt_chunk_elem`.

### Testing

Pickle union arm: `testing`.

Active when `global_ea_client_id == 2`. Wraps `eadb_chunk_elem`. Added for compatibility with internal EA test files only; not part of the public format specification.


## Non-filtered Dataset Chunk Element

Pickle type: `eadb_chunk_elem`.

One element for a non-filtered chunk (client ID 0). Contains only the chunk's file address.

**Fields: Non-filtered Dataset Chunk Element**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Address Raw | `addr_raw` | File address of the chunk data (`sizeof_offsets` bytes). HADDR_UNDEF if the chunk has not been written. |


## Filtered Dataset Chunk Element

Pickle type: `eadb_filt_chunk_elem`.

One element for a filtered chunk (client ID 1). Records the chunk address, its on-disk (post-filter) size, and the filter pipeline skip mask.

**Fields: Filtered Dataset Chunk Element**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Address Raw | `addr_raw` | File address of the filtered chunk data (`sizeof_offsets` bytes). |
| Chunk Size Raw | `chunk_size_raw` | On-disk (filtered) size of the chunk in bytes (`global_ea_chunk_size_len` bytes = `raw_elmt_size − sizeof_offsets − 4`). |
| Filter Mask | `filter_mask` | Filter pipeline skip mask. Bit i set means filter i was not applied to this chunk. |
