# VIII.B/C. Appendix D: Reference Encoding (revised and backward-compatible)

This pickle decodes the on-disk elements of HDF5 reference datasets and
attributes. Two families are covered.

**Revised references (Section VIII.B)** — one element of an
`H5T_STD_REF` dataset, the reference type introduced in HDF5 1.12. Every
element shares a fixed size and a 2-byte common header (`ref_enc_hdr`:
reference type and flags). There are two sub-formats: an internal
`H5R_OBJECT2` reference stores its object token directly in the element,
while all other kinds (dataset-region, attribute, or external object
references) store a blob in the global heap and keep only the blob size
and the global heap ID in the element. `ref_enc_block` covers both cases
via conditional fields; its `_print` follows the heap and decodes the
blob (token, optional external filename, dataspace selection, or
attribute name).

**Backward-compatible references (Section VIII.C)** — the older
`H5T_STD_REF_OBJ` and `H5T_STD_REF_DSETREG` element formats.
`ref_enc_obj1_block` is a bare file address; `ref_enc_region1_block` is a
global heap ID whose heap object holds the dataset address and a
serialized selection.

Serialized dataspace selections use the same wire format as `dspace_enc`
/ `vds`.

All fields are stored in little-endian byte order.

## `ref_enc_hdr`

2-byte common header at the start of every revised (`H5T_STD_REF`) reference element. Shared by the direct and blob sub-formats.

| Field | Description |
|-------|-------------|
| `ref_type` | Reference type: 2 = `H5R_OBJECT2`, 3 = `H5R_DATASET_REGION2`, 4 = `H5R_ATTR`. |
| `flags` | Reference flags. Bit 0 (`H5R_IS_EXTERNAL`) is set when the reference targets an object in an external file. |


## `ref_enc_block`

Complete on-disk revised (`H5T_STD_REF`) reference element. Embeds `ref_enc_hdr`, then, depending on type and flags, either the inline object token (internal `H5R_OBJECT2`) or the blob descriptor (blob size plus global heap ID) for all other references.

| Field | Description |
|-------|-------------|
| `hdr` | Embedded `ref_enc_hdr` (reference type and flags). |
| `token_size` | Number of valid bytes in the inline object token. Present only for an internal `H5R_OBJECT2` reference. _optional_ |
| `token` | Opaque object token (`sizeof_offsets` bytes). Present only for an internal `H5R_OBJECT2` reference. _optional_ |
| `blob_size_raw` | Byte count of the reference blob stored in the global heap (4-byte unsigned integer). Present for all blob-format references. _optional_ |
| `heap_addr_raw` | File address of the global heap collection holding the reference blob (`sizeof_offsets` bytes). Present for all blob-format references. _optional_ |
| `heap_idx_raw` | Object index of the blob within that collection (4-byte unsigned integer). Present for all blob-format references. _optional_ |


## `ref_enc_obj1_block`

Backward-compatible object reference element (`H5R_OBJECT1`, Section VIII.C). A bare raw file address of the referenced object. Element size is `sizeof_offsets` bytes.

| Field | Description |
|-------|-------------|
| `addr_raw` | Raw file address of the referenced object (`sizeof_offsets` bytes). |


## `ref_enc_region1_block`

Backward-compatible dataset-region reference element (`H5R_DATASET_REGION1`, Section VIII.C). A global heap ID; the heap object holds the dataset's file address followed by a serialized selection. Element size is `sizeof_offsets + 4` bytes.

| Field | Description |
|-------|-------------|
| `heap_addr_raw` | File address of the global heap collection holding the region data (`sizeof_offsets` bytes). |
| `heap_idx_raw` | Object index of the region data within that collection (4-byte unsigned integer). |


