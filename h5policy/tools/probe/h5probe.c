/* Copyright (C) 2026 The HDF Group.
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <http://www.gnu.org/licenses/>.
 *
 * h5probe -- an exact-build libhdf5 probe.
 *
 * Linked against a SELECTED libhdf5 (the one under test, not whatever h5py
 * bundles), this opens one file through the public API and drives it through
 * the materialization/activation surface a real consumer would reach: it visits
 * every object, opens datasets, reads a bounded sample of raw data (exercising
 * filters, decompression, external/VDS storage), and reads attributes.  Named
 * exercise modes additionally drive entry points that a generic object walk
 * does not reach (external-link traversal and EFL writes).
 *
 * It reports a single JSON object on stdout describing what libhdf5 did and the
 * exact build identity.  It does NOT judge correctness: the h5policy oracle owns
 * the invariant.  This only answers "did the selected libhdf5 accept, reject
 * safely, or misbehave, and what did it touch."  OS-level activation events
 * (foreign opens, plugin dlopen, writes, network) are observed separately by the
 * LD_PRELOAD interposer; if libhdf5 crashes, this process dies with a signal and
 * the wrapper reports it -- so this program installs no signal handlers.
 *
 * Exit codes: 0 opened, 2 rejected-cleanly (H5Fopen or a later call failed),
 * 3 usage/internal.  A signal death is observed by the parent, not encoded here.
 */
#ifndef _GNU_SOURCE
#define _GNU_SOURCE          /* dladdr, from <dlfcn.h> */
#endif

#include <hdf5.h>

#include <dlfcn.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Bounded raw-data read: cap per-dataset elements so a hostile logical size
 * cannot make the probe itself the denial of service.  rlimits and a wall
 * timeout in the wrapper are the outer guard; this is the inner one. */
#define PROBE_MAX_ELEMENT_BYTES (4096 * 32)
#define PROBE_MAX_ELEMENTS 4096
/* Bounds on the chunk_index sweep (see chunk_sample_coords). */
#define PROBE_MAX_CHUNK_SAMPLES 4096
#define PROBE_MAX_READ_BYTES (4096 * 32)

enum entry_point_id {
    EP_H5FOPEN,
    EP_H5LVISIT2,
    EP_H5OVISIT3,
    EP_H5OOPEN,
    EP_H5DOPEN2,
    EP_H5DREAD,
    EP_H5DWRITE,
    EP_H5TGET_SIZE,
    EP_H5TGET_CLASS,
    EP_H5TGET_NMEMBERS,
    EP_H5TGET_MEMBER_TYPE,
    EP_H5TGET_SUPER,
    EP_H5SGET_EXTENT,
    EP_H5DGET_CREATE_PLIST,
    EP_H5SSELECT_ELEMENTS,
    EP_H5AOPEN_BY_IDX,
    EP_H5AREAD,
    EP_H5AGET_TYPE,
    EP_H5FGET_INFO2,
    EP_H5GGET_INFO,
    EP_H5FGET_CREATE_PLIST,
    EP_H5PGET_USERBLOCK,
    EP_H5FGET_EOA,
    EP_H5FGET_FILESIZE,
    EP_H5FGET_MDC_IMAGE_INFO,
    EP_H5FGET_MDC_SIZE,
    EP_H5GGET_CREATE_PLIST,
    EP_COUNT
};

struct entry_point_stat {
    const char *name;
    unsigned long calls;
    unsigned long successes;
    unsigned long failures;
};

struct probe_stats {
    unsigned long objects;
    unsigned long datasets;
    unsigned long attributes;
    unsigned long data_reads;    /* datasets whose raw data was sampled */
    unsigned long data_writes;   /* datasets whose isolated raw data was sampled */
    unsigned long call_errors;   /* post-open calls that failed (counted, not fatal) */
    unsigned long traversal_calls; /* family-mode traversal calls that completed */
    unsigned long family_attempts;
    unsigned long family_completed;
    unsigned long chunk_samples;   /* chunks touched by the chunk_index sweep */
    unsigned long chunk_sweep_skipped; /* datasets where the sweep was not applicable */
    int exercise_write;
    int exercise_chunk_index;
    int exercise_btree;
    int exercise_dense_index;
    int exercise_heap_structures;
    int exercise_shared_messages;
    int exercise_cache_image;
    int exercise_message_envelope;
    int exercise_legacy_messages;
    int exercise_datatype;
    int exercise_dataspace;
    int exercise_dataset_layout;
    int exercise_address_space;
    struct entry_point_stat entry_points[EP_COUNT];
};

