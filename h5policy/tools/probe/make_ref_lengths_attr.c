/* Create a file whose ATTRIBUTE values hold revised references carrying the
 * self-described lengths libhdf5's reference decoder trusts.
 *
 * Built through the C API for the same reason as make_stdref_attr.c: the local
 * h5py links libhdf5 1.14.5 and cannot write H5T_STD_REF.
 *
 * Two attributes on dataset "d":
 *
 *   objs   two internal H5R_OBJECT2 references.  Not blob-backed:
 *          H5T__ref_disk_write stores the encoding inline in the element,
 *            [type:1][flags:1][token_size:1][token][zero padding]
 *          so the token length is METADATA here, inside the attribute message.
 *   attrs  two H5R_ATTR references to d@"target_attribute".  Element 0 is
 *          internal; element 1 is EXTERNAL -- created against a second file --
 *          so its global-heap blob is
 *            [token_size:1][token][file name len:2][file name][attr name len:2][attr name]
 *          and a walker must step over the file name to find the attribute name.
 *
 * The external target file is written next to the output and may be deleted:
 * nothing in the output is resolved against it.
 *
 * The regime is asserted, not assumed: the helper reads both attributes back
 * and exits non-zero unless the object references are internal and the second
 * attribute reference is external, so a library that changed either encoding
 * fails generation instead of producing fixtures that test nothing.
 *
 * Object times are suppressed -- the root group's too -- so the bytes are
 * reproducible across runs.
 *
 * Usage: make_ref_lengths_attr OUTPUT.h5 EXTERNAL_TARGET.h5 [OFFSET_SIZE]
 *
 * OFFSET_SIZE sets the superblock's sizeof_offsets/sizeof_lengths (default 8);
 * the inline token's room is o + 7, so a smaller width moves the bound.
 */
