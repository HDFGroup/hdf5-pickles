# Tutorial

This short tutorial shows how to explore the sample HDF5 file `file.h5` from the poke REPL using the pickles in this repository. It assumes GNU poke is installed and that you start from the repository root.

Start poke with the repository `pickles/` directory on the load path:

```sh
cd <THIS DIRECTORY>
POKE_LOAD_PATH=$PWD/pickles poke file.h5
```

At the `(poke)` prompt, load the pickles needed for the superblock and object headers:

```poke
load common
load superblock
load ohdr_msgs
load lookup3
```

These commands do not print anything on success; poke simply returns to the prompt.

## 1. Map the superblock

The HDF5 superblock begins at byte offset `0`:

```poke
var sb = superblock @ 0#B
sb.super_vers
var root_addr = bytes_to_off (sb.super.v2_v3.root_obj_addr_raw)
root_addr
```

Expected output:

```text
(poke) sb.super_vers
2UB
(poke) root_addr
48UL#B
```

This tells us that `file.h5` uses a version 2 superblock and that the root object header starts at byte offset `48`.

## 2. Decode the root object header

```poke
var root = oh_hdr @ root_addr
root
```

Expected output snippet:

```text
oh_hdr {
  sig_peek=[79UB,72UB,68UB,82UB],
  _ohdr=struct {
    v2=struct {
      signature=[79UB,72UB,68UB,82UB],
      version=2UB,
      flags=32UB,
      timestamps=hdr_timestamps {
        access=1773447782U,
        modification=1773447782U,
        change=1773447782U,
        birth=1773447782U
      },
      chunk0_size=[120UB],
      ...
      chksum=[7UB,68UB,33UB,252UB]
    }
  }
}
```

We are looking at a version 2 object header. Unlike the earlier version, it comes with a checksum. You can verify the checksum with the `lookup3_hashlittle` function from `lookup3.pk`:

```poke
lookup3_u32_le(root._ohdr.v2.chksum)
```

Expected output:

```text
4230038535U
```

Let's calculate the checksum ourselves to see how it works. The checksum is computed over the *entire object header* (including the prefix) except for the checksum field ( 4 bytes) itself, which is located at the end of the header.

```poke
lookup3_hashlittle(byte[root'size as offset<uint<64>,B> - 4UL#B] @ root_addr, 0)
```

Expected output:

```text
4230038535U
```

Phew! This confirms that the checksum is correct and that we understand how to compute it.

Print the root object header's decoded messages:

```poke
root.get_messages ()
```

Expected output snippet:

```text
Message 0...
msg_prefix {
  v2_msg_prefix=struct {
    msg_type=2UB,
    msg_size=18UH,
    msg_flags=0UB
  }
}
oh_msg_linfo {
  version=0UB,
  flags=0UB,
  fheap_addr_raw=[255UB,255UB,255UB,255UB,255UB,255UB,255UB,255UB],
  name_bt2_addr_raw=[255UB,255UB,255UB,255UB,255UB,255UB,255UB,255UB]
}

Message 2...
msg_prefix {
  v2_msg_prefix=struct {
    msg_type=6UB,
    msg_size=26UH,
    msg_flags=0UB
  }
}
oh_msg_link {
  version=1UB,
  flags=0UB,
  lnk_len=[15UB],
  lnk_name=[68UB,105UB,114UB,101UB,99UB,116UB,67UB,104UB,117UB,110UB,107UB,68UB,97UB,116UB,97UB],
  ohdr_addr_raw=[195UB,0UB,0UB,0UB,0UB,0UB,0UB,0UB]
}
```

The interesting part here is the link message: the byte array in `lnk_name` is the ASCII string `DirectChunkData`, and `ohdr_addr_raw` points to the child object header at byte offset `195`.

## 3. Follow the link to the dataset object header

Now map that child object header and decode its messages:

```poke
var dset = oh_hdr @ 195#B
dset.get_messages ()
```

Expected output snippet:

```text
Message 0...
oh_msg_sdspace {
  version=2UB,
  space=struct {
    v2=struct {
      ndims=2UB,
      flags=1UB,
      space_type=1UB,
      dim_size=[
        [8UB,0UB,0UB,0UB,0UB,0UB,0UB,0UB],
        [8UB,0UB,0UB,0UB,0UB,0UB,0UB,0UB]
      ],
      max=[
        [8UB,0UB,0UB,0UB,0UB,0UB,0UB,0UB],
        [8UB,0UB,0UB,0UB,0UB,0UB,0UB,0UB]
      ]
    }
  }
}

Message 1...
oh_msg_dtype {
  hdr.flags=2064U
  hdr.elm_size=4U
  types=struct {
    fixed_point=struct {
      bit_offset=0UH,
      bit_precision=32UH
    }
  }
}

Message 4...
oh_msg_layout {
  version=3UB,
  layout=struct {
    v3=struct {
      layout_class=2UB,
      properties=struct {
        chunked=struct {
          ndims=3UB,
          idx_addr_raw=[223UB,1UB,0UB,0UB,0UB,0UB,0UB,0UB],
          dim_size=[4U,4U,4U]
        }
      }
    }
  }
}
```

