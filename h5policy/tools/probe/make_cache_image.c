/* Create a small, valid metadata-cache-image fixture for h5policy's corpus.
 * This uses only public HDF5 APIs because h5py does not expose the MDC-image
 * FAPL setting. */
#include <hdf5.h>

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
    hid_t group = H5Gcreate2(file, "indexed", H5P_DEFAULT, H5P_DEFAULT,
                             H5P_DEFAULT);
    hid_t space = H5Screate_simple(1, (hsize_t[]){8}, NULL);
    hid_t dataset = H5Dcreate2(group, "payload", H5T_STD_I32LE, space,
                               H5P_DEFAULT, H5P_DEFAULT, H5P_DEFAULT);
    int values[8] = {0, 1, 2, 3, 4, 5, 6, 7};
    herr_t rc = group < 0 || space < 0 || dataset < 0 ||
                H5Dwrite(dataset, H5T_NATIVE_INT, H5S_ALL, H5S_ALL,
                         H5P_DEFAULT, values) < 0;
    if (dataset >= 0) H5Dclose(dataset);
    if (space >= 0) H5Sclose(space);
    if (group >= 0) H5Gclose(group);
    if (H5Fclose(file) < 0)
        rc = 1;
    return rc ? 5 : 0;
}
