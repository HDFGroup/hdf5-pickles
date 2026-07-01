# HDF5 Fixtures

These fixtures exercise the Emacs GNU poke protocol against concrete HDF5
metadata layouts:

- `old_style_group.h5`: v1 symbol-table group.
- `dense_group.h5`: v2 dense group using a fractal heap and v2 B-tree.
- `chunk_v1_btree.h5`: classic v1 B-tree chunk index.
- `chunk_fixed_array.h5`: fixed-array chunk index.
- `chunk_extensible_array.h5`: extensible-array chunk index.
- `chunk_v2_btree.h5`: v2 B-tree chunk index.
- `nested_datatypes.h5`: nested compound and array datatype messages.

Regenerate them under the CMake build tree with:

```sh
python3 tests/fixtures/make_hdf5_fixtures.py build/tests/fixtures
```

The `emacs-check` CMake target does this automatically. The generator requires
`h5py` and `numpy`.
