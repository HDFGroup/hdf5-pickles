# What is bounded raw decode?

“Bounded raw decode” means: parse bytes into a small, inert, explicitly bounded representation before interpreting them as HDF5 semantics or constructing `libhdf5`-native objects.

![From Bytes in Storage to in Memory Structures](./From%20Bytes%20in%20Storage%20to%20in%20Memory%20Structures.png)

The decoder’s contract should be:

```text
input:  file image, offset, explicit byte extent, profile limits
output: raw record + child references + findings
never:  allocate from unchecked file values
never:  follow external paths
never:  load plugins
never:  decompress
never:  recursively traverse without depth/visited limits
never:  construct trusted/native HDF5 objects from unvalidated bytes
```

Below are a few examples (pseudo-code) of what bounded raw decode is and is not.

## 1. Object-header message envelope

Object headers are a good first target because many later decoders consume object-header messages.

**Unsafe shape:**

```C
decode_object_header(fd, addr) {
    while (...) {
        msg = decode_message(fd, cursor);
        dispatch_message(msg.type, msg.payload);   // payload may overrun chunk
        cursor += msg.size;                        // size is file-controlled
    }
}
```

**Bounded raw decode shape:**

```C
decode_ohdr_chunk(fd, chunk_addr, chunk_size, file_size, ctx) {
    end = checked_add(chunk_addr, chunk_size, file_size);

    cursor = chunk_addr;
    while (cursor < end) {
        old_cursor = cursor;

        if (end - cursor < MIN_MSG_HEADER)
            finding(H5_CORRUPT_MESSAGE_HEADER_TRUNCATED, cursor);

        hdr = raw_read_message_header(fd, cursor, end);
        cursor += hdr.header_size;

        payload_end = checked_add(cursor, hdr.payload_size, end);

        raw_msg = {
            .type = hdr.type,
            .flags = hdr.flags,
            .creation_order = hdr.creation_order,
            .payload_start = cursor,
            .payload_size = hdr.payload_size,
            .payload_end = payload_end
        };

        enqueue_raw_message(raw_msg);

        cursor = align8(payload_end);

        if (cursor <= old_cursor)
            finding(H5_CORRUPT_NON_PROGRESS_LOOP, cursor);
    }
}
```

The key property is that message-specific parsers receive only this:

```C
RawSlice payload = { start, size, end };
```

They are not allowed to read outside the payload slice. A dataspace decoder, datatype decoder, link decoder, or filter-pipeline decoder should not see the whole file and should not infer its own extent.

## 2. Dataspace message: rank and dimensions

A dataspace message can declare dimensions that imply enormous allocations. Raw decode should read the dimension vector, but not allocate the dataset or compute products unsafely.

**Bounded raw decode:**

```C
RawDataspace decode_dataspace(RawSlice s, Policy p) {
    Cursor c = cursor_for(s);

    version = read_u8(&c);
    rank    = read_u8(&c);
    flags   = read_u8(&c);

    if (rank > p.max_rank)
        finding(H5_RESOURCE_RANK, s.start);

    if (!cursor_has(&c, rank * encoded_length_size))
        finding(H5_CORRUPT_DATASPACE_TRUNCATED, c.off);

    dims = small_fixed_vector(rank);

    for (i = 0; i < rank; i++)
        dims[i] = read_encoded_length(&c);

    return RawDataspace {
        .version = version,
        .rank = rank,
        .flags = flags,
        .dims = dims,
        .payload_range = s
    };
}
```

**Later semantic validation:**

```C
uint64_t elements = 1;

for each dim in raw_dataspace.dims:
    elements = checked_mul(elements, dim, p.max_element_count);

logical_bytes = checked_mul(elements, dtype_size,
                            p.max_logical_dataset_bytes);

if (logical_bytes > p.max_logical_dataset_bytes)
    finding(H5_RESOURCE_LOGICAL_DATASET_BYTES, raw_dataspace.offset);
```

The raw decoder does **not** do this:

```C
malloc(dim0 * dim1 * dim2 * dtype_size);
```

It records the shape. A later validator decides whether the shape is acceptable.

## 3. Datatype message: recursive/nested types

Datatype messages can contain nested compound, array, variable-length, string, reference, and enum structures. The bounded decoder should avoid raw recursion into attacker-controlled nesting.

**Bounded pattern:**

