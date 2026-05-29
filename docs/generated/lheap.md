# III.D. Disk Format: Level 1D - Local Heap

Local heaps store small variable-length strings, primarily the names
used by version 1 group symbol tables. The heap header records the
size and file address of a separate data segment. Offsets stored in
symbol table entries are byte offsets within that data segment.

Byte 0 of the data segment is the empty-string sentinel. Used regions
contain NUL-terminated strings padded as needed, while unused regions
form a singly-linked free list. Free-list offsets are relative to the
start of the data segment.

## `lheap_free_blk`

Free block entry stored inside the local heap data segment. Free blocks are linked by offsets within the same data segment.

| Field | Description |
|-------|-------------|
| `next_off_raw` | Offset of the next free block within the data segment (`sizeof_lengths` bytes). The value 1 marks the end of the free list. |
| `blk_size_raw` | Size in bytes of this free block (`sizeof_lengths` bytes). |


## `local_heap`

Local Heap header (signature 'HEAP'). It describes the external data segment that contains heap strings and free-list records.

| Field | Description |
|-------|-------------|
| `signature` | 4-byte signature: 'H' 'E' 'A' 'P'. Must match exactly. |
| `version` | Local heap format version. Must be 0. |
| `reserved` | Reserved three-byte field. Must be zero. |
| `data_seg_size_raw` | Total allocated size of the data segment (`sizeof_lengths` bytes). |
| `free_list_head_raw` | Offset of the first free block within the data segment (`sizeof_lengths` bytes). All-FF or the value 1 indicates that the free list is empty. |
| `data_seg_addr_raw` | File address of the local heap data segment (`sizeof_offsets` bytes). |