#include "hdf5.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(expr)                                                           \
    do {                                                                      \
        if ((expr) < 0) {                                                     \
            fprintf(stderr, "make_ref_lengths_attr: failed: %s\n", #expr);    \
            return EXIT_FAILURE;                                              \
        }                                                                     \
    } while (0)

static hid_t
make_target(const char *path, hid_t fcpl, hid_t ocpl)
{
    hsize_t one[1] = {1};
    int     v      = 1;
    hid_t   fid, sp, did, aid;

    if ((fid = H5Fcreate(path, H5F_ACC_TRUNC, fcpl, H5P_DEFAULT)) < 0)
        return -1;
    sp  = H5Screate_simple(1, one, NULL);
    did = H5Dcreate2(fid, "d", H5T_NATIVE_INT, sp, H5P_DEFAULT, ocpl, H5P_DEFAULT);
    aid = H5Acreate2(did, "target_attribute", H5T_NATIVE_INT, sp, H5P_DEFAULT, H5P_DEFAULT);
    if (sp < 0 || did < 0 || aid < 0 || H5Awrite(aid, H5T_NATIVE_INT, &v) < 0)
        return -1;
    H5Aclose(aid);
    H5Dclose(did);
    H5Sclose(sp);
    return fid;
}

int
main(int argc, char **argv)
{
    hid_t      fcpl, ocpl, fid, xfid, did, asp, aid;
    hsize_t    two[1] = {2};
    H5R_ref_t  obj[2], att[2], back[2];
    H5R_type_t t;
    int        i;

    if (argc != 3 && argc != 4) {
        fprintf(stderr, "usage: make_ref_lengths_attr OUTPUT.h5 EXTERNAL_TARGET.h5 [OFFSET_SIZE]\n");
        return EXIT_FAILURE;
    }
    /* The file-creation list carries object-creation properties for the root
     * group, which otherwise records wall-clock times. */
    CHECK(fcpl = H5Pcreate(H5P_FILE_CREATE));
    CHECK(H5Pset_obj_track_times(fcpl, 0));
    if (argc == 4)
        CHECK(H5Pset_sizes(fcpl, (size_t)atoi(argv[3]), (size_t)atoi(argv[3])));
    CHECK(ocpl = H5Pcreate(H5P_DATASET_CREATE));
    CHECK(H5Pset_obj_track_times(ocpl, 0));
    CHECK(fid = make_target(argv[1], fcpl, ocpl));
    CHECK(xfid = make_target(argv[2], fcpl, ocpl));

    CHECK(H5Rcreate_object(fid, "d", H5P_DEFAULT, &obj[0]));
    CHECK(H5Rcreate_object(fid, "/", H5P_DEFAULT, &obj[1]));
    CHECK(H5Rcreate_attr(fid, "d", "target_attribute", H5P_DEFAULT, &att[0]));
    CHECK(H5Rcreate_attr(xfid, "d", "target_attribute", H5P_DEFAULT, &att[1]));

    CHECK(did = H5Dopen2(fid, "d", H5P_DEFAULT));
    CHECK(asp = H5Screate_simple(1, two, NULL));
    CHECK(aid = H5Acreate2(did, "objs", H5T_STD_REF, asp, H5P_DEFAULT, H5P_DEFAULT));
    CHECK(H5Awrite(aid, H5T_STD_REF, obj));
    CHECK(H5Aclose(aid));
    CHECK(aid = H5Acreate2(did, "attrs", H5T_STD_REF, asp, H5P_DEFAULT, H5P_DEFAULT));
    CHECK(H5Awrite(aid, H5T_STD_REF, att));
    CHECK(H5Aclose(aid));
    for (i = 0; i < 2; i++) {
        CHECK(H5Rdestroy(&obj[i]));
        CHECK(H5Rdestroy(&att[i]));
    }

    /* Regime: both object references internal, attribute reference 1 external
     * (H5Rget_file_name names the other file), attribute reference 0 not. */
    CHECK(aid = H5Aopen(did, "objs", H5P_DEFAULT));
    CHECK(H5Aread(aid, H5T_STD_REF, back));
    CHECK(H5Aclose(aid));
    for (i = 0; i < 2; i++) {
        if ((t = H5Rget_type(&back[i])) != H5R_OBJECT2) {
            fprintf(stderr, "make_ref_lengths_attr: objs[%d] is type %d, not H5R_OBJECT2\n", i, (int)t);
            return EXIT_FAILURE;
        }
        CHECK(H5Rdestroy(&back[i]));
    }
    CHECK(aid = H5Aopen(did, "attrs", H5P_DEFAULT));
    CHECK(H5Aread(aid, H5T_STD_REF, back));
    CHECK(H5Aclose(aid));
    {
        char name0[256], name1[256];
        if (H5Rget_type(&back[0]) != H5R_ATTR || H5Rget_type(&back[1]) != H5R_ATTR ||
            H5Rget_file_name(&back[0], name0, sizeof name0) < 0 ||
            H5Rget_file_name(&back[1], name1, sizeof name1) < 0) {
            fprintf(stderr, "make_ref_lengths_attr: attrs are not two readable H5R_ATTR references\n");
            return EXIT_FAILURE;
        }
        /* An internal reference reports the file it was read from; an external
         * one reports the file it was created against. */
        if (strcmp(name1, argv[2]) != 0 || strcmp(name0, argv[1]) != 0) {
            fprintf(stderr, "make_ref_lengths_attr: attrs[1] is not external to %s\n", argv[1]);
            return EXIT_FAILURE;
        }
    }
    for (i = 0; i < 2; i++)
        CHECK(H5Rdestroy(&back[i]));

    CHECK(H5Sclose(asp));
    CHECK(H5Dclose(did));
    CHECK(H5Fclose(xfid));
    CHECK(H5Fclose(fid));
    CHECK(H5Pclose(ocpl));
    CHECK(H5Pclose(fcpl));
    return EXIT_SUCCESS;
}
