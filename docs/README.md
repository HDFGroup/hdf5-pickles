# Documentation workflow

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
after a rename:

```sh
cmake --build build --target docs-check
```

Exit code 0 = clean; 1 = issues found.  Wire this into CI so drift is
caught automatically when a pickle field is renamed.

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