static void init_stats(struct probe_stats *st)
{
    static const char *names[EP_COUNT] = {
        "H5Fopen", "H5Lvisit2", "H5Ovisit3", "H5Oopen", "H5Dopen2",
        "H5Dread", "H5Dwrite", "H5Tget_size", "H5Tget_class",
        "H5Tget_nmembers", "H5Tget_member_type", "H5Tget_super",
        "H5Sget_simple_extent_npoints", "H5Dget_create_plist",
        "H5Sselect_elements", "H5Aopen_by_idx", "H5Aread", "H5Aget_type",
        "H5Fget_info2", "H5Gget_info", "H5Fget_create_plist", "H5Pget_userblock",
        "H5Fget_eoa", "H5Fget_filesize", "H5Fget_mdc_image_info",
        "H5Fget_mdc_size", "H5Gget_create_plist"
    };
    memset(st, 0, sizeof *st);
    for (int i = 0; i < EP_COUNT; i++)
        st->entry_points[i].name = names[i];
}

static void entry_point_result(struct probe_stats *st, enum entry_point_id id,
                               int succeeded)
{
    struct entry_point_stat *ep = &st->entry_points[id];
    ep->calls++;
    if (succeeded)
        ep->successes++;
    else
        ep->failures++;
}

static void json_escape(const char *s, char *out, size_t n)
{
    size_t o = 0;
    for (size_t i = 0; s && s[i] && o + 2 < n; i++) {
        unsigned char c = (unsigned char)s[i];
        if (c == '"' || c == '\\') { out[o++] = '\\'; out[o++] = (char)c; }
        else if (c == '\n') { out[o++] = '\\'; out[o++] = 'n'; }
        else if (c < 0x20) { /* skip other control bytes */ }
        else out[o++] = (char)c;
    }
    out[o] = '\0';
}

#define DATATYPE_MAX_DEPTH 64
static void exercise_datatype(hid_t dtype, struct probe_stats *st, unsigned depth)
{
    if (dtype < 0 || depth > DATATYPE_MAX_DEPTH) return;
    H5T_class_t cls = H5Tget_class(dtype);
    entry_point_result(st, EP_H5TGET_CLASS, cls != H5T_NO_CLASS);
    size_t sz = H5Tget_size(dtype);
    entry_point_result(st, EP_H5TGET_SIZE, sz > 0);
    int n = H5Tget_nmembers(dtype);
    entry_point_result(st, EP_H5TGET_NMEMBERS, n >= 0);
    if (st->exercise_datatype && depth == 0 && cls != H5T_NO_CLASS && sz > 0)
        st->family_completed++;
    if (n > 0 && cls == H5T_COMPOUND) {
        for (int i = 0; i < n && i < 4096; i++) {
            hid_t m = H5Tget_member_type(dtype, (unsigned)i);
            entry_point_result(st, EP_H5TGET_MEMBER_TYPE, m >= 0);
            if (m >= 0) { exercise_datatype(m, st, depth + 1); H5Tclose(m); }
        }
    } else if (cls == H5T_ARRAY) {
        hid_t base = H5Tget_super(dtype);
        entry_point_result(st, EP_H5TGET_SUPER, base >= 0);
        if (base >= 0) { exercise_datatype(base, st, depth + 1); H5Tclose(base); }
    }
}

