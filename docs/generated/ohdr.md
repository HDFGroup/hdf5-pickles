# IV.A. Disk Format: Level 2A – Data Object Headers

Object headers store all metadata associated with an HDF5 data object
(a group or a dataset). Every object header is composed of a prefix
followed by a sequence of variable-length messages; the messages
describe the object's dataspace, datatype, storage layout, attributes,
and other properties.

Two object header versions are defined. Version 1 is the original
format. Version 2 is more compact: it narrows several fields, makes
timestamps and attribute phase-change thresholds optional, and adds a
checksum over the entire header.

An object header may span more than one contiguous block on disk.
Additional blocks are called continuation chunks and are referenced by
Object Header Continuation messages (type 0x0010) within the preceding
chunk. Each version 2 continuation chunk is delimited by the 4-byte
signature 'O' 'C' 'H' 'K' and ends with a 4-byte checksum.

All object header fields are stored in little-endian byte order.

## `Timestamps`

Four UNIX timestamps optionally embedded in a version 2 object header. Present when bit 5 of the object header `flags` field is set. Each value is a 32-bit unsigned seconds count relative to the UNIX epoch (1970-01-01 00:00:00 UTC).

| Field | Description |
|-------|-------------|
| `access` | Time of the last read access to the object. |
| `modification` | Time of the last write to the object's raw data. |
| `change` | Time of the last change to the object's metadata. |
| `birth` | Time at which the object was created. |


## `AttrPhase`

Attribute storage phase-change thresholds optionally embedded in a version 2 object header. Present when bit 4 of `flags` is set. These thresholds control when the HDF5 library switches between compact attribute storage (inside the object header) and indexed attribute storage (in a fractal heap and B-tree).

| Field | Description |
|-------|-------------|
| `max_compact` | Maximum number of attributes stored in compact form before the library converts to indexed storage. Once the count exceeds this value the library migrates to a fractal heap and B-tree. |
| `min_dense` | Minimum number of attributes that must remain in indexed storage before the library converts back to compact form. Must be less than or equal to `max_compact`. |


## `msg_prefix`

Fixed-size header that precedes every message payload in an object header chunk. The layout differs between version 1 and version 2 headers; the active arm is selected by the global version state set when the enclosing `ohdr` is mapped.

### `v1_msg_prefix`

Version 1 message prefix (5 bytes of declared fields; the `Get_messages` logic accounts for 3 additional reserved bytes beyond this struct, giving an effective prefix size of 8 bytes).

| Field | Description |
|-------|-------------|
| `msg_type` | 16-bit message type identifier. Values 0x0000–0x001F are defined by the HDF5 specification; all others are reserved. |
| `msg_size` | Size of the message payload in bytes, not including this prefix or the 3 reserved bytes that follow it. |
| `msg_flags` | Bit flags applying to this message. Bit 0: message data is constant after object creation and may be cached or shared. Bit 1: message is shared (payload is a Shared Message record rather than the message data itself). Bit 2: this message must not be shared. Bit 3: the HDF5 library may skip this message on open if it does not understand it. Bit 4: this message was marked as shareable but has not yet been moved to the shared message table. Bit 5: the object header was created before version 1.6 and this message was not originally encoded as a shared message. |

### `v2_msg_prefix`

Version 2 message prefix (4 bytes without creation-order tracking, 6 bytes with it). The type field narrows from 16 to 8 bits compared with the version 1 prefix.

| Field | Description |
|-------|-------------|
| `msg_type` | 8-bit message type identifier. |
| `msg_size` | Size of the message payload in bytes, not including this prefix. |
| `msg_flags` | Bit flags (same bit definitions as in `v1_msg_prefix`). |
| `crt_order` | Creation order index of this message within the object header. Present only when bit 2 of the enclosing object header's `flags` field is set. _optional_ |


## `ohdr`

An HDF5 object header in either version 1 or version 2 format. The first four bytes are mapped twice: once as `sig_peek` (pinned at offset 0 without consuming bytes) to select the correct union arm, and again as part of the chosen version struct.

| Field | Description |
|-------|-------------|
| `sig_peek` | Four bytes read at file offset 0 of the header without advancing the read position. If equal to the signature 'O' 'H' 'D' 'R' the version 2 arm is selected; otherwise the version 1 arm is selected. |

### `v2`

Version 2 object header layout (identified by the 4-byte signature 'O' 'H' 'D' 'R'). More compact than version 1; adds a checksum and optional timestamps.

| Field | Description |
|-------|-------------|
| `signature` | 4-byte signature: 'O' 'H' 'D' 'R'. Must match the constant V2_SIG. |
| `version` | Object header version number. Must be 2. |
| `flags` | Bit flags controlling optional fields and the encoding of `chunk0_size`. Bits 0–1: byte width of `chunk0_size`: 00 = 1 byte, 01 = 2 bytes, 10 = 4 bytes, 11 = 8 bytes. Bit 2: creation-order tracking is active — message prefixes include the optional `crt_order` field. Bit 3: a creation-order index (B-tree) is maintained for the attributes of this object. Bit 4: the `attr_phase` field is present. Bit 5: the `timestamps` field is present. |
| `timestamps` | Optional creation and access timestamps (type `Timestamps`). Present when `flags` bit 5 is set. _optional_ |
| `attr_phase` | Optional attribute phase-change thresholds (type `AttrPhase`). Present when `flags` bit 4 is set. _optional_ |
| `chunk0_size` | Size in bytes of the message data in the first object header chunk. Encoded as 1, 2, 4, or 8 bytes according to `flags` bits 0–1. The message data immediately follows this field and is not itself part of the on-disk `ohdr` struct; it is accessed via the internal `_msg_chunk` wrapper. |
| `gap` | Zero or more padding bytes between the last message and the checksum in the first chunk. Present only when the messages do not fill the chunk exactly (i.e. when `chunk0_size` is not divisible by the message prefix size). _optional_ |
| `chksum` | 4-byte Jenkins lookup3 checksum computed over all bytes of the object header from `signature` through the last byte of `gap` (or of the final message if there is no gap). |

### `v1`

Version 1 object header layout. Identified by a version byte of 1 at the start of the header (no signature bytes precede it).

| Field | Description |
|-------|-------------|
| `version` | Object header version number. Must be 1. |
| `res1` | Reserved. Must be zero. |
| `msg_cnt` | Total number of header messages across all chunks of this object header, including any continuation chunks. |
| `obj_ref_cnt` | Reference count: the number of hard links pointing to this object. An object is eligible for deletion when this count reaches zero. |
| `obj_hdr_size` | Size in bytes of the message data in the first object header chunk. The message bytes immediately follow the 16-byte fixed prefix and are accessed via the internal `_msg_chunk` wrapper. |
| `res2` | Reserved. Must be zero (4 bytes). |


