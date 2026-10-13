/* Create a small, valid complex-number dataset for h5policy's corpus.
 *
 * h5py (the corpus writer) bundles libhdf5 1.14.x, which has no complex number
 * datatype class, so the class-11 fixtures cannot be produced from h5py.  This
 * helper uses the public HDF5 API against the installed 2.x h5cc instead.
 *
 * Usage: make_complex OUTPUT.h5
 *
 * The file holds one contiguous 1-D dataset "c" of four H5T_COMPLEX_IEEE_F64LE
 * values, written with the EARLIEST format bounds so the dataset's object
 * header is version 1 and carries no checksum.  That lets the malformed
 * sibling fixture byte-patch the datatype message in place (gencorpus
 * _make_complex_size_not_twice_base) without recomputing an object-header
 * checksum.  Requires libhdf5 >= 2.0 (complex number support). */
#include <hdf5.h>
#include <complex.h>
#include <stdio.h>

int main(int argc, char **argv)
{
    if (argc != 2)
        return 2;

    hsize_t             dims[1] = {4};
    double _Complex     data[4] = {1.0 + 1.0 * I, 2.0 + 0.5 * I,
                                   -3.0 - 4.0 * I, 0.25 + 8.0 * I};
    hid_t fapl = H5Pcreate(H5P_FILE_ACCESS);
    if (fapl < 0 ||
        H5Pset_libver_bounds(fapl, H5F_LIBVER_EARLIEST, H5F_LIBVER_LATEST) < 0)
        return 3;

    hid_t f = H5Fcreate(argv[1], H5F_ACC_TRUNC, H5P_DEFAULT, fapl);
    if (f < 0)
        return 3;

    hid_t s = H5Screate_simple(1, dims, NULL);
    hid_t dcpl = H5Pcreate(H5P_DATASET_CREATE);
    if (s < 0 || dcpl < 0 ||
        H5Pset_layout(dcpl, H5D_CONTIGUOUS) < 0 ||
        H5Pset_alloc_time(dcpl, H5D_ALLOC_TIME_EARLY) < 0)
        return 3;

    hid_t d = H5Dcreate2(f, "c", H5T_COMPLEX_IEEE_F64LE, s, H5P_DEFAULT, dcpl,
                         H5P_DEFAULT);
    if (d < 0)
        return 3;
    if (H5Dwrite(d, H5T_NATIVE_DOUBLE_COMPLEX, H5S_ALL, H5S_ALL, H5P_DEFAULT,
                 data) < 0)
        return 3;

    H5Dclose(d);
    H5Pclose(dcpl);
    H5Sclose(s);
    H5Pclose(fapl);
    H5Fclose(f);
    return 0;
}