/* Build a point selection holding one element from EVERY chunk, so a single
 * H5Dread dereferences every child pointer in the chunk index.
 *
 * Sampling a single element only touches the chunk that element happens to
 * live in, leaving a corrupt child pointer anywhere else in the index
 * unreached -- and the file reported as a clean open.
 *
 * Bounded three ways so a hostile chunk grid cannot blow the probe up: per-
 * dimension grid extent, total chunk count, and total buffer bytes.  Returns
 * the point count, or 0 when sampling does not apply -- the caller then falls
 * back to the single-element read and records the sweep as skipped.
 */
static hsize_t chunk_sample_coords(const hsize_t *dims, const hsize_t *cdims,
                                   int rank, size_t tsize, hsize_t **out)
{
    hsize_t grid[H5S_MAX_RANK], total = 1;

    if (rank <= 0 || rank > H5S_MAX_RANK || tsize == 0)
        return 0;
    for (int i = 0; i < rank; i++) {
        if (dims[i] == 0 || cdims[i] == 0)
            return 0;
        grid[i] = (dims[i] + cdims[i] - 1) / cdims[i];
        if (grid[i] > PROBE_MAX_CHUNK_SAMPLES)
            return 0;
        total *= grid[i];
        if (total > PROBE_MAX_CHUNK_SAMPLES)
            return 0;
    }
    if (total * tsize > PROBE_MAX_READ_BYTES)
        return 0;

    hsize_t *c = (hsize_t *)calloc((size_t)total * (size_t)rank, sizeof *c);
    if (!c)
        return 0;
    /* Row-major walk of the chunk grid; each point is a chunk origin, which is
     * always inside the dataset extent. */
    for (hsize_t n = 0; n < total; n++) {
        hsize_t rem = n;
        for (int i = rank - 1; i >= 0; i--) {
            hsize_t idx = rem % grid[i];
            rem /= grid[i];
            c[n * (hsize_t)rank + (hsize_t)i] = idx * cdims[i];
        }
    }
    *out = c;
    return total;
}

