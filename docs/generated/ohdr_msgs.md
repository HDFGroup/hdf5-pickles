# IV.A. Disk Format: Level 2A - Data Object Headers and Messages

<a id="subsec_fmt4_dataobject_hdr"></a>

Upstream: [HDF5 File Format Specification 4.0, section IV.A.1, IV.A.2, IV.A.3, IV.B, VII.A, VII.B](https://support.hdfgroup.org/documentation/hdf5/latest/_f_m_t4.html#subsec_fmt4_dataobject_hdr) · Coverage: **Partial**

Object headers store all metadata associated with an HDF5 data object
(a group or a dataset). Every object header is composed of a prefix
(`oh_hdr`) followed by a sequence of variable-length messages; the
messages describe the object's dataspace, datatype, storage layout,
attributes, and other properties.

Two object header versions are defined. Version 1 is the original
format and has no signature. Version 2 begins with the 4-byte signature
`'OHDR'` and is more compact: it narrows several fields, makes timestamps
and attribute phase-change thresholds optional, and adds a checksum over
the entire header. An object header may span more than one contiguous
block on disk; additional blocks are continuation chunks referenced by
Object Header Continuation messages (type 0x0010). Version 2 continuation
chunks begin with the 4-byte signature `'OCHK'`; version 1 continuation
chunks have no signature.

Each message occupies one slot in an object header chunk and is
preceded by a `msg_prefix`, whose layout differs between version 1 and
version 2 headers. The message payload begins immediately after the
prefix. Message type identifiers range from 0x0000 to 0x0018. The
`message_factory` function dispatches a raw type ID and file offset to
the appropriate typed struct. Unknown types are returned as bounded raw byte
arrays; callers decide whether the message flags permit skipping them.

Several messages exist in an "old" and a "new" versioned form:
`oh_msg_old_fill` / `oh_msg_fill` and `oh_msg_old_mtime` /
`oh_msg_mtime`. Applications should write only the new form; the old
form is retained for reading legacy files.

All fields are stored in little-endian byte order. The executable mappings
reject source-defined local invariants before a malformed field can drive a
later map: unsupported dataspace, link, layout, and index versions; reserved
flag bits; invalid scalar/null dataspace ranks; zero link names; zero-length
continuation chunks; and invalid chunk-index encodings. Once a superblock
has supplied its declared EOF, hard-link targets plus continuation and
metadata-cache-image address ranges are checked against that bound. Target
type validation and graph-wide consistency remain outside this
format-inspection layer.

<a id="subsec_fmt4_dataobject_hdr_prefix"></a>

## Data Object Header Prefix

Pickle type: `oh_hdr`.

An HDF5 object header in either version 1 or version 2 format. The first four bytes are mapped twice: once as `sig_peek` (pinned at offset 0 without consuming bytes) to select the correct union arm, and again as part of the chosen version struct.

**Layout: Version 1 Object Header Prefix**

<table class="format-layout">
  <thead><tr><th>byte</th><th>byte</th><th>byte</th><th>byte</th></tr></thead>
  <tbody>
    <tr><td>Version</td><td>Reserved</td><td colspan="2">Number of Messages</td></tr>
    <tr><td colspan="4">Reference Count</td></tr>
    <tr><td colspan="4">Object Header Size</td></tr>
    <tr><td colspan="4">Reserved</td></tr>
  </tbody>
</table>

**Layout: Version 2 Object Header Prefix**

<table class="format-layout">
  <thead><tr><th>byte</th><th>byte</th><th>byte</th><th>byte</th></tr></thead>
  <tbody>
    <tr><td colspan="4">Signature</td></tr>
    <tr><td>Version</td><td>Flags</td><td colspan="2">Optional Fields</td></tr>
    <tr><td colspan="4">Optional Fields (continued)</td></tr>
    <tr><td colspan="4">Chunk 0 Size</td></tr>
    <tr><td colspan="4">Messages (variable size)</td></tr>
    <tr><td colspan="4">Checksum</td></tr>
  </tbody>
</table>

The signature is the four ASCII bytes `OHDR`. The flags select the optional timestamp, phase-change, and creation-order fields and the width of Chunk 0 Size.

**Fields: Data Object Header Prefix**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Sig Peek | `sig_peek` | Four bytes read at file offset 0 of the header without advancing the read position. If equal to the signature 'O' 'H' 'D' 'R' the version 2 arm is selected; otherwise the version 1 arm is selected. |

### Version 2

Pickle union arm: `v2`.

Version 2 object header layout (identified by the 4-byte signature 'O' 'H' 'D' 'R'). More compact than version 1; adds a checksum and optional timestamps.

**Fields: Version 2**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Signature | `signature` | 4-byte signature: 'O' 'H' 'D' 'R'. Must match `H5_FORMAT_OHDR_SIGNATURE`. |
| Version | `version` | Object header version number. Must be 2. |
| Flags | `flags` | Bit flags controlling optional fields and the encoding of `chunk0_size`. Bits 0–1: byte width of `chunk0_size`: 00 = 1 byte, 01 = 2 bytes, 10 = 4 bytes, 11 = 8 bytes. Bit 2: creation-order tracking is active — message prefixes include the optional `crt_order` field. Bit 3: a creation-order index (B-tree) is maintained for the attributes of this object. Bit 4: the `attr_phase` field is present. Bit 5: the `timestamps` field is present. |
| Timestamps | `timestamps` | Optional creation and access timestamps (type `hdr_timestamps`). Present when `flags` bit 5 is set. _optional_ |
| Attr Phase | `attr_phase` | Optional attribute phase-change thresholds (type `hdr_attr_phase`). Present when `flags` bit 4 is set. _optional_ |
| Chunk0 Size | `chunk0_size` | Size in bytes of the message data in the first object header chunk. Encoded as 1, 2, 4, or 8 bytes according to `flags` bits 0–1. The message data immediately follows this field and is not itself part of the on-disk `oh_hdr` struct; it is accessed via the internal `_msg_chunk` wrapper. Any padding between the last message and the checksum is the trailing part of that same `chunk0_size`-byte region; `get_gap_size` derives its length instead of mapping a second on-disk field. |
| Chksum | `chksum` | 4-byte Jenkins lookup3 checksum computed over all bytes of the object header from `signature` through the complete `chunk0_size`-byte message-and-padding region. |

### Version 1

Pickle union arm: `v1`.

Version 1 object header layout. Identified by a version byte of 1 at the start of the header (no signature bytes precede it).

**Fields: Version 1**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Version | `version` | Object header version number. Must be 1. |
| Reserved | `res1` | Reserved. Must be zero. |
| Message Cnt | `msg_cnt` | Total number of header messages across all chunks of this object header, including any continuation chunks. |
| Object Ref Cnt | `obj_ref_cnt` | Reference count: the number of hard links pointing to this object. An object is eligible for deletion when this count reaches zero. |
| Object Header Size | `obj_hdr_size` | Size in bytes of the message data in the first object header chunk. The message bytes immediately follow the 16-byte fixed prefix and are accessed via the internal `_msg_chunk` wrapper. |
| Reserved | `res2` | Reserved. Must be zero (4 bytes). |


## Object Header Timestamps

Pickle type: `hdr_timestamps`.

Four UNIX timestamps optionally embedded in a version 2 object header. Present when bit 5 of the object header `flags` field is set. Each value is a 32-bit unsigned seconds count relative to the UNIX epoch (1970-01-01 00:00:00 UTC).

**Fields: Object Header Timestamps**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Access | `access` | Time of the last read access to the object. |
| Modification | `modification` | Time of the last write to the object's raw data. |
| Change | `change` | Time of the last change to the object's metadata. |
| Birth | `birth` | Time at which the object was created. |


## Attribute Phase-change Thresholds

Pickle type: `hdr_attr_phase`.

Attribute storage phase-change thresholds optionally embedded in a version 2 object header. Present when bit 4 of `flags` is set. These thresholds control when the HDF5 library switches between compact attribute storage (inside the object header) and indexed attribute storage (in a fractal heap and B-tree).

**Fields: Attribute Phase-change Thresholds**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Max Compact | `max_compact` | Maximum number of attributes stored in compact form before the library converts to indexed storage. Once the count exceeds this value the library migrates to a fractal heap and B-tree. |
| Min Dense | `min_dense` | Minimum number of attributes that must remain in indexed storage before the library converts back to compact form. Must be less than or equal to `max_compact`. |


## Object Header Message Prefix

Pickle type: `msg_prefix`.

Fixed-size header that precedes every message payload in an object header chunk. The layout differs between version 1 and version 2 headers; the active arm is selected by the global version state set when the enclosing `oh_hdr` is mapped.

### Version 1 Message Prefix

Pickle union arm: `v1_msg_prefix`.

Version 1 message prefix (5 bytes of declared fields; the message-decoding logic accounts for 3 additional reserved bytes beyond this struct, giving an effective prefix size of 8 bytes).

**Fields: Version 1 Message Prefix**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Message Type | `msg_type` | 16-bit message type identifier. Values 0x0000–0x0018 are defined by the HDF5 specification; all others are reserved. |
| Message Size | `msg_size` | Size of the message payload in bytes, not including this prefix or the 3 reserved bytes that follow it. |
| Message Flags | `msg_flags` | Bit flags applying to this message. Bit 0: message data is constant after object creation and may be cached or shared. Bit 1: message is shared (payload is a Shared Message record rather than the message data itself). Bit 2: this message must not be shared. Bit 3: the HDF5 library may skip this message on open if it does not understand it. Bit 4: this message was marked as shareable but has not yet been moved to the shared message table. Bit 5: the object header was created before version 1.6 and this message was not originally encoded as a shared message. |

### Version 2 Message Prefix

Pickle union arm: `v2_msg_prefix`.

Version 2 message prefix (4 bytes without creation-order tracking, 6 bytes with it). The type field narrows from 16 to 8 bits compared with the version 1 prefix.

**Fields: Version 2 Message Prefix**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Message Type | `msg_type` | 8-bit message type identifier. |
| Message Size | `msg_size` | Size of the message payload in bytes, not including this prefix. |
| Message Flags | `msg_flags` | Bit flags (same bit definitions as in `v1_msg_prefix`). |
| Crt Order | `crt_order` | Creation order index of this message within the object header. Present only when bit 2 of the enclosing object header's `flags` field is set. _optional_ |


<a id="subsubsec_fmt4_dataobject_hdr_msg_nil"></a>

## NIL Message

Pickle type: `oh_msg_nil`.

Null message (type 0x0000). An empty, zero-length payload used to fill gaps left when a previous message was deleted or when an object header chunk is created with reserved space.


<a id="subsubsec_fmt4_dataobject_hdr_msg_simple"></a>

## Dataspace Message

Pickle type: `oh_msg_sdspace`.

Dataspace message (type 0x0001). Describes the shape and dimensionality of a dataset, including current dimension sizes and, optionally, maximum dimension sizes.

**Fields: Dataspace Message**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Version | `version` | Format version. Valid values: 1 and 2. |

### Version 1

Pickle union arm: `v1`.

Version 1 dataspace. Uses a fixed 5-byte reserved block.

**Fields: Version 1**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Number of Dimensions | `ndims` | Number of dimensions (0 = scalar). |
| Flags | `flags` | Bit 0: maximum dimension sizes are present (`max` field follows). Bit 1: permutation indices are present (`perm` field follows; never written by the library). |
| Reserved | `res` | Reserved. Must be zero (5 bytes). |
| Dim Size | `dim_size` | Array of `ndims` current dimension sizes, each `sizeof_lengths` bytes. |
| Max | `max` | Array of `ndims` maximum dimension sizes. `0xFFFF…FF` denotes unlimited. Present when `flags` bit 0 is set. _optional_ |
| Perm | `perm` | Permutation indices. Present when `flags` bit 1 is set. _optional; never written by the library_ |

### Version 2

Pickle union arm: `v2`.

Version 2 dataspace. Replaces the reserved block with an explicit space-type byte.

**Fields: Version 2**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Number of Dimensions | `ndims` | Number of dimensions. |
| Flags | `flags` | Bit 0: maximum dimension sizes are present (`max` field follows). |
| Space Type | `space_type` | Dataspace class: 0 = H5S_SCALAR, 1 = H5S_SIMPLE, 2 = H5S_NULL. |
| Dim Size | `dim_size` | Array of `ndims` current dimension sizes. |
| Max | `max` | Array of `ndims` maximum dimension sizes. Present when `flags` bit 0 is set. _optional_ |


<a id="subsubsec_fmt4_dataobject_hdr_msg_linkinfo"></a>

## Link Info Message

Pickle type: `oh_msg_linfo`.

Link info message (type 0x0002). Carries addresses of the fractal heap and B-trees used for dense link storage, and optionally the maximum creation order index assigned to a link in this group.

**Fields: Link Info Message**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Version | `version` | Format version. Must be 0. |
| Flags | `flags` | Bit 0: creation order is tracked — `max_corder` is present. Bit 1: creation order is indexed — `corder_bt2_addr_raw` is present. |
| Max Corder | `max_corder` | Maximum creation order value assigned to a link. Present when `flags` bit 0 is set. _optional_ |
| Fheap Address Raw | `fheap_addr_raw` | File address of the fractal heap for dense link storage. HADDR_UNDEF when compact. |
| Name Version 2 B-tree Address Raw | `name_bt2_addr_raw` | File address of the v2 B-tree indexing link names. HADDR_UNDEF when compact. |
| Corder Version 2 B-tree Address Raw | `corder_bt2_addr_raw` | File address of the v2 B-tree indexing link creation order. Present when `flags` bit 1 is set. _optional_ |


<a id="subsubsec_fmt4_dataobject_hdr_msg_dtmessage"></a>

## Datatype Message

Pickle type: `oh_msg_dtype`.

Datatype message (type 0x0003). Fully describes the type of a dataset's elements or an attribute's values. The datatype class is encoded in `hdr.flags` bits 0–3; the format version in bits 4–7. Compound, enumerated, variable-length, and array types embed one or more recursive `dtype_hdr` + properties blocks. Version 5 adds the recursive Complex class (11).

**Fields: Datatype Message**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Header | `hdr` | Common 8-byte datatype header (`dtype_hdr`): class, version, class flags, element size. |

### Fixed Point

Pickle union arm: `fixed_point`.

Class 0. Unsigned or signed integer stored in a fixed number of bits.

**Fields: Fixed Point**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Bit Offset | `bit_offset` | Bit offset of the first significant bit within the element. |
| Bit Precision | `bit_precision` | Number of significant bits. |

### Floating Point

Pickle union arm: `floating_point`.

Class 1. IEEE or VAX floating-point number. The byte order, padding, normalization, and exponent bias are encoded in `hdr.flags` class bits.

**Fields: Floating Point**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Bit Offset | `bit_offset` | Bit offset of the first significant bit. |
| Bit Precision | `bit_precision` | Total number of bits in the floating-point value. |
| Eloc | `eloc` | Bit position of the least-significant exponent bit. |
| Esize | `esize` | Number of bits in the exponent. |
| Mloc | `mloc` | Bit position of the least-significant mantissa bit. |
| Msize | `msize` | Number of bits in the mantissa. |
| Ebias | `ebias` | Exponent bias value. |

### Time

Pickle union arm: `time`.

Class 2. Fixed-precision time value. Byte order is in `hdr.flags` class bits.

**Fields: Time**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Bit Precision | `bit_precision` | Number of bits used to represent the time value. |

### Text String

Pickle union arm: `text_string`.

Class 3. Fixed-length character string. Padding type (null- terminate, null-pad, or space-pad) and character set (ASCII or UTF-8) are encoded entirely in `hdr.flags` class bits; there are no additional property bytes on disk.

### Bitfield

Pickle union arm: `bitfield`.

Class 4. Sequence of bits within a larger byte array. Layout mirrors fixed-point.

**Fields: Bitfield**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Bit Offset | `bit_offset` | Bit offset of the first significant bit. |
| Bit Precision | `bit_precision` | Number of significant bits. |

### Opaque

Pickle union arm: `opaque`.

Class 5. Uninterpreted raw bytes. The tag length is encoded in `hdr.flags` class bits (bits 8–15).

**Fields: Opaque**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Tag | `tag` | ASCII tag string describing the opaque data. |
| Pad | `pad` | Zero bytes padding `tag` to the next 8-byte boundary. |

### Compound

Pickle union arm: `compound`.

Class 6. Heterogeneous record type. The number of members is encoded in `hdr.flags` class bits (bits 8–23). Member layout differs between format versions 1, 2, and 3.

**Fields: Compound**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Membs | `membs` | Union holding the version-appropriate array of member descriptors. |

#### Version 1

Pickle union arm: `v1`.

Version 1 members: array of `compound_props1`, one entry per member.

#### Version 2

Pickle union arm: `v2`.

Version 2 members: array of `compound_props2`, one entry per member.

#### Version 3

Pickle union arm: `v3`.

Version 3 members: array of `compound_props3`, one entry per member.

### Reference

Pickle union arm: `reference`.

Class 7. Reference to another HDF5 object or region. The reference type and, for version 4+, the encoded version are in `hdr.flags` class bits. No additional property bytes.

### Enumeration

Pickle union arm: `enumeration`.

Class 8. Mapping of integer values to symbolic names. The number of members is in `hdr.flags` class bits (bits 8–23). Embeds a recursive base-type descriptor followed by member names and values.

**Fields: Enumeration**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Base Header | `base_hdr` | 8-byte `dtype_hdr` of the underlying integer base type. |
| Base Props | `base_props` | Type-class properties for the base type. |
| Memb Names | `memb_names` | Union holding member name strings, version-dependent. |
| Memb Values | `memb_values` | Packed array of `num_members × base_hdr.elm_size` bytes, one value per member. |

#### Version 1 2

Pickle union arm: `v1_2`.

Member names for versions 1 and 2: array of `enum_props`, each NUL-terminated and padded to 8 bytes.

#### Version 3

Pickle union arm: `v3`.

Member names for version 3: array of plain NUL-terminated strings.

### Variable Length

Pickle union arm: `variable_length`.

Class 9. Variable-length sequence or string. The VL type (sequence vs. string) is in `hdr.flags` class bits. Embeds a recursive base-type descriptor.

**Fields: Variable Length**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Base Header | `base_hdr` | 8-byte `dtype_hdr` of the base element type. |
| Base Props | `base_props` | Type-class properties for the base type. |

### Array

Pickle union arm: `array`.

Class 10. Fixed-size multidimensional array of a base type. Dimension information differs between version 2 and versions 3–5.

**Fields: Array**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Arr | `arr` | Union holding the version-appropriate dimension descriptor. |
| Base Header | `base_hdr` | 8-byte `dtype_hdr` of the array element type. |
| Base Props | `base_props` | Type-class properties for the element type. |

#### Version 2

Pickle union arm: `v2`.

Version 2 array dimensions: `array_props2` (with permutation array).

#### Version 3

Pickle union arm: `v3`.

Versions 3–5 array dimensions: `array_props3` (without permutation array).

### Complex

Pickle union arm: `complex`.

Class 11, introduced with datatype message version 5. A homogeneous complex number contains two values of the recursive floating-point base type. Class bit 0 marks homogeneous encoding; bits 1–2 select rectangular (0), polar (1), or exponential (2) form. This arm decodes the only encoding the format defines — homogeneous, rectangular, reserved class bits clear — which is also the only one the library reads or writes.

**Fields: Complex**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Base Header | `base_hdr` | 8-byte `dtype_hdr` of the floating-point base type. |
| Base Props | `base_props` | Type-class properties for the floating-point base type. |

### Complex Undefined

Pickle union arm: `complex_undefined`.

Class 11 with any other class bit field: not homogeneous, a reserved form, or a reserved bit set. No property layout is defined for those encodings, so this arm maps nothing past the 8-byte header — it reports the class bits as found and leaves the property bytes raw rather than presenting a base type that no consumer would ever read. Its constraint is the exact complement of `complex`, so a defined complex that merely fails to map (a truncated one, say) still raises instead of decoding here.


## Datatype Message Header

Pickle type: `dtype_hdr`.

8-byte common header present at the start of every Datatype message and embedded recursively in compound, enumerated, variable-length, array, and complex types. Encodes the datatype class, format version, and class-specific flags.

**Fields: Datatype Message Header**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Flags | `flags` | Packed 32-bit field. Bits 0–3: datatype class (0 = fixed-point, 1 = floating-point, 2 = time, 3 = string, 4 = bitfield, 5 = opaque, 6 = compound, 7 = reference, 8 = enumerated, 9 = variable-length, 10 = array, 11 = complex). Bits 4–7: format version. Bits 8–23: class bit-fields whose meaning depends on the class. |
| Element Size | `elm_size` | Size in bytes of one element of this datatype. |


## Compound Properties - Datatype Version 1

Pickle type: `compound_props1`.

Per-member descriptor for a version 1 compound datatype. Names are padded to 8-byte boundaries and a legacy array-dimension block is stored but is ignored by all current implementations.

**Fields: Compound Properties - Datatype Version 1**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Memb Name | `memb_name` | NUL-terminated member name string. |
| Pad | `pad` | Zero bytes padding `memb_name` to the next 8-byte boundary. |
| Memb Off | `memb_off` | 4-byte byte offset of this member within one compound element. |
| Ndim | `ndim` | Legacy: number of dimensions in the member's array descriptor. Always 0 in files written by the current library. |
| Reserved | `res1` | Reserved. Must be zero (3 bytes). |
| Perm | `perm` | Legacy: permutation index for each dimension (4 bytes; ignored). |
| Reserved | `res2` | Reserved. Must be zero (4 bytes). |
| Dim Sizes | `dim_sizes` | Legacy: 4 × 4 array of dimension sizes. Only the first `ndim` entries are meaningful; the rest are zero. |
| Memb Header | `memb_hdr` | 8-byte `dtype_hdr` describing this member's datatype. |
| Memb Props | `memb_props` | Variable-length type-class properties for the member's datatype. |


## Compound Properties - Datatype Version 2

Pickle type: `compound_props2`.

Per-member descriptor for a version 2 compound datatype. Removes the legacy dimension block present in version 1.

**Fields: Compound Properties - Datatype Version 2**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Memb Name | `memb_name` | NUL-terminated member name, padded to 8-byte boundary. |
| Pad | `pad` | Zero bytes padding `memb_name` to the next 8-byte boundary. |
| Memb Off | `memb_off` | 4-byte byte offset of this member within one compound element. |
| Memb Header | `memb_hdr` | 8-byte `dtype_hdr` describing this member's datatype. |
| Memb Props | `memb_props` | Variable-length type-class properties for the member's datatype. |


## Compound Properties - Datatype Version 3

Pickle type: `compound_props3`.

Per-member descriptor for a version 3 compound datatype. The member offset field is variable-width (1, 2, 4, or 8 bytes) determined by the total size of the compound element.

**Fields: Compound Properties - Datatype Version 3**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Memb Name | `memb_name` | NUL-terminated member name (no padding). |
| Memb Off | `memb_off` | Variable-width byte offset of this member. Width is 1 byte if `elm_size < 256`, 2 bytes if `< 65536`, 4 bytes if `< 4 GB`, otherwise 8 bytes. |
| Memb Header | `memb_hdr` | 8-byte `dtype_hdr` describing this member's datatype. |
| Memb Props | `memb_props` | Variable-length type-class properties for the member's datatype. |


## Enumeration Properties

Pickle type: `enum_props`.

Per-member name entry for version 1 and 2 enumerated datatypes. In version 3 the names are stored as plain NUL-terminated strings without padding.

**Fields: Enumeration Properties**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Name | `name` | NUL-terminated enumeration member name. |
| Pad | `pad` | Zero bytes padding the name to the next 8-byte boundary. |


## Array Properties - Datatype Version 2

Pickle type: `array_props2`.

Array datatype dimension descriptor for version 2. Includes a permutation index array that is always set to identity order `(0, 1, 2, …)` in files written by the current library.

**Fields: Array Properties - Datatype Version 2**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Number of Dimensions | `ndims` | Number of array dimensions. |
| Reserved | `res` | Reserved. Must be zero (3 bytes). |
| Dim Size | `dim_size` | Array of `ndims` uint32 dimension extents. |
| Perm Size | `perm_size` | Array of `ndims` uint32 permutation indices (legacy; always identity). |


## Array Properties - Datatype Version 3

Pickle type: `array_props3`.

Array datatype dimension descriptor for version 3. The permutation array is removed.

**Fields: Array Properties - Datatype Version 3**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Number of Dimensions | `ndims` | Number of array dimensions. |
| Dim Size | `dim_size` | Array of `ndims` uint32 dimension extents. |


<a id="subsubsec_fmt4_dataobject_hdr_msg_ofvmessage"></a>

## Data Storage - Fill Value (Old) Message

Pickle type: `oh_msg_old_fill`.

Fill value message, old form (type 0x0004). Stores a single raw fill value without versioning or allocation-time metadata. Present only in legacy files; new files use `oh_msg_fill`.

**Fields: Data Storage - Fill Value (Old) Message**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Fill Size | `fill_size` | Size in bytes of the fill value. Zero means no fill value is defined. |
| Fill Value | `fill_value` | Raw fill value bytes. Present only when `fill_size > 0`. _optional_ |


<a id="subsubsec_fmt4_dataobject_hdr_msg_fvmessage"></a>

## Data Storage - Fill Value Message

Pickle type: `oh_msg_fill`.

Fill value message, new form (type 0x0005). Extends the old form with explicit allocation- and fill-time controls and a defined/ undefined flag.

**Fields: Data Storage - Fill Value Message**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Version | `version` | Format version. Valid values: 1, 2, 3. |

### Versions 1 and 2

Pickle union arm: `v1_v2`.

Versions 1 and 2: explicit allocation-time, fill-time, and defined flag.

**Fields: Versions 1 and 2**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Alloc Time | `alloc_time` | When storage space is allocated: 0 = early (on creation), 1 = late (on first write), 2 = incremental. |
| Fill Time | `fill_time` | When fill values are written: 0 = on allocation, 1 = never, 2 = if user-defined fill value is set. |
| Fill Defined | `fill_defined` | Non-zero if a user-defined fill value is stored. |
| Fill Size | `fill_size` | Byte size of the fill value. Present only when `fill_defined > 0`. _optional_ |
| Fill Value | `fill_value` | Raw fill value bytes. Present when `fill_defined > 0` and `fill_size > 0`. _optional_ |

### Version 3

Pickle union arm: `v3`.

Version 3: allocation-time and fill-time are packed into a single flags byte; the fill-defined bit eliminates the separate `fill_defined` field.

**Fields: Version 3**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Flags | `flags` | Bits 0–1: allocation time (same values as v1/v2 `alloc_time`). Bits 2–3: fill time (same values as v1/v2 `fill_time`). Bit 5: fill value is defined (replaces the separate `fill_defined` field). |
| Fill Size | `fill_size` | Byte size of the fill value. Present when `flags` bit 5 is set. _optional_ |
| Fill Value | `fill_value` | Raw fill value bytes. Present when `flags` bit 5 is set and `fill_size > 0`. _optional_ |


<a id="subsubsec_fmt4_dataobject_hdr_msg_link"></a>

## Link Message

Pickle type: `oh_msg_link`.

Link message (type 0x0006). Describes one link within a group. The link type (hard, soft, external, or user-defined) is encoded in the `flags` field.

**Fields: Link Message**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Version | `version` | Format version. Must be 1. |
| Flags | `flags` | Bits 0–1: byte width of the `lnk_len` field (00 = 1 byte, 01 = 2 bytes, 10 = 4 bytes, 11 = 8 bytes). Bit 2: creation order is stored (`corder` field present). Bit 3: link type is explicitly stored (`lnk_type` field present). Bit 4: character set is stored (`cset` field present). |
| Lnk Type | `lnk_type` | Link type byte. 0 = hard link, 1 = soft link, 64 = external link, 255 = user-defined link. Present only when `flags` bit 3 is set (otherwise the type is hard, i.e. 0). _optional_ |
| Corder | `corder` | Link creation order value. Present only when `flags` bit 2 is set. _optional_ |
| Cset | `cset` | Character set of the link name: 0 = ASCII, 1 = UTF-8. Present when `flags` bit 4 is set. _optional_ |
| Lnk Len | `lnk_len` | Byte length of the link name array `lnk_name`. Width determined by `flags` bits 0–1. |
| Lnk Name | `lnk_name` | Link name character array (not NUL-terminated). |
| Ohdr Address Raw | `ohdr_addr_raw` | Target object header address. Present only for hard links (`lnk_type == 0`). _hard links only_ |
| Soft Len | `soft_len` | Byte length of the soft-link target string. Present only for soft links. _soft links only_ |
| Soft Name | `soft_name` | Soft-link target path (not NUL-terminated). Present when `soft_len > 0`. _soft links only_ |
| Ud Len | `ud_len` | Byte length of the user-defined link data. Present for external and user-defined links. _external/user-defined links only_ |
| Ud Data | `ud_data` | User-defined link data. For external links this is a NUL-terminated file path followed by a NUL-terminated object path. Present when `ud_len > 0`. _external/user-defined links only_ |


<a id="subsubsec_fmt4_dataobject_hdr_msg_external"></a>

## Data Storage - External Data Files Message

Pickle type: `oh_msg_external`.

External Data Files message (type 0x0007). Lists the external files that hold a dataset's raw data when contiguous storage is placed outside the HDF5 file. Each slot names one file segment via the local heap referenced by `heap_addr_raw`.

**Fields: Data Storage - External Data Files Message**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Version | `version` | Message version. Must be 1. |
| Reserved | `reserved` | Reserved. Must be zero (3 bytes). |
| Allocated Slots | `allocated_slots` | Number of slot entries allocated in this message (may exceed `used_slots`). |
| Used Slots | `used_slots` | Number of slot entries currently in use; only these are mapped in `slots`. |
| Heap Address Raw | `heap_addr_raw` | File address of the local heap holding the external file name strings (`sizeof_offsets` bytes). |
| Slots | `slots` | Array of `used_slots` `ext_slot` records, one per external file segment. |


## External File List Slot

Pickle type: `ext_slot`.

One entry in the External Data Files slot array (`oh_msg_external`). Each record describes a contiguous segment of a dataset's raw data stored in one external file.

**Fields: External File List Slot**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Name Off Raw | `name_off_raw` | Offset of the external file's name within the local heap referenced by the message's `heap_addr_raw` (`sizeof_lengths` bytes). |
| File Off Raw | `file_off_raw` | Byte offset into the external file at which this segment's data begins (`sizeof_lengths` bytes). |
| Data Size Raw | `data_size_raw` | Number of bytes reserved for this segment in the external file (`sizeof_lengths` bytes). |


<a id="subsubsec_fmt4_dataobject_hdr_msg_layout"></a>

## Data Layout Message

Pickle type: `oh_msg_layout`.

Data layout message (type 0x0008). Specifies how a dataset's raw data are stored on disk: compact (inside the object header), contiguous, chunked, or virtual. Five format versions are defined; versions 1 and 2 share the same struct, and so do versions 4 and 5.

**Fields: Data Layout Message**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Version | `version` | Format version. Valid values: 1, 2, 3, 4, 5. |

### Versions 1 and 2

Pickle union arm: `v1_v2`.

Layout for versions 1 and 2. The layout class is a separate field from the dimensionality.

**Fields: Versions 1 and 2**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Number of Dimensions | `ndims` | Number of dimensions plus one (the extra entry holds the element size). |
| Layout Class | `layout_class` | Storage class: 0 = compact, 1 = contiguous, 2 = chunked. |
| Reserved | `res` | Reserved. Must be zero (5 bytes). |

#### Contig

Pickle union arm: `contig`.

Contiguous layout properties (layout_class == 1).

**Fields: Contig**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Data Address Raw | `data_addr_raw` | File address of the contiguous data block. |
| Dim Size | `dim_size` | Array of `ndims` uint32 dimension sizes. |

#### Chunked

Pickle union arm: `chunked`.

Chunked layout properties (layout_class == 2).

**Fields: Chunked**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Index Address Raw | `idx_addr_raw` | File address of the v1 B-tree chunk index. |
| Dim Size | `dim_size` | Array of `ndims` uint32 dimension sizes (last entry = element size). |

#### Compact

Pickle union arm: `compact`.

Compact layout properties (layout_class == 0).

**Fields: Compact**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Dim Size | `dim_size` | Array of `ndims` uint32 dimension sizes. |
| Size | `size` | Number of bytes of raw data stored inline. |
| Compact Data | `compact_data` | Inline raw data bytes. Present only when `size > 0`. _optional_ |

### Version 3

Pickle union arm: `v3`.

Layout version 3. Layout class moves to the front; dimensionality is per-class.

**Fields: Version 3**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Layout Class | `layout_class` | Storage class: 0 = compact, 1 = contiguous, 2 = chunked. |

#### Compact

Pickle union arm: `compact`.

Compact storage (layout_class == 0).

**Fields: Compact**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Size | `size` | Number of bytes of raw data stored inline. |
| Raw Data | `raw_data` | Inline raw data bytes. Present only when `size > 0`. _optional_ |

#### Contig

Pickle union arm: `contig`.

Contiguous storage (layout_class == 1).

**Fields: Contig**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Data Address Raw | `data_addr_raw` | File address of the contiguous data block. |
| Data Size Raw | `data_size_raw` | Size in bytes of the contiguous data block. |

#### Chunked

Pickle union arm: `chunked`.

Chunked storage (layout_class == 2).

**Fields: Chunked**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Number of Dimensions | `ndims` | Number of chunk dimensions. |
| Index Address Raw | `idx_addr_raw` | File address of the v1 B-tree chunk index. |
| Dim Size | `dim_size` | Array of `ndims` uint32 chunk dimension sizes. |

### Versions 4 and 5

Pickle union arm: `v4_v5`.

Layout versions 4 and 5. Chunked storage gains an explicit index type field with per-type parameters; virtual storage is added. Version 5 (libhdf5 2.x, `H5F_LIBVER_V200`) encodes this message identically to version 4: it differs only in the chunk index *records*, where the filtered-chunk size field widens to `sizeof_lengths` so a filter that grows a chunk cannot overflow it.

**Fields: Versions 4 and 5**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Layout Class | `layout_class` | Storage class: 0 = compact, 1 = contiguous, 2 = chunked, 3 = virtual. |

#### Compact

Pickle union arm: `compact`.

Compact storage (layout_class == 0).

**Fields: Compact**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Size | `size` | Number of bytes of raw data stored inline. |
| Raw Data | `raw_data` | Inline raw data bytes. Present only when `size > 0`. _optional_ |

#### Contig

Pickle union arm: `contig`.

Contiguous storage (layout_class == 1).

**Fields: Contig**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Data Address Raw | `data_addr_raw` | File address of the contiguous data block. |
| Data Size Raw | `data_size_raw` | Size in bytes of the contiguous data block. |

#### Chunked

Pickle union arm: `chunked`.

Chunked storage (layout_class == 2).

**Fields: Chunked**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Flags | `flags` | Bit 0: chunk dimension sizes use a filter. Bit 1: a single-chunk index with filters is used (filter metadata present in the index parameters). |
| Number of Dimensions | `ndims` | Number of chunk dimensions. |
| Enc Bytes Per Dim | `enc_bytes_per_dim` | Number of bytes used to encode each entry of `dim_size`. |
| Dim Size | `dim_size` | Array of `ndims` chunk dimension sizes, each `enc_bytes_per_dim` bytes. |
| Index Type | `idx_type` | Chunk index type: 1 = single-chunk, 2 = implicit (compact/contiguous), 3 = fixed array, 4 = extensible array, 5 = version 2 B-tree. |
| Index Address Raw | `idx_addr_raw` | File address of the chunk index data structure. |

##### Single

Pickle union arm: `single`.

Single-chunk index parameters (idx_type == 1).

**Fields: Single**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Filter Chunk Size | `filter_chunk_size` | Filtered chunk size in bytes (`sizeof_lengths` bytes). Present only when `flags` bit 1 is set. _optional_ |
| Filter Mask | `filter_mask` | Filter pipeline skip mask for the single chunk. Present only when `flags` bit 1 is set. _optional_ |

##### Implicit

Pickle union arm: `implicit`.

Implicit index (idx_type == 2). No additional parameters stored.

##### Farray

Pickle union arm: `farray`.

Fixed Array index parameters (idx_type == 3).

**Fields: Farray**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Max Dblk Page Nelmts Bits | `max_dblk_page_nelmts_bits` | Log2 of the maximum number of elements in a data block page. |

##### Earray

Pickle union arm: `earray`.

Extensible Array index parameters (idx_type == 4).

**Fields: Earray**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Max Nelmts Bits | `max_nelmts_bits` | Log2 of the maximum number of elements in the array. |
| Index Blk Elmts | `idx_blk_elmts` | Number of elements to store in the index block. |
| Sup Blk Min Data Ptrs | `sup_blk_min_data_ptrs` | Minimum number of data block pointers in a super block. |
| Data Blk Min Elmts | `data_blk_min_elmts` | Minimum number of elements per data block. |
| Max Dblk Page Nelmts Bits | `max_dblk_page_nelmts_bits` | Log2 of the maximum number of elements in a data block page. _1 byte in the pickle; the spec specifies 2 bytes_ |

##### Version 2 B-tree

Pickle union arm: `bt2`.

Version 2 B-tree index parameters (idx_type == 5).

**Fields: Version 2 B-tree**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Node Size | `node_size` | Size of each B-tree node in bytes. |
| Split Percent | `split_percent` | Node occupancy (%) above which the node is split. |
| Merge Percent | `merge_percent` | Node occupancy (%) below which two nodes are merged. |

#### Virtual

Pickle union arm: `virtual`.

Virtual storage (layout_class == 3).

**Fields: Virtual**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Gheap Address Raw | `gheap_addr_raw` | File address of the global heap collection holding the VDS mapping. |
| Index | `idx` | Index of the VDS entry within the global heap collection. |


<a id="subsubsec_fmt4_dataobject_hdr_msg_groupinfo"></a>

## Group Info Message

Pickle type: `oh_msg_ginfo`.

Group info message (type 0x000a). Stores optional parameters controlling when a group switches between compact and dense link storage, and estimated size hints for newly created groups.

**Fields: Group Info Message**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Version | `version` | Format version. Must be 0. |
| Flags | `flags` | Bit 0: compact/dense phase-change thresholds are stored (`max_compact` and `min_dense` present). Bit 1: group size estimates are stored (`est_num_entries` and `est_name_len` present). |
| Max Compact | `max_compact` | Maximum number of links in compact form before conversion to indexed. Present when `flags` bit 0 is set. _optional_ |
| Min Dense | `min_dense` | Minimum number of links in indexed form before conversion to compact. Present when `flags` bit 0 is set. _optional_ |
| Est Num Entries | `est_num_entries` | Estimated number of entries in new groups. Present when `flags` bit 1 is set. _optional_ |
| Est Name Len | `est_name_len` | Estimated average length of link names. Present when `flags` bit 1 is set. _optional_ |


<a id="subsubsec_fmt4_dataobject_hdr_msg_filter"></a>

## Data Storage - Filter Pipeline Message

Pickle type: `oh_msg_pline`.

Filter pipeline message (type 0x000b). Lists the filters that are applied to a dataset's raw data in order. Versions 1 and 2 differ only in the filter descriptor layout.

**Fields: Data Storage - Filter Pipeline Message**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Version | `version` | Format version. Valid values: 1, 2. |
| Nfilters | `nfilters` | Number of filter descriptors in the pipeline (0–32). |

### Version 1

Pickle union arm: `v1`.

Version 1 pipeline. The filter list is preceded by a 6-byte reserved block.

**Fields: Version 1**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Reserved | `res` | Reserved. Must be zero (6 bytes). |
| Filtered List | `filt_list` | Array of `nfilters` version 1 `filt_descr` entries. |

### Version 2

Pickle union arm: `v2`.

Version 2 pipeline. The reserved block is removed; the filter list begins immediately.

**Fields: Version 2**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Filtered List | `filt_list` | Array of `nfilters` version 2 `filt_descr` entries. |


## Filter Description

Pickle type: `filt_descr`.

Descriptor for one filter in the filter pipeline message. Version 1 appends a `padding` field when `cd_nelmts` is odd; version 2 omits the padding.

**Fields: Filter Description**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| ID | `id` | Filter identification number. Values 1–255 are reserved for filters registered with The HDF Group; values 256–65535 are available for third-party filters. Well-known IDs: 1 = DEFLATE (zlib), 2 = SHUFFLE, 3 = FLETCHER32, 4 = SZIP, 5 = NBIT, 6 = SCALEOFFSET. |
| Name Len | `name_len` | Byte length of the optional `name` array including the NUL terminator. Zero when no name is stored. |
| Flags | `flags` | Filter flags. Bit 0: filter is optional — if it cannot be applied the data is stored without filtering. |
| Cd Nelmts | `cd_nelmts` | Number of uint32 client-data values in `cd_data`. |
| Name | `name` | Optional NUL-terminated filter name. Present only when `name_len > 0`. _optional_ |
| Cd Data | `cd_data` | Array of `cd_nelmts` uint32 parameters passed to the filter. |
| Padding | `padding` | 4-byte alignment padding. Present in version 1 only, and only when `cd_nelmts` is odd. _version 1 only, when cd_nelmts is odd_ |


<a id="subsubsec_fmt4_dataobject_hdr_msg_attribute"></a>

## Attribute Message

Pickle type: `oh_msg_attr`.

Attribute message (type 0x000c). Stores an attribute inline in the object header. Each attribute consists of a name, a datatype, a dataspace, and a data payload; versions 1 and 3 align the name, datatype, and dataspace to 8 bytes, while version 2 does not.

**Fields: Attribute Message**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Version | `version` | Format version. Valid values: 1, 2, 3. |
| Flags | `flags` | Reserved in version 1 (must be zero). In versions 2 and 3: bit 0 = datatype is shared, bit 1 = dataspace is shared. |
| Name Size | `name_size` | Byte length of the `name` field (including NUL terminator in v1). |
| Datatype Size | `dtype_size` | Byte length of the `dtype` field. |
| Dataspace Size | `dspace_size` | Byte length of the `dspace` field. |
| Cset | `cset` | Character set of the attribute name: 0 = ASCII, 1 = UTF-8. Version 3 only. _version 3 only_ |
| Name | `name` | Attribute name bytes. In version 1 the length is rounded up to an 8-byte boundary; in versions 2 and 3 it is stored exactly. |
| Datatype | `dtype` | Raw datatype message bytes (parsed as `oh_msg_dtype`). |
| Dataspace | `dspace` | Raw dataspace message bytes (parsed as `oh_msg_sdspace`). |
| Data | `data` | Raw attribute data bytes (size = `dtype.elm_size × product(dim_sizes)`). |


<a id="subsubsec_fmt4_dataobject_hdr_msg_comment"></a>

## Object Comment Message

Pickle type: `oh_msg_name`.

Object comment message (type 0x000d). Stores a short human-readable comment string for the object. There is no version or length field; the string is NUL-terminated and the message payload size determines its extent.

**Fields: Object Comment Message**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Name | `name` | NUL-terminated comment string. |


<a id="subsubsec_fmt4_dataobject_hdr_msg_omodified"></a>

## Object Modification Time (Old) Message

Pickle type: `oh_msg_old_mtime`.

Modification time message, old form (type 0x000e). Stores an object modification time as the fixed-width ASCII string YYYYMMDDhhmmss. Present only in legacy files; new files use `oh_msg_mtime`.

**Fields: Object Modification Time (Old) Message**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Timestamp | `timestamp` | Fourteen ASCII decimal bytes in YYYYMMDDhhmmss order. |
| Reserved | `res` | Reserved. Must be zero (2 bytes). |


<a id="subsubsec_fmt4_dataobject_hdr_msg_shared"></a>

## Shared Message Table Message

Pickle type: `oh_msg_shmesg_table`.

Shared object header message table message (type 0x000f). Points to the file-level shared message (SOHM) master table and records the number of indexes it contains.

**Fields: Shared Message Table Message**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Version | `version` | Format version. Must be 0. |
| Address Raw | `addr_raw` | File address of the shared object header message master table. |
| Nindexes | `nindexes` | Number of shared message indexes in the master table. |


<a id="subsubsec_fmt4_dataobject_hdr_msg_continuation"></a>

## Object Header Continuation Message

Pickle type: `oh_msg_cont`.

Object header continuation message (type 0x0010). Points to an additional object header chunk on disk, allowing an object header to span multiple non-contiguous blocks.

**Fields: Object Header Continuation Message**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Address Raw | `addr_raw` | File address of the continuation block. |
| Size Raw | `size_raw` | Byte size of the continuation block. |


<a id="subsubsec_fmt4_dataobject_hdr_msg_stmgroup"></a>

## Symbol Table Message

Pickle type: `oh_msg_stab`.

Symbol table message (type 0x0011). Present on groups encoded with the version 1 (legacy) symbol table structure. Points to the group's v1 B-tree and local heap.

**Fields: Symbol Table Message**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| B-tree Address Raw | `btree_addr_raw` | File address of the root node of the version 1 group B-tree. |
| Heap Address Raw | `heap_addr_raw` | File address of the local heap containing link name strings. |


<a id="subsubsec_fmt4_dataobject_hdr_msg_mod"></a>

## Object Modification Time Message

Pickle type: `oh_msg_mtime`.

Modification time message, new form (type 0x0012). Stores the object modification time as a UNIX timestamp.

**Fields: Object Modification Time Message**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Version | `version` | Format version. Must be 1. |
| Reserved | `res` | Reserved. Must be zero (3 bytes). |
| Seconds | `seconds` | UNIX timestamp (seconds since 1970-01-01 00:00:00 UTC) of the last metadata modification. |


<a id="subsubsec_fmt4_dataobject_hdr_msg_btreek"></a>

## B-tree ‘K’ Values Message

Pickle type: `oh_msg_btreek`.

Version 1 B-tree K values message (type 0x0013). Overrides the file-global B-tree K values from the superblock for this particular object. Stored in the superblock extension object header.

**Fields: B-tree ‘K’ Values Message**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Version | `version` | Format version. Must be 0. |
| B-tree K Chunk | `btree_k_chunk` | Internal node K value for the indexed (chunked) storage v1 B-tree. |
| B-tree K Snode | `btree_k_snode` | Internal node K value for the group (symbol table) v1 B-tree. |
| Sym Leaf K | `sym_leaf_k` | Leaf node K value for the group (symbol table) v1 B-tree. |


<a id="subsubsec_fmt4_dataobject_hdr_msg_drvinfo"></a>

## Driver Info Message

Pickle type: `oh_msg_drvinfo`.

Driver information message (type 0x0014). Stores virtual file driver metadata in an object header, most commonly in the superblock extension. The payload layout is selected by the 8-byte driver identifier.

**Fields: Driver Info Message**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Version | `version` | Format version. Must be 0. |
| Driver ID | `drv_id` | 8-byte ASCII driver identifier. Known values handled here are `NCSAmult` for the multi-file driver and `NCSAfami` for the family driver. |
| Driver Info Size | `drv_info_size` | Size in bytes of the driver-specific payload. |
| Datatype | `dtype` | Derived driver type used for dispatch: 1 = `NCSAmult`, 2 = `NCSAfami`, 0 = unknown. |
| Driver Info | `drv_info` | Driver-specific payload selected from the `drv_id` value. |

### Multi

Pickle union arm: `multi`.

Payload for the multi-file driver (`NCSAmult`). It maps each HDF5 usage class to a member file and stores the corresponding virtual address ranges and padded member file names.

**Fields: Multi**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Member Mapping | `member_mapping` | Six-byte mapping from usage class to member file index: superblock, B-tree, raw data, global heap, local heap, and object header. |
| Reserved | `reserved` | Reserved two-byte field. Must be zero. |
| N Members | `n_members` | Derived count of distinct non-zero member file indices in `member_mapping`. |
| Member Addrs | `member_addrs` | Array of `multi_drv_member_addr` records, one for each distinct mapped member file. |
| Member Names Raw | `member_names_raw` | Raw member file name bytes. Names are NUL-terminated and each encoded name is padded to an 8-byte boundary. |

### Fami

Pickle union arm: `fami`.

Payload for the family driver (`NCSAfami`).

**Fields: Fami**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Member Size | `member_size` | Size in bytes of each family member file. |

### Raw

Pickle union arm: `raw`.

Fallback payload for unrecognized driver identifiers. The bytes are retained without interpretation.

**Fields: Raw**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Data | `data` | Raw driver-specific payload bytes. |


<a id="subsubsec_fmt4_dataobject_hdr_msg_attrinfo"></a>

## Attribute Info Message

Pickle type: `oh_msg_ainfo`.

Attribute info message (type 0x0015). Stores addresses of the fractal heap and B-trees used for dense attribute storage, mirrors `oh_msg_linfo` but for attributes rather than links.

**Fields: Attribute Info Message**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Version | `version` | Format version. Must be 0. |
| Flags | `flags` | Bit 0: creation order is tracked — `max_crt_idx` is present. Bit 1: creation order is indexed — `corder_bt2_addr_raw` is present. |
| Max Crt Index | `max_crt_idx` | Maximum creation order value assigned to an attribute. Present when `flags` bit 0 is set. _optional_ |
| Fheap Address Raw | `fheap_addr_raw` | File address of the fractal heap for dense attribute storage. HADDR_UNDEF when compact. |
| Name Version 2 B-tree Address Raw | `name_bt2_addr_raw` | File address of the v2 B-tree indexing attribute names. |
| Corder Version 2 B-tree Address Raw | `corder_bt2_addr_raw` | File address of the v2 B-tree indexing attribute creation order. Present when `flags` bit 1 is set. _optional_ |


<a id="subsubsec_fmt4_dataobject_hdr_msg_refcount"></a>

## Object Reference Count Message

Pickle type: `oh_msg_refcount`.

Object reference count message (type 0x0016). Stores the count of hard links pointing to the object when that count exceeds what fits in the version 1 object header's 32-bit field.

**Fields: Object Reference Count Message**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Version | `version` | Format version. Must be 0. |
| Ref Cnt | `ref_cnt` | Current hard-link reference count. |


<a id="subsubsec_fmt4_dataobject_hdr_msg_fsinfo"></a>

## File Space Info Message

Pickle type: `oh_msg_fsinfo`.

File space info message (type 0x0017). Describes the file space management strategy. Deprecated version 0 uses the legacy strategy layout and optionally stores six manager addresses; version 1 uses the modern strategy layout and optionally stores twelve addresses split between small and large allocations. Stored in the superblock extension.

**Fields: File Space Info Message**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Version | `version` | Format version. Version 0 is deprecated and has a distinct legacy layout; version 1 is the current layout. |
| Strategy | `strategy` | Version-dependent file-space strategy. In v0: 0 = DEFAULT, 1 = ALL_PERSIST, 2 = ALL, 3 = AGGR_VFD, 4 = VFD. In v1: 0 = FSM_AGGR, 1 = PAGE, 2 = AGGR, 3 = NONE. |
| Persist | `persist` | Version 1 only. Non-zero if free-space-manager state is persisted across file opens. |
| Threshold | `threshold` | Minimum free-space section size (`sizeof_lengths` bytes) that is tracked. |
| Free-space Address | `fs_addr` | Version 0 only, present when strategy is ALL_PERSIST (1). Array of 6 file addresses (`sizeof_offsets` bytes each), one per legacy allocation type. |
| Page Size | `page_size` | Version 1 file-space page size (`sizeof_lengths` bytes). |
| Pgend Meta Thres | `pgend_meta_thres` | Version 1 threshold for storing small metadata at the end of a page. |
| Eoa | `eoa` | Version 1 end-of-address value from before free-space-manager allocation (`sizeof_offsets` bytes). |
| Small Free-space Address | `small_fs_addr` | Version 1 only, present when `persist` is non-zero. Array of 6 file addresses (`sizeof_offsets` bytes each) for small-allocation free-space managers, one per allocation type. |
| Large Free-space Address | `large_fs_addr` | Version 1 only, present when `persist` is non-zero. Array of 6 file addresses for large-allocation free-space managers, one per allocation type. |


<a id="h5lens_metadata_cache_image_message"></a>

## Metadata Cache Image Message

Pickle type: `oh_msg_mdci`.

Metadata cache image message (type 0x0018). Points to a serialized snapshot of the metadata cache written at file close to accelerate the next file open. Not described in the public format specification.

**Fields: Metadata Cache Image Message**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Version | `version` | Format version. Must be 0. |
| Image Address Raw | `image_addr_raw` | File address of the serialized metadata cache image block. |
| Image Size | `image_size` | Byte size of the metadata cache image block (`sizeof_lengths` bytes). |
