# III.D. Disk Format: Level 1D - Local Heaps

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

## `lh_free_blk`

One free block in the local heap's data segment. Free blocks form a singly-linked list sorted by ascending data-segment offset. The minimum free block size is `2 × sizeof_lengths` bytes.

| Field | Description |
|-------|-------------|
| `next_off_raw` | Data-segment byte offset of the next free block, or 1 to signal the end of the free list (`sizeof_lengths` bytes). |
| `blk_size_raw` | Size of this free block in bytes (`sizeof_lengths` bytes). |


## `lheap_hdr`

Local heap header (signature 'HEAP'). Records the size and file address of the data segment and the head of its free list. The total header size is `8 + 2 × sizeof_lengths + sizeof_offsets` bytes.

| Field | Description |
|-------|-------------|
| `signature` | 4-byte signature: 'H' 'E' 'A' 'P'. Must match exactly. |
| `version` | Local heap version. Must be 0. |
| `reserved` | Reserved. Must be zero (3 bytes). |
| `data_seg_size_raw` | Total number of bytes allocated for the data segment (`sizeof_lengths` bytes). |
| `free_list_head_raw` | Data-segment byte offset of the first free block (`sizeof_lengths` bytes). An all-ones (undefined) value or 1 indicates that the heap has no free blocks. |
| `data_seg_addr_raw` | File address of the data segment's first byte (`sizeof_offsets` bytes). |