static void exercise_dataset_io(hid_t dset, struct probe_stats *st)
{
    hid_t space = H5Dget_space(dset);
    hid_t dtype = H5Dget_type(dset);
    hid_t memspace = H5I_INVALID_HID;
    hsize_t *coord = NULL;
    if (space < 0 || dtype < 0) { st->call_errors++; goto done; }

    exercise_datatype(dtype, st, 0);

    hssize_t npoints = H5Sget_simple_extent_npoints(space);
    entry_point_result(st, EP_H5SGET_EXTENT, npoints >= 0);
    if (st->exercise_dataspace && npoints >= 0)
        st->family_completed++;
    hid_t dcpl = H5Dget_create_plist(dset);
    entry_point_result(st, EP_H5DGET_CREATE_PLIST, dcpl >= 0);
    if (st->exercise_dataset_layout && dcpl >= 0)
        st->family_completed++;
    int chunked = dcpl >= 0 && H5Pget_layout(dcpl) == H5D_CHUNKED;
    hsize_t chunk_dims[H5S_MAX_RANK];
    int chunk_rank = 0;
    if (chunked)
        chunk_rank = H5Pget_chunk(dcpl, H5S_MAX_RANK, chunk_dims);
    if (dcpl >= 0) H5Pclose(dcpl);
    size_t tsize = H5Tget_size(dtype);
    entry_point_result(st, EP_H5TGET_SIZE, tsize > 0);
    H5T_class_t tclass = H5Tget_class(dtype);
    entry_point_result(st, EP_H5TGET_CLASS, tclass != H5T_NO_CLASS);
    int nmembers = H5Tget_nmembers(dtype);
    entry_point_result(st, EP_H5TGET_NMEMBERS, nmembers >= 0);
    if (npoints < 0 || tsize == 0) { st->call_errors++; goto done; }

    /* Select exactly one element.  This reaches EFL/VDS/filter I/O even when a
     * hostile dataset declares a huge logical extent, while keeping the memory
     * and file selection bounded.  Variable-length values are deliberately not
     * materialized: their pointed-to payload is not bounded by H5Tget_size. */
    if (npoints == 0 || tsize > PROBE_MAX_ELEMENT_BYTES ||
        H5Tdetect_class(dtype, H5T_VLEN) > 0 || H5Tis_variable_str(dtype) > 0)
        goto done;

    int rank = H5Sget_simple_extent_ndims(space);
    if (rank < 0) { st->call_errors++; goto done; }
    hsize_t nsel = 1;          /* elements in the selection (and in the buffer) */
    int swept = 0;             /* the selection covers every chunk */
    if (rank > 0) {
        hsize_t dims[H5S_MAX_RANK];
        if (rank > H5S_MAX_RANK ||
            H5Sget_simple_extent_dims(space, dims, NULL) < 0) {
            st->call_errors++; goto done;
        }
        if (st->exercise_chunk_index && chunked && chunk_rank == rank) {
            /* One element per chunk: every child pointer gets dereferenced. */
            nsel = chunk_sample_coords(dims, chunk_dims, rank, tsize, &coord);
            swept = nsel > 0;
        }
        if (!swept) {
            nsel = 1;
            coord = (hsize_t *)calloc((size_t)rank, sizeof *coord);
            if (!coord) goto done;
            if (st->exercise_chunk_index) {
                st->chunk_sweep_skipped++;
                for (int i = 0; i < rank; i++)
                    coord[i] = dims[i] ? dims[i] - 1 : 0;
            }
        }
        if (H5Sselect_elements(space, H5S_SELECT_SET, (size_t)nsel, coord) < 0) {
            entry_point_result(st, EP_H5SSELECT_ELEMENTS, 0);
            st->call_errors++;
            goto done;
        }
        entry_point_result(st, EP_H5SSELECT_ELEMENTS, 1);
    } else if (H5Sselect_all(space) < 0) {
        st->call_errors++;
        goto done;
    }
    memspace = nsel > 1 ? H5Screate_simple(1, &nsel, NULL) : H5Screate(H5S_SCALAR);
    if (memspace < 0) { st->call_errors++; goto done; }

    void *buf = calloc((size_t)nsel, tsize);
    if (!buf) goto done;
    herr_t io = H5Dread(dset, dtype, memspace, space, H5P_DEFAULT, buf);
    entry_point_result(st, EP_H5DREAD, io >= 0);
    if (io < 0)
        st->call_errors++;                 /* a rejected read is a clean refusal */
    else
        st->data_reads++;
    if (io >= 0 && swept)
        st->chunk_samples += (unsigned long)nsel;
    /* Only a completed full sweep counts as exercising the chunk index: a
     * fallback single-element read reaches one chunk and is not family
     * coverage. */
    if (io >= 0 && st->exercise_chunk_index && chunked && swept)
        st->family_completed++;

    if (st->exercise_write) {
        memset(buf, 0, tsize);
        io = H5Dwrite(dset, dtype, memspace, space, H5P_DEFAULT, buf);
        entry_point_result(st, EP_H5DWRITE, io >= 0);
        if (io < 0)
            st->call_errors++;
        else
            st->data_writes++;
    }
    free(buf);

done:
    free(coord);
    if (memspace >= 0) H5Sclose(memspace);
    if (space >= 0) H5Sclose(space);
    if (dtype >= 0) H5Tclose(dtype);
}

