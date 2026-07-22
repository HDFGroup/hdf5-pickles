/* Create a valid file that has BOTH a metadata cache image and a dense-link
 * group, for the cache-image traversal-boundary fixture.
 *
 * The point of the pairing: the cache image shadows only the addresses it
 * happens to cache, so a file like this has metadata on both sides of the
 * shadow.  h5policy must skip the shadowed objects and still vet the rest --
 * see _make_cache_image_shadowed_btree in h5policy-gencorpus, which corrupts a
 * structure on the UNSHADOWED side and asserts the walk still reaches it.
 *
 * Enough links are created to force dense (v2 B-tree + fractal heap) link
 * storage rather than a compact link message list.  Public APIs only: h5py
 * exposes neither the MDC-image FAPL setting nor the link phase-change knobs. */
#include <hdf5.h>
#include <stdio.h>

#define NLINKS 40

int main(int argc, char **argv)
{
    if (argc != 2)
        return 2;

    H5AC_cache_image_config_t image = {
        H5AC__CURR_CACHE_IMAGE_CONFIG_VERSION,
        true,
        false,
        H5AC__CACHE_IMAGE__ENTRY_AGEOUT__NONE
    };
    hid_t fapl = H5Pcreate(H5P_FILE_ACCESS);
    if (fapl < 0 || H5Pset_libver_bounds(fapl, H5F_LIBVER_LATEST,
                                         H5F_LIBVER_LATEST) < 0 ||
        H5Pset_mdc_image_config(fapl, &image) < 0)
        return 3;

    hid_t file = H5Fcreate(argv[1], H5F_ACC_TRUNC, H5P_DEFAULT, fapl);
    H5Pclose(fapl);
    if (file < 0)
        return 4;

    /* Force dense link storage: switch to it as soon as there is more than one
     * link, so NLINKS children are guaranteed to be indexed by a v2 B-tree. */
    hid_t gcpl = H5Pcreate(H5P_GROUP_CREATE);
    if (gcpl < 0 || H5Pset_link_phase_change(gcpl, 1, 0) < 0)
        return 5;

    /* arg 3 is the LINK creation plist; the group creation plist is arg 4. */
    hid_t group = H5Gcreate2(file, "dense", H5P_DEFAULT, gcpl, H5P_DEFAULT);
    H5Pclose(gcpl);
    if (group < 0)
        return 6;

    herr_t rc = 0;
    for (int i = 0; i < NLINKS && rc == 0; i++) {
        char name[32];
        snprintf(name, sizeof name, "link_%03d", i);
        hid_t child = H5Gcreate2(group, name, H5P_DEFAULT, H5P_DEFAULT,
                                 H5P_DEFAULT);
        if (child < 0)
            rc = -1;
        else if (H5Gclose(child) < 0)
            rc = -1;
    }

    if (H5Gclose(group) < 0)
        rc = -1;
    if (H5Fclose(file) < 0)
        rc = -1;
    return rc ? 7 : 0;
}