This shows the sort of machine-readable structure the pickles expose: dataspace, datatype, filter pipeline, and layout information are all decoded directly from the file.

## 4. Parse the chunk B-tree

The dataset layout message above tells us where the chunk index lives:

- `idx_addr_raw=[223UB,1UB,0UB,0UB,0UB,0UB,0UB,0UB]`
- interpreted as a little-endian file offset, that is `479#B` (`0x1df`)

In this sample file, the chunk index starts with the signature `TREE`, so it is a version 1 B-tree for raw-data chunks. Load the B-tree pickles, set the raw-chunk key dimensionality, and map the node:

```poke
load v1_btree
set_bt1_ndims (3UB)
var bt = bt1_hdr @ 479#B
bt
```

Why `3UB`? `v1_btree.pk` expects the raw-chunk key width to be the dataset dimensionality plus one. `file.h5` stores a 2-dimensional dataset (`8 x 8`), so the correct setting here is `2 + 1 = 3`.

Enable tree-style pretty printing in the current session. You can also put
these commands in poke's configuration file (`~/.pokerc`):

```poke
.set pretty-print yes
.set omode tree
```

Expected output (with options for readability):

```text
bt1_hdr {
  signature=[84UB,82UB,69UB,69UB],
  node_type=1UB,
  node_level=0UB,
  entries_used=4UH,
  left_sib_raw=[255UB,255UB,255UB,255UB,255UB,255UB,255UB,255UB],
  right_sib_raw=[255UB,255UB,255UB,255UB,255UB,255UB,255UB,255UB],
  body=struct {
    type1=struct {
      pairs=[pair1 {
        key=key1 {
          chunk_size=64U,
          filter_mask=1U,
          chunk_offsets=[0UL,0UL,0UL]
        },
        child_raw=[183UB,12UB,0UB,0UB,0UB,0UB,0UB,0UB]
      },pair1 {
        key=key1 {
          chunk_size=40U,
          filter_mask=0U,
          chunk_offsets=[0UL,4UL,0UL]
        },
        child_raw=[63UB,12UB,0UB,0UB,0UB,0UB,0UB,0UB]
      },pair1 {
        key=key1 {
          chunk_size=40U,
          filter_mask=0U,
          chunk_offsets=[4UL,0UL,0UL]
        },
        child_raw=[103UB,12UB,0UB,0UB,0UB,0UB,0UB,0UB]
      },pair1 {
        key=key1 {
          chunk_size=40U,
          filter_mask=0U,
          chunk_offsets=[4UL,4UL,0UL]
        },
        child_raw=[143UB,12UB,0UB,0UB,0UB,0UB,0UB,0UB]
      }],
      final_key=key1 {
        chunk_size=0U,
        filter_mask=0U,
        chunk_offsets=[4UL,4UL,4UL]
      }
    }
  }
}
```

For a more readable dump, use the recursive printer:

```poke
print_v1_btree (479#B, 0)
```

This prints the four chunk records in `file.h5`. Since `node_level=0`, this root node is also a leaf, so there are no child B-tree nodes to descend into; each `child_raw` value is the file address of the chunk payload itself.

Expected output (with options for readability):

```text
bt1_hdr {
  signature=[84UB,82UB,69UB,69UB]
  node_type=1UB
  node_level=0UB
  entries_used=4UH
  left_sib=[255UB,255UB,255UB,255UB,255UB,255UB,255UB,255UB]
  right_sib=[255UB,255UB,255UB,255UB,255UB,255UB,255UB,255UB]
  body=struct {
    type1=struct {
      pairs=[pair1 {
        key[0UL]: key=key1 {
          chunk_size=64U
          filter_mask=1U
          offsets=[0UL,0UL,0UL]
        }
      child[0UL]: child_raw=[183UB,12UB,0UB,0UB,0UB,0UB,0UB,0UB]
      }]
      pairs=[pair1 {
        key[1UL]: key=key1 {
          chunk_size=40U
          filter_mask=0U
          offsets=[0UL,4UL,0UL]
        }
      child[1UL]: child_raw=[63UB,12UB,0UB,0UB,0UB,0UB,0UB,0UB]
      }]
      pairs=[pair1 {
        key[2UL]: key=key1 {
          chunk_size=40U
          filter_mask=0U
          offsets=[4UL,0UL,0UL]
        }
      child[2UL]: child_raw=[103UB,12UB,0UB,0UB,0UB,0UB,0UB,0UB]
      }]
      pairs=[pair1 {
        key[3UL]: key=key1 {
          chunk_size=40U
          filter_mask=0U
          offsets=[4UL,4UL,0UL]
        }
      child[3UL]: child_raw=[143UB,12UB,0UB,0UB,0UB,0UB,0UB,0UB]
      }]
      key[4UL]: final_key=key1 {
        chunk_size=0U
        filter_mask=0U
        offsets=[4UL,4UL,4UL]
      }
    }
  }
}
```