static void probe_attributes(hid_t obj, struct probe_stats *st)
{
    H5O_info2_t oi;
    if (H5Oget_info3(obj, &oi, H5O_INFO_NUM_ATTRS) < 0) { st->call_errors++; return; }
    for (hsize_t i = 0; i < oi.num_attrs; i++) {
        hid_t a = H5Aopen_by_idx(obj, ".", H5_INDEX_CRT_ORDER, H5_ITER_INC, i,
                                 H5P_DEFAULT, H5P_DEFAULT);
        entry_point_result(st, EP_H5AOPEN_BY_IDX, a >= 0);
        if (a < 0)
            a = H5Aopen_by_idx(obj, ".", H5_INDEX_NAME, H5_ITER_INC, i,
                               H5P_DEFAULT, H5P_DEFAULT);
        if (a < 0)
            entry_point_result(st, EP_H5AOPEN_BY_IDX, 0);
        if (a < 0) { st->call_errors++; continue; }
        st->attributes++;
        hid_t at = H5Aget_type(a);
        entry_point_result(st, EP_H5AGET_TYPE, at >= 0);
        if (at >= 0 && st->exercise_shared_messages) st->family_completed++;
        hid_t as = H5Aget_space(a);
        hssize_t np = (as >= 0) ? H5Sget_simple_extent_npoints(as) : -1;
        size_t ts = (at >= 0) ? H5Tget_size(at) : 0;
        if (np >= 0 && np <= PROBE_MAX_ELEMENTS && ts > 0 &&
            (size_t)np * ts <= PROBE_MAX_ELEMENTS * 32) {
            void *buf = calloc(1, (size_t)np * ts + 1);
            if (buf) {
                herr_t io = H5Aread(a, at, buf);
                entry_point_result(st, EP_H5AREAD, io >= 0);
                if (io < 0) st->call_errors++;
                else if (st->exercise_heap_structures) st->family_completed++;
                free(buf);
            }
        }
        if (at >= 0) H5Tclose(at);
        if (as >= 0) H5Sclose(as);
        H5Aclose(a);
    }
}

static herr_t visit_cb(hid_t root, const char *name, const H5O_info2_t *info,
                       void *op)
{
    struct probe_stats *st = (struct probe_stats *)op;
    st->objects++;

    /* Force object-header materialization for every visited object: the
     * envelope surface that decodes message versions, flags, lengths and
     * padding.  For groups this must also decode the group-info and link-info
     * messages, which H5Oopen alone does NOT touch -- envelope.group_info_*
     * and envelope.link_info_* are message_envelope invariants, and reaching
     * them requires the group creation property list. */
    if (st->exercise_message_envelope) {
        hid_t envelope = H5Oopen(root, name, H5P_DEFAULT);
        entry_point_result(st, EP_H5OOPEN, envelope >= 0);
        if (envelope < 0) {
            st->call_errors++;
            return 0;
        }
        if (info->type == H5O_TYPE_GROUP) {
            hid_t gcpl = H5Gget_create_plist(envelope);
            entry_point_result(st, EP_H5GGET_CREATE_PLIST, gcpl >= 0);
            if (gcpl < 0) {
                st->call_errors++;
                H5Oclose(envelope);
                return 0;
            }
            unsigned crt_order = 0;
            unsigned est_entries = 0, est_name_len = 0;
            H5Pget_link_creation_order(gcpl, &crt_order);
            H5Pget_est_link_info(gcpl, &est_entries, &est_name_len);
            H5Pclose(gcpl);
        }
        st->family_completed++;
        H5Oclose(envelope);
    }

    if (info->type == H5O_TYPE_DATASET) {
        hid_t obj = H5Dopen2(root, name, H5P_DEFAULT);
        entry_point_result(st, EP_H5DOPEN2, obj >= 0);
        if (obj < 0) { st->call_errors++; return 0; }
        st->datasets++;
        probe_attributes(obj, st);
        exercise_dataset_io(obj, st);
        H5Dclose(obj);
        return 0;
    }

    hid_t obj = H5Oopen(root, name, H5P_DEFAULT);
    entry_point_result(st, EP_H5OOPEN, obj >= 0);
    if (obj < 0) { st->call_errors++; return 0; }   /* keep visiting siblings */
    if (st->exercise_legacy_messages && info->type == H5O_TYPE_GROUP) {
        H5G_info_t ginfo;
        herr_t gi = H5Gget_info(obj, &ginfo);
        entry_point_result(st, EP_H5GGET_INFO, gi >= 0);
        if (gi < 0) st->call_errors++;
        else st->family_completed++;
    }
    probe_attributes(obj, st);
    H5Oclose(obj);
    return 0;
}

/* H5Ovisit deliberately does not follow external links.  Enumerate links and
 * explicitly open each external-link path so a clean trace really means the
 * traversal entry point was exercised. */
