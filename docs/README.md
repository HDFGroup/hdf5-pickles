# H5Lens documentation

## Reader guide

The generated format reference starts at the
[H5Lens HDF5 File Format Reference](generated/README.md) landing page.
For the repository entry points and the dependencies between them, see the
[tool overview](tool-overview.md).

Start with [H5Lens in 10 Minutes](FIRST_10_MINUTES.md) to install the toolchain,
inspect a file, and interpret a policy finding. Continue with the [H5Lens
tutorial](TUTORIAL.md) for guided exploration through `h5explain`. The
[HDF5 file assessment workflow](H5POLICY_WORKFLOW.md) explains how to select an
`h5policy` profile, run the bounded preflight, interpret completeness and
findings, trace the evidence behind a classification, judge invariant-coverage
completeness, and act on the decision. The
[low-level GNU poke tutorial](POKE_TUTORIAL.md) exposes the underlying mappings,
and [Writing HDF5 with GNU poke](POKE_CONSTRUCTION.md) keeps write-through and
construction exercises in an explicitly advanced path. For repository-specific
vocabulary used by the policy corpus and CVE workflow, see the
[glossary](GLOSSARY.md).

Architecture and provenance references include the [bounded raw-decode
model](What%20is%20bounded%20raw%20decode.md), the [file-format evolution
matrix](HDF5%20File%20Format%20Specification%20Evolution.md), and the
[object-store mapping](Mapping%20HDF5%20Binary%20Primitives%20onto%20an%20Object%20Store.md),
which is a design proposal rather than an implemented subsystem. Security-case
work follows the separate [CVE strategy](A%20CVE%20strategy%20for%20the%20HDF5%20library.md).
The [H5PL policy-profile API extension](H5PL_POLICY_PROFILE_API.md) is a draft
upstream-facing design for carrying the four h5policy profile identities into
native HDF5 plugin decisions and constructing user-defined blends with the same
profile structure; it is not an implemented API.

## Contributor workflow

Each specification page is generated from two sources of truth:

- **`pickles/*.pk`** — the executable format definitions (shared constants,
  structure, types, and constraints)
- **`docs/spec/*.yml`** — prose sidecars (field descriptions, introductory text,
  version notes, cross-references)

The upstream section hierarchy, coverage status, and generated landing page are
defined by **`docs/spec/index.yml`**. The manifest follows the
[HDF5 File Format Specification Version 4.0](https://support.hdfgroup.org/documentation/hdf5/latest/_f_m_t4.html)
and records when that hierarchy was last reviewed. It is a navigation and
coverage contract; the pickles remain authoritative for what H5Lens decodes.

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
after a rename. It also checks upstream section mappings, coverage states,
layout-to-type and layout-to-field references, and byte-compares every tracked
generated page with freshly rendered output. The same target executes the
`h5explain` commands in
[`TUTORIAL.md`](TUTORIAL.md), the direct mappings in
[`POKE_TUTORIAL.md`](POKE_TUTORIAL.md), and the disposable write and
construction sessions in [`POKE_CONSTRUCTION.md`](POKE_CONSTRUCTION.md). It
also checks the documented h5policy cache-image boundary against live reports
from every profile, the root h5patch entry points against the authoritative
repair catalog, and the documented h5explain navigation-history semantics
against the implementation. The h5policy assessment workflow's profiles,
decision table, finding inventory, invariant coverage, and assurance counts are
checked against the command-line and registry contracts. The first-ten-minutes
guide runs its inspection and policy commands and checks the canary inventory
against its source mappings. The lazy-validation ratios are derived from the
tracked measurement before its deterministic fields are reproduced. The
profile tables, command help surfaces, marker inventory, Mermaid tool overview,
and Codespaces configuration retain their own structural checks. Relative
targets in tracked Markdown links are also checked, without fetching external
URLs:

```sh
cmake --build build --target docs-check
```

Exit code 0 = clean; 1 = issues found. The tutorial check is skipped when GNU
poke is unavailable.

## Adding a new pickle

1. Write `docs/spec/<pickle-stem>.yml` using the schema below.
2. Map its upstream sections and coverage in `docs/spec/index.yml`.
3. Add `<pickle-stem>` to `PKDOC_SPECS` in `CMakeLists.txt`.
4. Run `cmake --build build --target docs` to generate the Markdown and landing
   page.
5. Run `cmake --build build --target docs-check` to confirm mappings, names,
   links, and generated output.
6. Commit the sidecar, manifest, and generated files together.

## Sidecar schema

```yaml
pickle: foo.pk          # which pickle this documents (required)
section: "V.B. Title"  # becomes the H1 heading
upstream:               # canonical v4.0 mapping (required)
  version: "4.0"
  sections: [V.B]
  anchor: subsec_fmt4_example
coverage: partial       # covered, partial, or not-covered
type_order: [TypeName]  # optional specification-facing render order
intro: |               # introductory prose (plain Markdown)
  …

types:
  TypeName:
    title: "Specification-facing type name"
    desc: "One-sentence description of the type."
    layouts:           # optional four-byte-wide format diagrams
      - title: "TypeName"
        rows:          # every row must total exactly four columns
          - [{field: signature, label: "Signature", span: 4}]
          - ["Version", "Flags", {label: "Reserved", span: 2}]
          - [{label: "Object Address", span: 4, width: O}]
          - [{label: "Object Length", span: 4, width: L}]
        note: "`O` is the size of offsets; `L` is the size of lengths."
    fields:             # top-level fields of the struct, in order
      field_name:
        label: "Specification-facing field name"
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
inside a variant entry. `title` and `label` are optional; the generator derives
a readable fallback while retaining the exact pickle identifier in a separate
column. A layout `field:` must name a documented field in its bound type. A
page-level layout can use `type: TypeName` to place it beside that type's
fields table. When `type_order` is present it must list every documented type
exactly once.

## Coverage manifest

`docs/spec/index.yml` contains the complete upstream I–VIII hierarchy. Every
section has one of three statuses:

- `covered`: an executable pickle definition and field documentation exist
- `partial`: only part of the section or its variants is documented
- `not-covered`: there is no first-class H5Lens format page

Use `doc: <pickle-stem>` to link covered or partial sections to a generated
page. A sidecar can declare multiple upstream sections when one executable
definition spans the upstream organization. CI does not fetch the website;
upstream review is deliberate, and the checked-in version and review date make
changes auditable.