```C
RawDatatype decode_datatype(RawSlice s, Policy p, DecodeCtx ctx) {
    if (ctx.dtype_depth > p.max_datatype_recursion_depth)
        finding(H5_CORRUPT_DATATYPE_RECURSION_LIMIT, s.start);

    Cursor c = cursor_for(s);

    class_and_version = read_u8(&c);
    class_bit_fields  = read_u24(&c);
    size              = read_u32(&c);

    if (size > p.max_datatype_size)
        finding(H5_RESOURCE_DATATYPE_SIZE, s.start);

    RawDatatype dt = {
        .class = class_of(class_and_version),
        .version = version_of(class_and_version),
        .declared_size = size,
        .payload_range = s
    };

    switch (dt.class) {
    case H5T_COMPOUND:
        member_count = decode_member_count(class_bit_fields);

        if (member_count > p.max_compound_members)
            finding(H5_RESOURCE_COMPOUND_MEMBER_COUNT, s.start);

        for each member:
            member_name = read_bounded_cstring(&c, s.end);
            member_offset = read_checked_member_offset(&c, s.end);

            child_slice = bounded_child_datatype_slice(&c, s.end);
            dt.children.push(child_slice);   // record slice only
        break;

    case H5T_ARRAY:
        ndims = decode_array_ndims(...);

        if (ndims > p.max_rank)
            finding(H5_RESOURCE_ARRAY_RANK, s.start);

        read array dims into small vector;
        child_slice = bounded_child_datatype_slice(&c, s.end);
        dt.children.push(child_slice);
        break;
    }

    return dt;
}
```

Important distinction:

```text
raw decode:
  "there is a child datatype at this bounded slice"

semantic validation:
  "the child datatype is legal, finite, size-consistent, non-overlapping"

native construction:
  "build an H5T object"
```

The first two can happen in GNU poke. The third should not happen in the forensic stack.

## 4. External link message

An external link is policy-relevant because it can name another file. Bounded raw decode should parse the strings but never open the target.

**Bounded raw decode:**

```C
RawExternalLink decode_external_link(RawSlice s, Policy p) {
    Cursor c = cursor_for(s);

    version = read_u8(&c);
    flags   = read_u8(&c);

    filename = read_bounded_string(&c, s.end, p.max_link_string_bytes);
    objpath  = read_bounded_string(&c, s.end, p.max_link_string_bytes);

    return RawExternalLink {
        .filename = filename,
        .object_path = objpath,
        .payload_range = s
    };
}
```

**Policy validation:**

```C
if (!p.allow_external_links)
    finding(H5_POLICY_EXTERNAL_LINK, raw.offset);

if (is_absolute_path(raw.filename))
    finding(H5_POLICY_EXTERNAL_ABSOLUTE_PATH, raw.offset);

if (contains_dotdot_traversal(raw.filename))
    finding(H5_POLICY_EXTERNAL_PATH_TRAVERSAL, raw.offset);
```

The raw decoder must not do this:

```C
open(filename);
H5Fopen(filename, ...);
realpath(filename, ...);
```

Even canonicalization can become dangerous if it touches attacker-controlled paths in a hostile filesystem. For the forensic stack, decode and report only.

## 5. Filter pipeline message

The filter pipeline declares compression or transformation filters. Bounded raw decode should enumerate filter IDs and parameter vectors. It should not load plugins or decompress data.

**Bounded raw decode:**

```C
RawFilterPipeline decode_filter_pipeline(RawSlice s, Policy p) {
    Cursor c = cursor_for(s);

    version = read_u8(&c);
    nfilters = read_u8(&c);

    if (nfilters > p.max_filter_count)
        finding(H5_RESOURCE_FILTER_COUNT, s.start);

    for (i = 0; i < nfilters; i++) {
        id = read_u16(&c);
        flags = read_u16(&c);
        name_len = read_u16(&c);
        cd_nelmts = read_u16(&c);

        if (name_len > p.max_filter_name_bytes)
            finding(H5_RESOURCE_FILTER_NAME_BYTES, c.off);

        if (cd_nelmts > p.max_filter_client_values)
            finding(H5_RESOURCE_FILTER_CLIENT_VALUES, c.off);

        name = read_bounded_bytes(&c, name_len, s.end);
        cd_values = read_bounded_u32_array(&c, cd_nelmts, s.end);

        pipeline.filters.push({
            .id = id,
            .flags = flags,
            .name = name,
            .cd_values = cd_values
        });
    }

    return pipeline;
}
```

The raw decoder must not do this:

```C
dlopen(plugin_for_filter_id);
inflate(chunk);
allocate(declared_decompressed_size);
```

The decoder’s output should be enough to say:

```text
this file requires filter 32008
this filter is not built-in
this profile rejects dynamic filters
```

No plugin execution is needed.

## 6. Chunked layout and chunk index root

A layout message may point to a chunk index. Raw decode should validate the pointer and record it; traversal should be a separate bounded operation.

**Bounded raw decode:**

```C
RawLayout decode_layout(RawSlice s, Policy p, FileGeom g) {
    Cursor c = cursor_for(s);

    version = read_u8(&c);
    layout_class = read_u8(&c);

    switch (layout_class) {
    case H5D_CHUNKED:
        ndims = read_u8(&c);

        if (ndims > p.max_rank + 1)
            finding(H5_RESOURCE_CHUNK_RANK, s.start);

        chunk_dims = read_bounded_dims(&c, ndims, s.end);

        chunk_index_addr = read_encoded_offset(&c);

        if (!addr_is_defined(chunk_index_addr))
            finding(H5_CORRUPT_UNDEFINED_CHUNK_INDEX_ADDR, c.off);

        if (!addr_in_file(g, chunk_index_addr))
            finding(H5_CORRUPT_OFFSET_OUT_OF_FILE, c.off);

        return RawLayout {
            .class = H5D_CHUNKED,
            .chunk_dims = chunk_dims,
            .chunk_index_addr = chunk_index_addr
        };
    }
}
```

