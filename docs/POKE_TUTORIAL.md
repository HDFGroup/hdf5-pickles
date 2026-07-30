# Low-Level GNU poke Tutorial

This advanced tutorial shows how to explore the sample HDF5 file
`examples/file.h5` directly from the GNU poke REPL using the repository's
pickles. Start with the [H5Lens tutorial](TUTORIAL.md) if you want the supported
`h5explain` workflow; continue here to see the mappings, address conversions,
and checksum operations underneath it.

It assumes GNU poke is installed and that you start from the repository root.

Start poke with the repository `pickles/` directory on the load path:

```sh
POKE_LOAD_PATH=$PWD/pickles poke examples/file.h5
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

This tells us that `examples/file.h5` uses a version 2 superblock and that the root object header starts at byte offset `48`.

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

Why `3UB`? `v1_btree.pk` expects the raw-chunk key width to be the dataset dimensionality plus one. `examples/file.h5` stores a 2-dimensional dataset (`8 x 8`), so the correct setting here is `2 + 1 = 3`.

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

This prints the four chunk records in `examples/file.h5`. Since `node_level=0`, this root node is also a leaf, so there are no child B-tree nodes to descend into; each `child_raw` value is the file address of the chunk payload itself.

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

This is useful when extending the pickles or when you want to discover methods
such as `get_messages ()` directly from the REPL.

Continue with [Writing HDF5 with GNU poke](POKE_CONSTRUCTION.md) only when you
are ready to work with write-through mappings and dependent checksums.