static herr_t external_link_cb(hid_t root, const char *name,
                               const H5L_info2_t *info, void *op)
{
    struct probe_stats *st = (struct probe_stats *)op;
    if (info->type != H5L_TYPE_EXTERNAL)
        return 0;

    hid_t obj = H5Oopen(root, name, H5P_DEFAULT);
    entry_point_result(st, EP_H5OOPEN, obj >= 0);
    if (obj < 0)
        st->call_errors++;
    else
        H5Oclose(obj);
    return 0;                              /* keep looking for sibling links */
}

/* Resolve a concrete link selected by H5Lvisit2.  Unlike a generic object
 * walk, this makes the dense-link index answer a name lookup. */
static herr_t dense_link_cb(hid_t root, const char *name,
                            const H5L_info2_t *info, void *op)
{
    struct probe_stats *st = (struct probe_stats *)op;
    hid_t obj = H5Oopen(root, name, H5P_DEFAULT);
    entry_point_result(st, EP_H5OOPEN, obj >= 0);
    if (obj < 0)
        st->call_errors++;
    else {
        st->family_completed++;
        H5Oclose(obj);
    }
    return 0;
}

/* The B-tree/heap umbrella must resolve a concrete name from the indexed
 * link walk.  Merely completing H5Lvisit2 is not evidence that an index record
 * was materialized. */
static herr_t btree_link_cb(hid_t root, const char *name,
                            const H5L_info2_t *info, void *op)
{
    struct probe_stats *st = (struct probe_stats *)op;
    (void)info;
    hid_t obj = H5Oopen(root, name, H5P_DEFAULT);
    entry_point_result(st, EP_H5OOPEN, obj >= 0);
    if (obj < 0)
        st->call_errors++;
    else {
        st->family_completed++;
        H5Oclose(obj);
    }
    return 0;
}

static const char *linked_lib_path(void)
{
    Dl_info info;
    if (dladdr((void *)&H5Fopen, &info) && info.dli_fname)
        return info.dli_fname;
    return "";
}

