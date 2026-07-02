# h5policy Tests

Regression corpus for the `h5policy` oracle.  Every fixture has an expected,
controlled outcome; a change that alters any decision is surfaced for review.

## Layout

- `expected/*.yml` — the tracked specification: one case per file with its
  profile, expected decision, expected exit code, required finding codes, and
  forbidden outcomes (`crash`, `timeout`, `external_open`, `plugin_load`,
  `write`).
- `unit_datatype.pk` — synthetic checks for the bounded, depth-guarded
  datatype validator (recursion cap and truncation handling), run under poke.
- `valid/ malformed/ policy/ resource/ coverage/ cve/` — generated fixtures
  (git-ignored build output; see below).

## Running

```sh
./run.sh
```

This regenerates the fixtures, runs the datatype unit checks, runs `h5policy`
over every `expected/*.yml` case and asserts the result, then runs the
differential harness.

The suite is also wired into CTest (top-level `CMakeLists.txt`), so
`ctest -R h5policy_regression` runs it from a CMake build. The test is skipped
if `poke` or `python3` + `h5py` are unavailable.

## Differential harness

`../tools/h5policy-diff` cross-checks h5policy's independent parse against
libhdf5, catching field-offset bugs that the corpus alone can miss:

- **h5py** is the structural reference — does libhdf5 open the bytes, and what
  external links / dataset shapes / on-disk datatype sizes does it report;
- **h5dump** / **h5debug** are independent "does libhdf5 accept these bytes"
  signals (optional; skipped if not on `PATH`).

It fails if h5policy calls a libhdf5-valid file corrupt (or vice versa),
disagrees on external references, or over-counts a dataset's **rank**. The
logical-**bytes** comparison is advisory: h5policy reads the declared on-disk
element size, which for padded compounds (and VLEN) legitimately differs from
libhdf5's packed `H5Tget_size` — using the larger declared size is the
conservative, correct choice for a security oracle. Run standalone with:

```sh
../tools/h5policy-diff --dir .        # or: ../tools/h5policy-diff FILE ...
```

## Fixtures

The `*.h5` files are **generated**, not committed, by
`../tools/h5policy-gencorpus` (requires `h5py`).  Regenerate them with:

```sh
../tools/h5policy-gencorpus .
```

Valid fixtures are written with `libver=latest`; malformed fixtures are
byte-patched from a valid base so we make no assumption about libhdf5 accepting
them.  `cve/` is reserved for minimized CVE seeds (see `h5policy.md` §12).
