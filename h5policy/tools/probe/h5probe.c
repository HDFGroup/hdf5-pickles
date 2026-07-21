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

enum entry_point_id {
    EP_H5FOPEN,
    EP_H5LVISIT2,
    EP_H5OVISIT3,
    EP_H5OOPEN,
    EP_H5DOPEN2,
    EP_H5DREAD,
    EP_H5DWRITE,
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
    int exercise_write;
    struct entry_point_stat entry_points[EP_COUNT];
};

static void init_stats(struct probe_stats *st)
{
    static const char *names[EP_COUNT] = {
        "H5Fopen", "H5Lvisit2", "H5Ovisit3", "H5Oopen", "H5Dopen2",
        "H5Dread", "H5Dwrite"
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

static void exercise_dataset_io(hid_t dset, struct probe_stats *st)
{
    hid_t space = H5Dget_space(dset);
    hid_t dtype = H5Dget_type(dset);
    hid_t memspace = H5I_INVALID_HID;
    hsize_t *coord = NULL;
    if (space < 0 || dtype < 0) { st->call_errors++; goto done; }

    hssize_t npoints = H5Sget_simple_extent_npoints(space);
    size_t tsize = H5Tget_size(dtype);
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
    if (rank > 0) {
        coord = (hsize_t *)calloc((size_t)rank, sizeof *coord);
        if (!coord) goto done;
        if (H5Sselect_elements(space, H5S_SELECT_SET, 1, coord) < 0) {
            st->call_errors++;
            goto done;
        }
    } else if (H5Sselect_all(space) < 0) {
        st->call_errors++;
        goto done;
    }
    memspace = H5Screate(H5S_SCALAR);
    if (memspace < 0) { st->call_errors++; goto done; }

    void *buf = calloc(1, tsize);
    if (!buf) goto done;
    herr_t io = H5Dread(dset, dtype, memspace, space, H5P_DEFAULT, buf);
    entry_point_result(st, EP_H5DREAD, io >= 0);
    if (io < 0)
        st->call_errors++;                 /* a rejected read is a clean refusal */
    else
        st->data_reads++;

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
        if (a < 0)
            a = H5Aopen_by_idx(obj, ".", H5_INDEX_NAME, H5_ITER_INC, i,
                               H5P_DEFAULT, H5P_DEFAULT);
        if (a < 0) { st->call_errors++; continue; }
        st->attributes++;
        hid_t at = H5Aget_type(a);
        hid_t as = H5Aget_space(a);
        hssize_t np = (as >= 0) ? H5Sget_simple_extent_npoints(as) : -1;
        size_t ts = (at >= 0) ? H5Tget_size(at) : 0;
        if (np >= 0 && np <= PROBE_MAX_ELEMENTS && ts > 0 &&
            (size_t)np * ts <= PROBE_MAX_ELEMENTS * 32) {
            void *buf = calloc(1, (size_t)np * ts + 1);
            if (buf) {
                if (H5Aread(a, at, buf) < 0) st->call_errors++;
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
    int generic = strcmp(exercise, "generic") == 0;
    if (!external_link && !efl && !vds && !generic) {
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
    const char *decision;
    int rc;

    hid_t f = H5Fopen(path, efl ? H5F_ACC_RDWR : H5F_ACC_RDONLY, H5P_DEFAULT);
    entry_point_result(&st, EP_H5FOPEN, f >= 0);
    if (f < 0) {
        decision = "rejected";           /* libhdf5 refused the bytes at open */
        rc = 2;
    } else {
        if (external_link) {
            herr_t visited = H5Lvisit2(f, H5_INDEX_NAME, H5_ITER_INC,
                                       external_link_cb, &st);
            entry_point_result(&st, EP_H5LVISIT2, visited >= 0);
            if (visited < 0) st.call_errors++;
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
    printf("    \"call_errors\": %lu\n", st.call_errors);
    printf("  },\n");
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
