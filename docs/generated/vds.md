# III.F. Disk Format: Level 1F - Global Heap Block for Virtual Datasets

<a id="subsec_fmt4_infra_globalheapvds"></a>

Upstream: [HDF5 File Format Specification 4.0, section III.F](https://support.hdfgroup.org/documentation/hdf5/latest/_f_m_t4.html#subsec_fmt4_infra_globalheapvds) · Coverage: **Covered**

A virtual dataset maps regions of one or more source datasets onto a
single virtual dataset. The source-to-virtual mapping table is stored as
the data payload of a global heap object (`gheap`, Level 1E) and
referenced from the dataset's Data Layout message. This VDS heap block
holds that mapping table.

The block begins with a version byte and a mapping count, followed by
one entry per source→virtual mapping. Each entry names a source file and
source dataset (either inline as NUL-terminated strings, shared by index
from an earlier entry, or implicitly "." for the same file) and carries
a serialized source-dataspace selection and virtual-dataspace selection
(see `dspace_enc`). A Jenkins lookup3 checksum over all preceding bytes
closes the block.

This pickle types only the fixed-size prefix (`version` and
`num_mappings`); the variable-length entry list and trailing checksum are
walked directly by the `vds_block` `_print` method, since entry sizes
depend on the encoded selections. Two encoding versions exist: version 0
has no per-entry flags byte; version 1 adds one.

All fields are stored in little-endian byte order.

## Global Heap Block for Virtual Dataset

Pickle type: `vds_block`.

Virtual Dataset global heap block. Only the fixed prefix is mapped as typed fields; the per-mapping entries and trailing checksum are decoded on the fly by `_print` because each entry's length depends on its name-sharing flags and its serialized dataspace selections.

**Layout: Virtual Dataset Global Heap Block**

<table class="format-layout">
  <thead><tr><th>byte</th><th>byte</th><th>byte</th><th>byte</th></tr></thead>
  <tbody>
    <tr><td>Version</td><td colspan="3">Number of Mappings<sup>L</sup></td></tr>
    <tr><td colspan="4">Number of Mappings (continued)<sup>L</sup></td></tr>
    <tr><td colspan="4">Mapping Entries (variable size)</td></tr>
    <tr><td colspan="4">Checksum</td></tr>
  </tbody>
</table>

The first row is schematic because `L` may exceed three bytes. `L` is the size of lengths.

**Fields: Global Heap Block for Virtual Dataset**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Version | `version` | Block encoding version. 0 has no per-entry flags byte; 1 adds a flags byte to each mapping entry (source-file-shared, source-dataset-shared, source-same-file). |
| Num Mappings Raw | `num_mappings_raw` | Number of source→virtual mapping entries that follow (`sizeof_lengths` bytes). |
