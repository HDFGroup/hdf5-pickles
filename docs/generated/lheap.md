# III.D. Disk Format: Level 1D - Local Heaps

<a id="subsec_fmt4_infra_localheap"></a>

Upstream: [HDF5 File Format Specification 4.0, section III.D](https://support.hdfgroup.org/documentation/hdf5/latest/_f_m_t4.html#subsec_fmt4_infra_localheap) · Coverage: **Covered**

A local heap stores the small, variable-length objects that a single
HDF5 object needs kept together — most commonly the null-terminated
link-name strings of a legacy (symbol-table) group. The heap is made of
two parts: a fixed-size header (signature 'HEAP') and a separately
allocated data segment whose file address is recorded in the header.

The data segment holds null-terminated strings, each padded with
trailing zeros to an 8-byte boundary. Byte 0 of the segment is always a
null byte serving as the empty-string sentinel. Unused regions are
chained into a singly-linked free list; each free block records the
offset of the next free block and its own size. Two sentinels mark the
end of the list: an all-ones (undefined) value and the value 1
(`H5HL_FREE_NULL`).

All fields are stored in little-endian byte order.

## Local Heap

Pickle type: `lheap_hdr`.

Local heap header (signature 'HEAP'). Records the size and file address of the data segment and the head of its free list. The total header size is `8 + 2 × sizeof_lengths + sizeof_offsets` bytes.

**Layout: Local Heap Header**

<table class="format-layout">
  <thead><tr><th>byte</th><th>byte</th><th>byte</th><th>byte</th></tr></thead>
  <tbody>
    <tr><td colspan="4">Signature</td></tr>
    <tr><td>Version</td><td colspan="3">Reserved</td></tr>
    <tr><td colspan="4">Data Segment Size<sup>L</sup></td></tr>
    <tr><td colspan="4">Free-list Head Offset<sup>L</sup></td></tr>
    <tr><td colspan="4">Data Segment Address<sup>O</sup></td></tr>
  </tbody>
</table>

`O` is the size of offsets; `L` is the size of lengths.

**Fields: Local Heap**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Signature | `signature` | 4-byte signature: 'H' 'E' 'A' 'P'. Must match exactly. |
| Version | `version` | Local heap version. Must be 0. |
| Reserved | `reserved` | Reserved. Must be zero (3 bytes). |
| Data Seg Size Raw | `data_seg_size_raw` | Total number of bytes allocated for the data segment (`sizeof_lengths` bytes). |
| Free List Head Raw | `free_list_head_raw` | Data-segment byte offset of the first free block (`sizeof_lengths` bytes). An all-ones (undefined) value or 1 indicates that the heap has no free blocks. |
| Data Seg Address Raw | `data_seg_addr_raw` | File address of the data segment's first byte (`sizeof_offsets` bytes). |


## Local Heap Free-list Block

Pickle type: `lh_free_blk`.

One free block in the local heap's data segment. Free blocks form a singly-linked list sorted by ascending data-segment offset. The minimum free block size is `2 × sizeof_lengths` bytes.

**Fields: Local Heap Free-list Block**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Next Off Raw | `next_off_raw` | Data-segment byte offset of the next free block, or 1 to signal the end of the free list (`sizeof_lengths` bytes). |
| Blk Size Raw | `blk_size_raw` | Size of this free block in bytes (`sizeof_lengths` bytes). |
