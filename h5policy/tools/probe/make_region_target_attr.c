/* Create a file whose ATTRIBUTE holds two region references: the first names a
 * dataset, the second names an object that is NOT a dataset.
 *
 *     make_region_target_attr FILE {group|datatype} {revised|legacy}
 *
 * libhdf5 writes this shape itself: H5Rcreate_region and the deprecated
 * H5Rcreate(..., H5R_DATASET_REGION, ...) both accept a group or a committed
 * datatype as the target, and neither refuses.  The file is therefore not
 * malformed, but H5Ropen_region on the second reference opens the target and
 * hands it to the dataset dataspace callback as if it were a dataset (src/H5R.c,
 * H5R__open_region_api_common), which crashes 2.3.0.
 *
 * Element 0 is an in-file control: it names the dataset, so a finding that fires
 * twice is visibly a walker bug.  The regime is ASSERTED, not assumed: the
 * helper resolves both references before writing them and fails unless element
 * 0 is a dataset and element 1 is the requested kind, so a library change that
 * started refusing (or retargeting) such references fails loudly here instead
 * of quietly producing a fixture that tests nothing.
 *
 * Object times are suppressed so the bytes are reproducible across runs.
 */
#include "hdf5.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(expr)                                                           \
    do {                                                                      \
        if ((expr) < 0) {                                                     \
            fprintf(stderr, "make_region_target_attr: failed: %s\n", #expr);  \
            return EXIT_FAILURE;                                              \
        }                                                                     \
    } while (0)

#define REQUIRE(cond, msg)                                                    \
    do {                                                                      \
        if (!(cond)) {                                                        \
            fprintf(stderr, "make_region_target_attr: %s\n", msg);            \
            return EXIT_FAILURE;                                              \
        }                                                                     \
    } while (0)

int
main(int argc, char **argv)
{
    hid_t      fid, dsp, did, gid, tid, asp, aid;
    hsize_t    dims[1]  = {16};
    hsize_t    adims[1] = {2};
    hsize_t    start[1] = {2};
    hsize_t    count[1] = {5};
    int        data[16];
    int        i, legacy;
    const char *target;
    H5O_type_t want, got;

    if (argc != 4 || (strcmp(argv[2], "group") && strcmp(argv[2], "datatype")) ||
        (strcmp(argv[3], "revised") && strcmp(argv[3], "legacy"))) {
        fprintf(stderr,
                "usage: make_region_target_attr FILE {group|datatype} {revised|legacy}\n");
        return EXIT_FAILURE;
    }
    target = strcmp(argv[2], "group") == 0 ? "g" : "t";
    want   = strcmp(argv[2], "group") == 0 ? H5O_TYPE_GROUP : H5O_TYPE_NAMED_DATATYPE;
    legacy = strcmp(argv[3], "legacy") == 0;

    for (i = 0; i < 16; i++)
        data[i] = i;

    CHECK(fid = H5Fcreate(argv[1], H5F_ACC_TRUNC, H5P_DEFAULT, H5P_DEFAULT));

    /* The dataset (reference control and attribute holder), a group, and a
     * committed datatype.  Each is created with times off; the group and the
     * datatype exist in every variant so the files differ only in the target. */
    {
        hid_t dcpl, gcpl, tcpl;
        CHECK(dcpl = H5Pcreate(H5P_DATASET_CREATE));
        CHECK(H5Pset_obj_track_times(dcpl, 0));
        CHECK(gcpl = H5Pcreate(H5P_GROUP_CREATE));
        CHECK(H5Pset_obj_track_times(gcpl, 0));
        CHECK(tcpl = H5Pcreate(H5P_DATATYPE_CREATE));
        CHECK(H5Pset_obj_track_times(tcpl, 0));

        CHECK(dsp = H5Screate_simple(1, dims, NULL));
        CHECK(did = H5Dcreate2(fid, "d", H5T_NATIVE_INT, dsp, H5P_DEFAULT, dcpl,
                               H5P_DEFAULT));
        CHECK(H5Dwrite(did, H5T_NATIVE_INT, H5S_ALL, H5S_ALL, H5P_DEFAULT, data));
        CHECK(gid = H5Gcreate2(fid, "g", H5P_DEFAULT, gcpl, H5P_DEFAULT));
        CHECK(H5Gclose(gid));
        CHECK(tid = H5Tcopy(H5T_NATIVE_INT));
        CHECK(H5Tcommit2(fid, "t", tid, H5P_DEFAULT, tcpl, H5P_DEFAULT));
        CHECK(H5Tclose(tid));

        CHECK(H5Pclose(tcpl));
        CHECK(H5Pclose(gcpl));
        CHECK(H5Pclose(dcpl));
    }
    CHECK(H5Sselect_hyperslab(dsp, H5S_SELECT_SET, start, NULL, count, NULL));
    CHECK(asp = H5Screate_simple(1, adims, NULL));

    if (legacy) {
        hdset_reg_ref_t ref[2];
        CHECK(H5Rcreate(&ref[0], fid, "d", H5R_DATASET_REGION, dsp));
        CHECK(H5Rcreate(&ref[1], fid, target, H5R_DATASET_REGION, dsp));
        CHECK(H5Rget_obj_type2(fid, H5R_DATASET_REGION, &ref[0], &got));
        REQUIRE(got == H5O_TYPE_DATASET, "element 0 does not name a dataset");
        CHECK(H5Rget_obj_type2(fid, H5R_DATASET_REGION, &ref[1], &got));
        REQUIRE(got == want, "element 1 does not name the requested kind");
        CHECK(aid = H5Acreate2(did, "regs", H5T_STD_REF_DSETREG, asp, H5P_DEFAULT,
                               H5P_DEFAULT));
        CHECK(H5Awrite(aid, H5T_STD_REF_DSETREG, ref));
    }
    else {
        H5R_ref_t ref[2];
        CHECK(H5Rcreate_region(fid, "d", dsp, H5P_DEFAULT, &ref[0]));
        CHECK(H5Rcreate_region(fid, target, dsp, H5P_DEFAULT, &ref[1]));
        CHECK(H5Rget_obj_type3(&ref[0], H5P_DEFAULT, &got));
        REQUIRE(got == H5O_TYPE_DATASET, "element 0 does not name a dataset");
        CHECK(H5Rget_obj_type3(&ref[1], H5P_DEFAULT, &got));
        REQUIRE(got == want, "element 1 does not name the requested kind");
        CHECK(aid = H5Acreate2(did, "regs", H5T_STD_REF, asp, H5P_DEFAULT,
                               H5P_DEFAULT));
        CHECK(H5Awrite(aid, H5T_STD_REF, ref));
        for (i = 0; i < 2; i++)
            CHECK(H5Rdestroy(&ref[i]));
    }

    CHECK(H5Aclose(aid));
    CHECK(H5Sclose(asp));
    CHECK(H5Dclose(did));
    CHECK(H5Sclose(dsp));
    CHECK(H5Fclose(fid));
    return EXIT_SUCCESS;
}
