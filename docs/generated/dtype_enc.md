# VIII.B. Datatype Encoding

<a id="subsec_fmt4_appendixd_encodet"></a>

Upstream: [HDF5 File Format Specification 4.0, section VIII.B](https://support.hdfgroup.org/documentation/hdf5/latest/_f_m_t4.html#subsec_fmt4_appendixd_encodet) · Coverage: **Covered**

This is the standalone datatype encoding produced by the public
`H5Tencode()` / `H5Tdecode()` API calls. The HDF5 library never writes
these buffers into a file during normal operations; they appear on disk
only when application code explicitly stores the raw bytes (for example
as dataset or attribute data).

An encoded buffer is a two-byte prefix — a Datatype Message type ID
(always 3) and an encode version (always 0) — followed by a complete
Datatype Message payload (Section IV.A.3.d). That payload begins with an
8-byte header (class, version, class bit fields, and element size)
followed by class-specific properties. The class-specific decoding,
including recursive compound, enumeration, variable-length, array, and
complex types, is handled by the `oh_msg_dtype` type from `ohdr_msgs.pk`;
this pickle types only the two-byte prefix.

All fields are stored in little-endian byte order.

## Encoded Datatype Prefix

Pickle type: `dtype_enc_hdr`.

Two-byte prefix of an `H5Tencode` buffer. The Datatype Message itself begins immediately after and is decoded by `oh_msg_dtype`.

**Layout: Encoded Datatype**

<table class="format-layout">
  <thead><tr><th>byte</th><th>byte</th><th>byte</th><th>byte</th></tr></thead>
  <tbody>
    <tr><td>Datatype Message ID</td><td>Encoding Version</td><td colspan="2">Datatype Message (variable size)</td></tr>
    <tr><td colspan="4">Datatype Message (continued)</td></tr>
  </tbody>
</table>

**Fields: Encoded Datatype Prefix**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Datatype ID | `dtype_id` | Datatype Message type ID. Must be 3. |
| Encode Version | `encode_version` | Encode version (`H5T_ENCODE_VERSION`). Must be 0. |
