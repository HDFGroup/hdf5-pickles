# VII.C. The Fixed Array Index

<a id="subsec_fmt4_appendixc_fixedarr"></a>

Upstream: [HDF5 File Format Specification 4.0, section VII.C](https://support.hdfgroup.org/documentation/hdf5/latest/_f_m_t4.html#subsec_fmt4_appendixc_fixedarr) · Coverage: **Covered**

The Fixed Array (FA) is a chunk index used for datasets with a fixed
number of chunks — i.e. datasets whose every dimension is either fixed
in size or has at most one unlimited dimension that never grows beyond
a single chunk in that dimension.  It provides O(1) access to any chunk
by logical index.

Two on-disk structures are defined:

- **Header** (signature 'FAHD') — one per dataset; stores element
  geometry and the address of the data block.
- **Data Block** (signature 'FADB') — holds the actual chunk addresses
  (and, for filtered datasets, per-chunk metadata).

**Paging:** when the element count exceeds `2^max_dblk_page_nelmts_bits`
the data block is split into fixed-size pages stored consecutively after
the data block prefix in the file.  The prefix then records only the
page-initialisation bitmask; elements live in `fa_dblk_page` records.
When `max_dblk_page_nelmts_bits == 0` or the element count is small
enough, all elements are stored directly in the data block (`fadb_nopaged`).

**Client IDs:**

| ID | Name                  | Element layout                                          |
|----|-----------------------|---------------------------------------------------------|
| 0  | H5FA_CLS_CHUNK_ID     | `sizeof_offsets`-byte chunk file address                |
| 1  | H5FA_CLS_FILT_CHUNK_ID| chunk address + filtered size + 4-byte filter mask     |

Use `print_fa(addr#B)` to map the header, print it, and recursively
print the data block and all pages.

The decoder verifies the lookup3 checksum on the header, each data-block
prefix, and every data-block page.

## Fixed Array Header

Pickle type: `fa_hdr`.

Fixed Array header (signature 'FAHD'). Describes the element type and geometry of the entire fixed array. Mapping this struct automatically sets all `global_fa_*` parameters via constraint side-effects so that the data block and pages can be mapped immediately afterwards.

**Layout: Fixed Array Header**

<table class="format-layout">
  <thead><tr><th>byte</th><th>byte</th><th>byte</th><th>byte</th></tr></thead>
  <tbody>
    <tr><td colspan="4">Signature</td></tr>
    <tr><td>Version</td><td>Client ID</td><td>Element Size</td><td>Max. Page Elements Bits</td></tr>
    <tr><td colspan="4">Number of Elements<sup>L</sup></td></tr>
    <tr><td colspan="4">Data Block Address<sup>O</sup></td></tr>
    <tr><td colspan="4">Checksum</td></tr>
  </tbody>
</table>

`O` is the size of offsets; `L` is the size of lengths.

**Fields: Fixed Array Header**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Signature | `signature` | 4-byte signature: 'F' 'A' 'H' 'D'. Must match exactly. |
| Version | `version` | Header format version. Must be 0. |
| Client ID | `client_id` | Element class: 0 = non-filtered chunk addresses, 1 = filtered chunk addresses. |
| Raw Elmt Size | `raw_elmt_size` | On-disk size in bytes of each array element. For client ID 0 this equals `sizeof_offsets`; for client ID 1 it equals `sizeof_offsets + chunk_size_len + 4`. |
| Max Dblk Page Nelmts Bits | `max_dblk_page_nelmts_bits` | Log₂ of the maximum number of elements per data block page. 0 means paging is disabled and all elements are stored inline in the data block. |
| Nelmts Raw | `nelmts_raw` | Total number of elements (chunks) indexed by this fixed array (`sizeof_lengths` bytes). |
| Dblk Address Raw | `dblk_addr_raw` | File address of the associated data block (`sizeof_offsets` bytes). |
| Chksum | `chksum` | Jenkins lookup3 checksum of all preceding header bytes. |


## Fixed Array Data Block

Pickle type: `fa_dblock`.

Top-level Fixed Array data block dispatch union (signature 'FADB'). Selects `fadb_paged` when `global_fa_npages > 0`, otherwise `fadb_nopaged`. Map with `var db = fa_dblock @ bytes_to_off(hdr.dblk_addr_raw)`.

### Paged

Pickle union arm: `paged`.

Paged prefix layout. Active when `global_fa_npages > 0`.

### Nopaged

Pickle union arm: `nopaged`.

Inline element layout. Active when `global_fa_npages == 0`.


## Non-paged Fixed Array Data Block

Pickle type: `fadb_nopaged`.

Fixed Array data block, non-paged layout (signature 'FADB'). Used when `global_fa_npages == 0`. All `global_fa_nelmts` elements are stored inline in the `elements` array.

**Fields: Non-paged Fixed Array Data Block**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Signature | `signature` | 4-byte signature: 'F' 'A' 'D' 'B'. Must match exactly. |
| Version | `version` | Data block format version. Must be 0. |
| Client ID | `client_id` | Element class (mirrors `fa_hdr.client_id`). |
| Header Address Raw | `hdr_addr_raw` | Back-pointer: file address of the Fixed Array header (`sizeof_offsets` bytes). |
| Elements | `elements` | Array of `global_fa_nelmts` inline elements (type `fadb_element`). |
| Chksum | `chksum` | Jenkins lookup3 checksum of all preceding data block bytes. |


## Paged Fixed Array Data Block

Pickle type: `fadb_paged`.

Fixed Array data block, paged layout (signature 'FADB'). Used when `global_fa_npages > 0`. This struct captures only the prefix; the actual elements are stored in `fa_dblk_page` records that follow immediately in the file. The page-initialisation bitmask tracks which pages have been written.

**Fields: Paged Fixed Array Data Block**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Signature | `signature` | 4-byte signature: 'F' 'A' 'D' 'B'. Must match exactly. |
| Version | `version` | Data block format version. Must be 0. |
| Client ID | `client_id` | Element class (mirrors `fa_hdr.client_id`). |
| Header Address Raw | `hdr_addr_raw` | Back-pointer: file address of the Fixed Array header (`sizeof_offsets` bytes). |
| Page Init Flags | `page_init_flags` | Page-initialisation bitmask (`global_fa_dblk_page_init_size` bytes = ⌈npages / 8⌉). Bit i is set when page i has been written to disk. |
| Chksum | `chksum` | Jenkins lookup3 checksum of all bytes from `signature` through `page_init_flags`. |


## Fixed Array Data Block Page

Pickle type: `fa_dblk_page`.

Fixed Array data block page. Only present when paging is active (`global_fa_npages > 0`). Pages have no on-disk signature; they are stored consecutively immediately after the data block prefix. All full pages hold `global_fa_dblk_page_nelmts` elements; the final page may hold fewer (`global_fa_last_page_nelmts`). Override `global_fa_page_nelmts` with `set_fa_page_nelmts(n)` before mapping the last page, then restore it with `reset_fa_page_nelmts`.

**Fields: Fixed Array Data Block Page**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Elements | `elements` | Array of `global_fa_page_nelmts` elements (type `fadb_element`). |
| Chksum | `chksum` | Jenkins lookup3 checksum of all preceding page bytes. |


## Fixed Array Data Block Element

Pickle type: `fadb_element`.

Dispatch union that resolves to the correct element layout based on `global_fa_client_id` at mapping time. Both arms have the same on-disk footprint (`raw_elmt_size` bytes) for a given header.

### Non Filtered

Pickle union arm: `non_filtered`.

Active when `global_fa_client_id == 0`. Wraps `fadb_chunk_elem`.

### Filtered

Pickle union arm: `filtered`.

Active when `global_fa_client_id == 1`. Wraps `fadb_filt_chunk_elem`.


## Non-filtered Dataset Chunk Element

Pickle type: `fadb_chunk_elem`.

One element for a non-filtered chunk (client ID 0). Contains only the chunk's file address.

**Fields: Non-filtered Dataset Chunk Element**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Address Raw | `addr_raw` | File address of the chunk data (`sizeof_offsets` bytes). HADDR_UNDEF if the chunk has not been written. |


## Filtered Dataset Chunk Element

Pickle type: `fadb_filt_chunk_elem`.

One element for a filtered chunk (client ID 1). Stores the chunk address, its on-disk (post-filter) size, and the filter pipeline skip mask.

**Fields: Filtered Dataset Chunk Element**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Address Raw | `addr_raw` | File address of the filtered chunk data (`sizeof_offsets` bytes). |
| Chunk Size Raw | `chunk_size_raw` | On-disk (filtered) size of the chunk in bytes (`global_fa_chunk_size_len` bytes = `raw_elmt_size − sizeof_offsets − 4`). |
| Filter Mask | `filter_mask` | Filter pipeline skip mask. Bit i set means filter i was not applied to this chunk. |