Then chunk-index traversal is separate:

```C
walk_chunk_index(addr, depth, ctx) {
    if (depth > policy.max_btree_depth)
        finding(H5_CORRUPT_BTREE_DEPTH_EXCEEDED, addr);

    if (visited_contains(ctx.btree_nodes, addr))
        finding(H5_CORRUPT_BTREE_CYCLE, addr);

    if (ctx.chunk_nodes_seen++ > policy.max_chunk_index_nodes)
        finding(H5_RESOURCE_CHUNK_INDEX_NODES, addr);

    node = decode_raw_btree_node(fd, addr, bounded_node_size);

    for each child_addr in node.child_addrs:
        if (!addr_in_file(file_geom, child_addr))
            finding(H5_CORRUPT_OFFSET_OUT_OF_FILE, child_addr);
        else
            enqueue_child(child_addr, depth + 1);
}
```

The bounded decoder does not enumerate every chunk unless the profile budget allows it. It should report the index structure, not accidentally walk a billion-entry chunk tree.

## 7. Heap or free-list iteration

This is where “progress” bounds matter. A malformed heap can cause infinite loops if a size field is zero or a next pointer repeats.

**Bounded raw decode:**

```C
decode_heap_block(addr, block_size, ctx) {
    end = checked_add(addr, block_size, file_size);
    cursor = addr + HEAP_HEADER_SIZE;

    while (cursor < end) {
        old_cursor = cursor;

        entry_size = read_encoded_length(fd, cursor, end);

        if (entry_size == 0)
            finding(H5_CORRUPT_NON_PROGRESS_LOOP, cursor);

        entry_end = checked_add(cursor, entry_size, end);

        emit_raw_heap_entry(cursor, entry_size);

        cursor = entry_end;

        if (cursor <= old_cursor)
            finding(H5_CORRUPT_NON_PROGRESS_LOOP, cursor);
    }
}
```

The invariant is simple:

```text
Every loop must consume bytes, advance to a new validated address, or terminate.
```

If the next offset is attacker-controlled, also require:

```text
next != current
next inside current bounded region or known valid region
visited-set does not already contain next
hop count <= profile.max_heap_chain_length
```

## 8. Cache image or serialized metadata blob

A cache image is a high-risk structure because it can contain nested serialized metadata. The bounded pattern is: first decode the envelope, then decode entries only inside the declared image bounds.

**Bounded raw decode:**

```C
decode_cache_image(addr, declared_size, p, g) {
    if (declared_size > p.max_cache_image_bytes)
        finding(H5_RESOURCE_CACHE_IMAGE_BYTES, addr);

    image_end = checked_add(addr, declared_size, g.file_size);

    Cursor c = cursor(addr, image_end);

    magic = read_bytes(&c, 4);
    version = read_u8(&c);
    entry_count = read_u32(&c);

    if (entry_count > p.max_cache_image_entries)
        finding(H5_RESOURCE_CACHE_IMAGE_ENTRIES, addr);

    for (i = 0; i < entry_count; i++) {
        entry_type = read_u16(&c);
        entry_addr = read_encoded_offset(&c);
        entry_size = read_encoded_length(&c);

        if (!range_in_file(entry_addr, entry_size, g.file_size))
            finding(H5_CORRUPT_CACHE_IMAGE_ENTRY_RANGE, c.off);

        if (!range_inside(addr, image_end, c.off, encoded_entry_header_size))
            finding(H5_CORRUPT_CACHE_IMAGE_OVERRUN, c.off);

        emit_raw_cache_entry(entry_type, entry_addr, entry_size);
    }

    if (c.off != image_end)
        finding(H5_CORRUPT_CACHE_IMAGE_TRAILING_BYTES, c.off);
}
```

The raw decoder records entries. It does not instantiate cache objects, attach them to global state, or let them override separately decoded metadata.

## Useful rule of thumb

A raw decoder may answer:

```text
What bytes are present?
What small scalar fields do they contain?
What bounded child slices or addresses are declared?
Where are the declared references?
Which immediate envelope invariants fail?
```

It may not answer by side effect:

```text
Open that file.
Load that plugin.
Decompress that chunk.
Allocate that dataset.
Construct that H5T/H5D/H5G object.
Follow every link.
Repair this metadata.
Trust this declared length.
```

That separation is the point. The raw decoder turns attacker-controlled bytes into bounded evidence. The policy validator decides whether the evidence is acceptable. Native construction happens only after both phases succeed. (See the figure at the top.)