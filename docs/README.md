# Documentation workflow

The generated format reference starts at the
[H5Lens HDF5 File Format Reference](generated/README.md) landing page.

Specification Markdown is generated from two sources of truth:

- **`pickles/*.pk`** — the executable format definitions (shared constants,
  structure, types, and constraints)
- **`docs/spec/*.yml`** — prose sidecars (field descriptions, introductory text,
  version notes, cross-references)

The generator lives in `tools/pkdoc.py` and requires PyYAML (`pip install pyyaml`).

## Generate

Run from the repository root:

```sh
cmake -S . -B build
cmake --build build --target docs
```

Output lands in `docs/generated/<name>.md`.

## Check consistency

The `--check` flag verifies that every type and field name in the sidecar
actually appears in the corresponding pickle, catching stale documentation
after a rename. The same target executes every GNU poke command block in
[`TUTORIAL.md`](../TUTORIAL.md) against disposable files and checks the
documented h5policy cache-image boundary against live reports from every
profile. It also checks the root h5patch overview against the authoritative
repair catalog:

```sh
cmake --build build --target docs-check
```

Exit code 0 = clean; 1 = issues found. The tutorial check is skipped when GNU
poke is unavailable.

## Adding a new pickle

1. Write `docs/spec/<pickle-stem>.yml` using the schema below.
2. Add `<pickle-stem>` to `PKDOC_SPECS` in `CMakeLists.txt`.
3. Run `cmake --build build --target docs-check` to confirm all names resolve.
4. Run `cmake --build build --target docs` to generate the Markdown.
5. Commit both the sidecar and the generated file together.

## Sidecar schema

```yaml
pickle: foo.pk          # which pickle this documents (required)
section: "V.B. Title"  # becomes the H1 heading
intro: |               # introductory prose (plain Markdown)
  …

types:
  TypeName:
    desc: "One-sentence description of the type."
    layouts:           # optional four-byte-wide format diagrams
      - title: "TypeName"
        rows:          # every row must total exactly four columns
          - [{label: "Signature", span: 4}]
          - ["Version", "Flags", {label: "Reserved", span: 2}]
          - [{label: "Object Address", span: 4, width: O}]
          - [{label: "Object Length", span: 4, width: L}]
        note: "`O` is the size of offsets; `L` is the size of lengths."
    fields:             # top-level fields of the struct, in order
      field_name:
        desc: "What this field means."
        note: "Optional italicised note (version caveat, units, etc.)."
    variants:           # union arms (named after the arm identifier in the pickle)
      arm_name:
        desc: "When this arm is active and what it means."
        fields:
          field_name:
            desc: "…"
```

Fields and variants may be nested to any depth by adding a `variants:` key
inside a variant entry.