## 5. Inspect the available types

You can also ask poke what each pickle defines:

```poke
.info type superblock
.info type oh_hdr
```

This is useful when extending the pickles or when you want to discover methods such as `get_messages ()` directly from the REPL.

## 6. Try a write on a disposable copy

Poke maps are writable. To avoid modifying the sample file in the repository, make a copy first:

```sh
cp file.h5 file-edit.h5
POKE_LOAD_PATH=$PWD/pickles poke file-edit.h5
```

Then edit a scalar field through the mapped object header:

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

This demonstrates byte-level write-through via the mapped pickle types. It does not automatically update higher-level HDF5 consistency metadata, so for real edits you may also need to recompute dependent fields such as checksums.

## 7. Creating an "empty" HDF5 file

We can also build a minimal HDF5 file from scratch: a version 2 superblock followed by a version 2 root object header for the root group. This time we construct the metadata in a memory-backed IOS first, and only save it to disk at the end.

Start poke from the repository root without opening a file yet:

```sh
cd <THIS DIRECTORY>
POKE_LOAD_PATH=$PWD/pickles poke
```

At the `(poke)` prompt, load the helper pickle and create a fresh memory IOS:

```poke
load construct
load lookup3
.mem image
```

First construct the version 2 superblock value. The root object header will start at offset `48#B`, and the final image size will be `179#B`:

```poke
fun undef_addr = uint<8>[8]: { return uint<8>[8] (255); }

var sb = superblock_v2 { sizeof_offsets = 8UB, sizeof_lengths = 8UB, ext_addr_raw = undef_addr, eof_addr_raw = u64_to_bytes_le (179UL, 8), root_obj_addr_raw = u64_to_bytes_le (48UL, 8) }
```

Now stage the root-group messages in the memory IOS at offset `1024#B`. That offset is arbitrary; we just use it as scratch space while building the object header chunk. The memory IOS starts zero-filled, so the `88` data bytes of the NIL message do not need any explicit initialization.

```poke
msg_prefix_v2 @ 1024#B = msg_prefix_v2 { msg_type = 2UB, msg_size = 18UH, msg_flags = 0UB }
oh_msg_linfo @ 1028#B = oh_msg_linfo { version = 0UB, flags = 0UB, fheap_addr_raw = undef_addr, name_bt2_addr_raw = undef_addr }

msg_prefix_v2 @ 1046#B = msg_prefix_v2 { msg_type = 10UB, msg_size = 2UH, msg_flags = 1UB }
oh_msg_ginfo @ 1050#B = oh_msg_ginfo { version = 0UB, flags = 0UB }

msg_prefix_v2 @ 1052#B = msg_prefix_v2 { msg_type = 0UB, msg_size = 88UH, msg_flags = 0UB }

var root = ohdr_v2 { flags = 0UB, chunk0_size = [120UB], msg_chunk = byte[120] @ 1024#B }
```

Serialize the typed values into the first `179` bytes of the memory IOS, compute the checksums, and save the result to disk:

```poke
superblock_v2 @ 0#B = sb
var sb_map = superblock_v2 @ 0#B
sb_map.chksum = lookup3_hashlittle(byte[44] @ 0#B, 0)

ohdr_v2 @ 48#B = root
var root_map = ohdr_v2 @ 48#B
root_map.chksum = lookup3_hashlittle(byte[127] @ 48#B, 0)

save :file "empty.h5" :size 179#B
```

Finally, map the image back using the parser pickles and verify it:

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

Expected output snippet:

```text
(poke) sb2.super_vers
2UB
(poke) bytes_to_off (sb2.super.v2_v3.root_obj_addr_raw)
48UL#B
(poke) lookup3_hashlittle(byte[44] @ 0#B, 0)
673867655U
(poke) lookup3_u32_le(root2._ohdr.v2.chksum)
2898835909U
(poke) lookup3_hashlittle(byte[root2'size as offset<uint<64>,B> - 4UL#B] @ 48#B, 0)
2898835909U

Message 0...
oh_msg_linfo { ... }

Message 1...
oh_msg_ginfo {
  version=0UB,
  flags=0UB
}

Message 2...
oh_msg_nil {
}
```

At this point `empty.h5` is a valid HDF5 file containing only the root group. For an external check, `h5dump -pBH empty.h5` reports `SUPERBLOCK_VERSION 2` and `GROUP "/" {}`.