int main(int argc, char **argv)
{
    const char *exercise = "generic";
    const char *path = NULL;
    if (argc == 2) {
        path = argv[1];
    } else if (argc == 4 && strcmp(argv[1], "--exercise") == 0) {
        exercise = argv[2];
        path = argv[3];
    } else {
        fprintf(stderr, "usage: h5probe [--exercise MODE] FILE\n");
        return 3;
    }
    int external_link = strcmp(exercise, "external_link") == 0;
    int efl = strcmp(exercise, "external_file_list") == 0;
    int vds = strcmp(exercise, "virtual_dataset") == 0;
    int datatype = strcmp(exercise, "datatype") == 0;
    int btree = strcmp(exercise, "btree") == 0;
    int link_walk = btree || strcmp(exercise, "dense_index") == 0;
    int family_mode = strcmp(exercise, "address_space") == 0 ||
                      strcmp(exercise, "dataspace") == 0 ||
                      strcmp(exercise, "dataset_layout") == 0 ||
                      strcmp(exercise, "chunk_index") == 0 ||
                      strcmp(exercise, "heap_structures") == 0 ||
                      strcmp(exercise, "shared_messages_legacy") == 0 ||
                      strcmp(exercise, "cache_image") == 0 ||
                      strcmp(exercise, "message_envelope") == 0 ||
                      strcmp(exercise, "legacy_messages") == 0;
    int generic = strcmp(exercise, "generic") == 0;
    if (!external_link && !efl && !vds && !datatype && !btree && !family_mode &&
        strcmp(exercise, "dense_index") != 0 && !generic) {
        fprintf(stderr, "h5probe: unknown exercise mode: %s\n", exercise);
        return 3;
    }

    /* Never print the HDF5 error stack: a rejection is expected output, not a
     * diagnostic to leak, and stderr noise would confuse the wrapper. */
    H5Eset_auto2(H5E_DEFAULT, NULL, NULL);

    unsigned maj = 0, min = 0, rel = 0;
    H5get_libversion(&maj, &min, &rel);

    char lib_esc[4096];
    json_escape(linked_lib_path(), lib_esc, sizeof lib_esc);

    struct probe_stats st;
    init_stats(&st);
    st.exercise_write = efl;
    st.exercise_chunk_index = strcmp(exercise, "chunk_index") == 0;
    st.exercise_btree = btree;
    st.exercise_dense_index = strcmp(exercise, "dense_index") == 0;
    st.exercise_heap_structures = strcmp(exercise, "heap_structures") == 0;
    st.exercise_shared_messages = strcmp(exercise, "shared_messages_legacy") == 0;
    st.exercise_cache_image = strcmp(exercise, "cache_image") == 0;
    st.exercise_message_envelope = strcmp(exercise, "message_envelope") == 0;
    st.exercise_legacy_messages = strcmp(exercise, "legacy_messages") == 0;
    st.exercise_datatype = strcmp(exercise, "datatype") == 0;
    st.exercise_dataspace = strcmp(exercise, "dataspace") == 0;
    st.exercise_dataset_layout = strcmp(exercise, "dataset_layout") == 0;
    st.exercise_address_space = strcmp(exercise, "address_space") == 0;
    if (!generic) st.family_attempts = 1;
    const char *decision;
    int rc;

    hid_t f = H5Fopen(path, efl ? H5F_ACC_RDWR : H5F_ACC_RDONLY, H5P_DEFAULT);
    entry_point_result(&st, EP_H5FOPEN, f >= 0);
    if (f < 0) {
        decision = "rejected";           /* libhdf5 refused the bytes at open */
        rc = 2;
    } else {
        if (st.exercise_address_space) {
            hid_t fcpl = H5Fget_create_plist(f);
            entry_point_result(&st, EP_H5FGET_CREATE_PLIST, fcpl >= 0);
            hsize_t userblock = 0;
            herr_t ub = fcpl >= 0 ? H5Pget_userblock(fcpl, &userblock) : -1;
            entry_point_result(&st, EP_H5PGET_USERBLOCK, ub >= 0);
            haddr_t eoa = 0;
            hsize_t filesize = 0;
            herr_t eoa_rc = H5Fget_eoa(f, &eoa);
            herr_t size_rc = H5Fget_filesize(f, &filesize);
            entry_point_result(&st, EP_H5FGET_EOA, eoa_rc >= 0);
            entry_point_result(&st, EP_H5FGET_FILESIZE, size_rc >= 0);
            if (ub < 0 || eoa_rc < 0 || size_rc < 0)
                st.call_errors++;
            /* The public values are absolute file offsets.  A completed
             * address-space canary has obtained both bounds and confirmed the
             * allocation ceiling does not reach beyond the physical image. */
            else if ((uintmax_t)eoa <= (uintmax_t)filesize &&
                     (uintmax_t)userblock <= (uintmax_t)filesize)
                st.family_completed++;
            if (fcpl >= 0) H5Pclose(fcpl);
        }
        if (st.exercise_cache_image) {
            haddr_t image_addr = HADDR_UNDEF;
            hsize_t image_size = 0, file_size = 0;
            size_t max_size = 0, min_clean_size = 0, cur_size = 0;
            int cur_entries = 0;
            herr_t image = H5Fget_mdc_image_info(f, &image_addr, &image_size);
            herr_t cache = H5Fget_mdc_size(f, &max_size, &min_clean_size,
                                           &cur_size, &cur_entries);
            herr_t size = H5Fget_filesize(f, &file_size);
            entry_point_result(&st, EP_H5FGET_MDC_IMAGE_INFO, image >= 0);
            entry_point_result(&st, EP_H5FGET_MDC_SIZE, cache >= 0);
            entry_point_result(&st, EP_H5FGET_FILESIZE, size >= 0);
            if (image < 0 || cache < 0 || size < 0)
                st.call_errors++;
            /* A cache image is relevant only when it has a defined, bounded
             * on-disk extent and HDF5 has a nonempty metadata cache to walk. */
            else if (image_addr != HADDR_UNDEF && image_size > 0 &&
                     (uintmax_t)image_addr <= (uintmax_t)file_size &&
                     (uintmax_t)image_size <= (uintmax_t)file_size - (uintmax_t)image_addr &&
                     cur_size > 0 && cur_entries > 0)
                st.family_completed++;
        }
        if (external_link || link_walk) {
            H5L_iterate2_t cb = st.exercise_dense_index ? dense_link_cb :
                                 st.exercise_btree ? btree_link_cb : external_link_cb;
            herr_t visited = H5Lvisit2(f, H5_INDEX_NAME, H5_ITER_INC, cb, &st);
            entry_point_result(&st, EP_H5LVISIT2, visited >= 0);
            if (visited < 0) st.call_errors++;
            else { st.traversal_calls++;
                   if (!st.exercise_dense_index && !st.exercise_btree)
                       st.family_completed++; }
        } else {
            /* Visit in creation order where available; fall back to name order. */
            herr_t visited = H5Ovisit3(f, H5_INDEX_CRT_ORDER, H5_ITER_INC,
                                       visit_cb, &st,
                                       H5O_INFO_BASIC | H5O_INFO_NUM_ATTRS);
            entry_point_result(&st, EP_H5OVISIT3, visited >= 0);
            if (visited < 0) {
                visited = H5Ovisit3(f, H5_INDEX_NAME, H5_ITER_INC, visit_cb,
                                    &st, H5O_INFO_BASIC | H5O_INFO_NUM_ATTRS);
                entry_point_result(&st, EP_H5OVISIT3, visited >= 0);
            }
            if (visited < 0) st.call_errors++;
            else { st.traversal_calls++;
                   if (!st.exercise_chunk_index && !st.exercise_heap_structures &&
                       !st.exercise_shared_messages && !st.exercise_cache_image &&
                       !st.exercise_message_envelope && !st.exercise_legacy_messages && !st.exercise_datatype &&
                       !st.exercise_dataspace && !st.exercise_dataset_layout &&
                       !st.exercise_address_space)
                       st.family_completed++; }
        }
        H5Fclose(f);
        decision = "opened";
        rc = 0;
    }

    printf("{\n");
    printf("  \"tool\": \"h5probe\",\n");
    printf("  \"exercise\": \"%s\",\n", exercise);
    printf("  \"decision\": \"%s\",\n", decision);
    printf("  \"libhdf5_version\": \"%u.%u.%u\",\n", maj, min, rel);
    printf("  \"linked_library\": \"%s\",\n", lib_esc);
    printf("  \"materialization\": {\n");
    printf("    \"objects\": %lu,\n", st.objects);
    printf("    \"datasets\": %lu,\n", st.datasets);
    printf("    \"attributes\": %lu,\n", st.attributes);
    printf("    \"data_reads\": %lu,\n", st.data_reads);
    printf("    \"data_writes\": %lu,\n", st.data_writes);
    printf("    \"traversal_calls\": %lu,\n", st.traversal_calls);
    printf("    \"chunk_samples\": %lu,\n", st.chunk_samples);
    printf("    \"chunk_sweep_skipped\": %lu,\n", st.chunk_sweep_skipped);
    printf("    \"call_errors\": %lu\n", st.call_errors);
    printf("  },\n");
    printf("  \"family_exercise\": {\"name\": \"%s\", \"attempts\": %lu, \"completed\": %lu},\n",
           exercise, st.family_attempts, st.family_completed);
    printf("  \"entry_points\": [\n");
    int emitted = 0;
    for (int i = 0; i < EP_COUNT; i++) {
        struct entry_point_stat *ep = &st.entry_points[i];
        if (ep->calls == 0) continue;
        if (emitted) printf(",\n");
        printf("    {\"name\": \"%s\", \"calls\": %lu, "
               "\"successes\": %lu, \"failures\": %lu}",
               ep->name, ep->calls, ep->successes, ep->failures);
        emitted = 1;
    }
    printf("\n  ]\n");
    printf("}\n");
    fflush(stdout);
    return rc;
}
