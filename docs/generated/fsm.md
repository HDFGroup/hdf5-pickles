# III.H. Disk Format: Level 1H - Free-space Manager

The free-space manager tracks the free (unused) regions within an HDF5
file or within a fractal heap, so that space freed by deleting objects
can be reused. It has two on-disk structures: a fixed header (signature
'FSHD') recording heap-wide counters and the geometry needed to decode
sections, and a section-info block (signature 'FSSE') holding the actual
free-section records.

The header's fields determine several derived widths — the byte sizes of
section offsets, lengths, and counts — which the section-info decoder
needs; mapping `fs_hdr` sets those as globals so a subsequent `fs_sinfo`
mapping is decoded correctly. Each free section carries a client-specific
type: for the fractal-heap client (client 0) the section types are
single / first-row / normal-row / indirect; for the file client
(client 1) they are simple / small / large.

Because the section-info block packs variable-width records, `fs_sinfo`
is mapped as one raw byte array whose `_print` method walks the section
groups; only the fixed header exposes typed fields.

All fields are stored in little-endian byte order.

## `fs_hdr`

Free-space Manager header (signature 'FSHD'). Records total tracked space, section counts, the section classes' shrink/expand thresholds, and the address and size of the section-info block. Mapping it sets the derived section offset/length/count widths used by `fs_sinfo`.

| Field | Description |
|-------|-------------|
| `signature` | 4-byte signature: 'F' 'S' 'H' 'D'. Must match exactly. |
| `version` | Header version. Must be 0. |
| `client_id` | Identifies the free-space manager's client: 0 = fractal heap, 1 = file. Determines how section type codes are interpreted. |
| `tot_space_raw` | Total amount of free space, in bytes, tracked by this manager (`sizeof_lengths` bytes). |
| `tot_sect_count_raw` | Total number of free sections tracked, serialized plus ghost (`sizeof_lengths` bytes). |
| `serial_sect_count_raw` | Number of serializable (non-ghost) free sections stored in the section-info block (`sizeof_lengths` bytes). |
| `ghost_sect_count_raw` | Number of ghost sections — sections known in memory but not serialized to the section-info block (`sizeof_lengths` bytes). |
| `nclasses` | Number of section classes managed by this free-space manager. |
| `shrink_percent` | Percent of expansion below which the section-info block is shrunk on the next size adjustment. |
| `expand_percent` | Percent of used space above which the section-info block is expanded on the next size adjustment. |
| `max_sect_addr` | Size, in bits, of the largest section address; determines the section offset width (`sect_off_size`). |
| `max_sect_size_raw` | Maximum section size, used to derive the section length width (`sect_len_size`) (`sizeof_lengths` bytes). |
| `sect_addr_raw` | File address of the section-info block ('FSSE'), or the undefined address when no sections are serialized (`sizeof_offsets` bytes). |
| `sect_size_raw` | On-disk size, in bytes, of the section-info block (`sizeof_lengths` bytes). |
| `alloc_sect_size_raw` | File space actually allocated for the section-info block (`sizeof_lengths` bytes). |
| `chksum` | Jenkins lookup3 checksum over the preceding header bytes. |


## `fs_sinfo`

Free-space Manager section-info block (signature 'FSSE'). Holds the serialized free sections grouped by size. Mapped as a raw `sect_size`-byte array; the `_print` method verifies the signature, reads the owning header address, then walks each section group and its per-section address and type using the widths derived from `fs_hdr`. A Jenkins lookup3 checksum occupies the last 4 bytes.

| Field | Description |
|-------|-------------|
| `data` | The entire section-info allocation, `sect_size` bytes long. It begins with a 'FSSE' signature, a version byte, and the owning header's file address, followed by variable-width section-group records and a trailing checksum. |


