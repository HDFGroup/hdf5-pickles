# Writing HDF5 with GNU poke

GNU poke mappings can write through to their backing IOS. This advanced
tutorial demonstrates that behavior on a disposable copy, then constructs a
minimal HDF5 file in memory.

> Never experiment with write-through mappings on an original or irreplaceable
> file. A field assignment does not automatically update dependent addresses,
> sizes, checksums, indexes, or other HDF5 consistency metadata.

Start with the [H5Lens tutorial](TUTORIAL.md) for normal read-only exploration
or the [low-level GNU poke tutorial](POKE_TUTORIAL.md) for direct decoding.
These examples assume GNU poke is installed and that you start from the
repository root.

## 1. Try a write on a disposable copy

Copy the tracked sample and open only the copy:

```sh
cp examples/file.h5 file-edit.h5
POKE_LOAD_PATH=$PWD/pickles poke file-edit.h5
```

At the `(poke)` prompt, load the object-header definitions, map the root header,
and change one timestamp:

```poke
load common
load ohdr_msgs
var root = oh_hdr @ 48#B
root._ohdr.v2.timestamps.birth
root._ohdr.v2.timestamps.birth = 0U
root._ohdr.v2.timestamps.birth
```

Expected output:

```text
(poke) root._ohdr.v2.timestamps.birth
1773447782U
(poke) root._ohdr.v2.timestamps.birth = 0U
(poke) root._ohdr.v2.timestamps.birth
0U
```

The assignment writes the scalar field, but the object-header checksum now
describes the old bytes. This is deliberate: the example demonstrates
write-through, not a complete repair. Use `h5patch` when you need an
evidence-gated repair plan that updates dependent metadata atomically.

Delete `file-edit.h5` when you finish.

## 2. Construct an empty HDF5 file

Build a minimal HDF5 file from scratch: a version 2 superblock followed by a
version 2 root object header for the root group. The metadata is staged in a
memory-backed IOS and saved only after its checksums are computed.

Start poke from the repository root without opening a file:

```sh
POKE_LOAD_PATH=$PWD/pickles poke
```

Load the construction helpers and create a memory IOS:

```poke
load construct
load lookup3
.mem image
```

Construct the version 2 superblock. The root object header will begin at
`48#B`, and the finished image will occupy `179#B`:

```poke
fun undef_addr = uint<8>[8]: { return uint<8>[8] (255); }

var sb = superblock_v2 { sizeof_offsets = 8UB, sizeof_lengths = 8UB, ext_addr_raw = undef_addr, eof_addr_raw = u64_to_bytes_le (179UL, 8), root_obj_addr_raw = u64_to_bytes_le (48UL, 8) }
```

Stage the root-group messages at the arbitrary scratch offset `1024#B`. The
memory IOS starts zero-filled, so the `88` data bytes of the NIL message need no
explicit initialization:

```poke
msg_prefix_v2 @ 1024#B = msg_prefix_v2 { msg_type = 2UB, msg_size = 18UH, msg_flags = 0UB }
oh_msg_linfo @ 1028#B = oh_msg_linfo { version = 0UB, flags = 0UB, fheap_addr_raw = undef_addr, name_bt2_addr_raw = undef_addr }

msg_prefix_v2 @ 1046#B = msg_prefix_v2 { msg_type = 10UB, msg_size = 2UH, msg_flags = 1UB }
oh_msg_ginfo @ 1050#B = oh_msg_ginfo { version = 0UB, flags = 0UB }

msg_prefix_v2 @ 1052#B = msg_prefix_v2 { msg_type = 0UB, msg_size = 88UH, msg_flags = 0UB }

var root = ohdr_v2 { flags = 0UB, chunk0_size = [120UB], msg_chunk = byte[120] @ 1024#B }
```

Serialize the typed values, compute their Jenkins lookup3 checksums, and save
the first `179` bytes:

```poke
superblock_v2 @ 0#B = sb
var sb_map = superblock_v2 @ 0#B
sb_map.chksum = lookup3_hashlittle(byte[44] @ 0#B, 0)

ohdr_v2 @ 48#B = root
var root_map = ohdr_v2 @ 48#B
root_map.chksum = lookup3_hashlittle(byte[127] @ 48#B, 0)

save :file "empty.h5" :size 179#B
```

Map the image back through the parser pickles and verify both checksums:

```poke
var sb2 = superblock @ 0#B
var root2 = oh_hdr @ 48#B

sb2.super_vers
bytes_to_off (sb2.super.v2_v3.root_obj_addr_raw)
lookup3_hashlittle(byte[44] @ 0#B, 0)
lookup3_u32_le(root2._ohdr.v2.chksum)
lookup3_hashlittle(byte[root2'size as offset<uint<64>,B> - 4UL#B] @ 48#B, 0)
root2.get_messages ()
```

The important results are:

```text
2UB
48UL#B
673867655U
2898835909U
2898835909U
```

The two object-header checksum values agree. At this point `empty.h5` is a
valid HDF5 file containing only the root group. If `h5dump` is installed,
`h5dump -pBH empty.h5` reports `SUPERBLOCK_VERSION 2` and `GROUP "/" {}`.
