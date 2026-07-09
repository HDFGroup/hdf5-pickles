# VIII.A. Appendix D: Dataspace Encoding (H5Sencode2 / H5Sdecode)

This is the standalone dataspace encoding produced by the public
`H5Sencode2()` / `H5Sdecode()` API calls. The HDF5 library never writes
these buffers into a file during normal operations; they appear on disk
only when application code explicitly stores the raw bytes (for example
as dataset or attribute data).

An encoded buffer is a fixed 7-byte prefix (`dspace_enc_hdr`) followed by
the dataspace extent message (an `oh_msg_sdspace` payload, Section
IV.A.2.b) and then a serialized H5S selection. The selection begins with
a 4-byte type (NONE, POINTS, HYPERSLABS, or ALL) and version, and its
remaining layout depends on both: hyperslab selections have versions 1-3
and point selections versions 1-2, with later versions using a compact
`enc_size`-based encoding and optional "regular" hyperslab form. The
selection walking is done by helper functions (`dspace_enc_sel_size`,
`dspace_enc_print_sel`), so this pickle types only the fixed prefix.

`size_of_size` in the prefix must match `global_sizeof_lengths`; for
64-bit HDF5 files both are 8.

All fields are stored in little-endian byte order.

## `dspace_enc_hdr`

Fixed 7-byte prefix of an `H5Sencode` buffer. The dataspace extent message and the serialized selection follow and are decoded by `oh_msg_sdspace` and the selection helpers respectively.

| Field | Description |
|-------|-------------|
| `ds_id` | Dataspace Message type ID (`OH_SDSPACE_ID`). Must be 1. |
| `encode_version` | Encode version (`H5S_ENCODE_VERSION`). Must be 0. |
| `size_of_size` | `sizeof(hsize_t)` on the encoding platform (typically 8). Each extent dimension value occupies this many bytes; it must match `global_sizeof_lengths`. |
| `extent_size` | Byte count of the dataspace extent message that follows the prefix (4-byte unsigned integer). |


