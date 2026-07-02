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

This regenerates the fixtures, runs the datatype unit checks, then runs
`h5policy` over every `expected/*.yml` case and asserts the result.

## Fixtures

The `*.h5` files are **generated**, not committed, by
`../tools/h5policy-gencorpus` (requires `h5py`).  Regenerate them with:

```sh
../tools/h5policy-gencorpus .
```

Valid fixtures are written with `libver=latest`; malformed fixtures are
byte-patched from a valid base so we make no assumption about libhdf5 accepting
them.  `cve/` is reserved for minimized CVE seeds (see `h5policy.md` §12).
