/* Create a file whose ATTRIBUTE value holds revised (H5T_STD_REF) references.
 *
 * This exists because h5py cannot write them.  The local h5py links libhdf5
 * 1.14.5, whose reference API predates H5R_ref_t round-tripping through
 * h5py, so `H5T_STD_REF` attributes are reachable only through the C API --
 * the same reason make_cache_image.c exists.
 *
 * The attribute holds two DATASET REGION references (H5R_DATASET_REGION2).
 * The region variety is the point: a revised reference is blob-backed, so its
 * on-disk element is
 *
 *     [type:1][flags:1][blob_size:4][heap addr:sizeof_offsets][heap idx:4]
 *
 * and the global-heap ID at offset 6 is METADATA, because an attribute's value
 * lives inside its object-header message.  A plain OBJECT reference would not
 * do: H5R__encode_heap direct-copies a non-external H5R_OBJECT2 and no heap ID
 * is written at all.
 *
 * Two elements, not one, so a fixture can corrupt the second and leave the
 * first as an in-file control.
 *
 * Object times are suppressed so the bytes are reproducible across runs.
 */
#include "hdf5.h"
#include <stdio.h>
#include <stdlib.h>

#define CHECK(expr)                                                           \
    do {                                                                      \
        if ((expr) < 0) {                                                     \
            fprintf(stderr, "make_stdref_attr: failed: %s\n", #expr);         \
            return EXIT_FAILURE;                                              \
        }                                                                     \
    } while (0)

int
main(int argc, char **argv)
{
    hid_t     fid, ocpl, dsp, did, asp, aid;
    hsize_t   dims[1]   = {16};
    hsize_t   adims[1]  = {2};
    hsize_t   start[1]  = {2};
    hsize_t   count[1]  = {5};
    H5R_ref_t ref[2];
    int       data[16];
    int       i;

    if (argc != 2) {
        fprintf(stderr, "usage: make_stdref_attr FILE\n");
        return EXIT_FAILURE;
    }

    for (i = 0; i < 16; i++)
        data[i] = i;

    CHECK(fid = H5Fcreate(argv[1], H5F_ACC_TRUNC, H5P_DEFAULT, H5P_DEFAULT));

    CHECK(ocpl = H5Pcreate(H5P_DATASET_CREATE));
    CHECK(H5Pset_obj_track_times(ocpl, 0));

    CHECK(dsp = H5Screate_simple(1, dims, NULL));
    CHECK(did = H5Dcreate2(fid, "d", H5T_NATIVE_INT, dsp, H5P_DEFAULT, ocpl,
                           H5P_DEFAULT));
    CHECK(H5Dwrite(did, H5T_NATIVE_INT, H5S_ALL, H5S_ALL, H5P_DEFAULT, data));

    CHECK(H5Sselect_hyperslab(dsp, H5S_SELECT_SET, start, NULL, count, NULL));
    CHECK(H5Rcreate_region(fid, "d", dsp, H5P_DEFAULT, &ref[0]));
    CHECK(H5Rcreate_region(fid, "d", dsp, H5P_DEFAULT, &ref[1]));

    CHECK(asp = H5Screate_simple(1, adims, NULL));
    CHECK(aid = H5Acreate2(did, "regs", H5T_STD_REF, asp, H5P_DEFAULT,
                           H5P_DEFAULT));
    CHECK(H5Awrite(aid, H5T_STD_REF, ref));

    for (i = 0; i < 2; i++)
        CHECK(H5Rdestroy(&ref[i]));

    CHECK(H5Aclose(aid));
    CHECK(H5Sclose(asp));
    CHECK(H5Dclose(did));
    CHECK(H5Sclose(dsp));
    CHECK(H5Pclose(ocpl));
    CHECK(H5Fclose(fid));
    return EXIT_SUCCESS;
}
