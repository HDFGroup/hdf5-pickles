# AGENTS instructions

## Scope

- The CVE workflow below applies only when a task involves a vulnerability
  specimen, advisory, OSS-Fuzz finding, or explicit CVE-case analysis.
- The documentation, generated-file, portable-provenance, boundary, and
  verification rules apply to every task.

## CVE case workflow

Apply the [§11 CVE process](docs/A%20CVE%20strategy%20for%20the%20HDF5%20library.md)
to each specimen. Prefer `tools/h5cve` for the workflow it supports.

### Required artifacts

Produce a complete, self-contained bundle under `cases/<id>/`:

- `case.yml` — the machine-readable record based on
  [`registry/cve-case.yml`](registry/cve-case.yml).
- `CASE.md` — the narrative case record, suitable for a CVE submission or for
  confirming that no vulnerability is present.
- `source-audit.md` — the source-level audit.
- Reproducers, probe sources, command transcripts, reports, and other evidence
  needed to support the conclusions.

These must be real artifacts with filled, measured fields, not sketches.

`<id>` follows the convention already in that tree — `md5(input.h5)`, or a short
descriptive slug for a hand-built specimen. Never name a bundle after an
advisory.

### Evidence requirements

- Use local evidence only: no web fetches, publishing, messages, or other
  outbound actions. If advisory text or another unavailable source would affect
  a conclusion, record that limitation.
- Record the current Git commit and dirty-worktree state, specimen hashes, tool
  and library versions, exact commands, exit codes, and baseline/candidate build
  identities.
- Label conclusions as measured, source-derived, inferred, or unmeasured. Never
  present an unavailable platform result as measured.
- Consider 32-bit and 64-bit behavior and other relevant platform differences.
  Run representative platforms when locally available; otherwise document the
  gap and the arithmetic, ABI, or layout risks that remain.
- Measure the oracle verdict, but do not make existing rejection the primary
  conclusion. Identify the violated invariant, affected entry points, exact-build
  behavior, activation boundary, sibling variants, and remaining coverage gaps.

### Existing case bundles

Treat existing `cases/<id>/` contents as unverified prior work. Preserve
hand-written probes and potentially useful artifacts, but regenerate
measurements against current HEAD and replace TODOs or unsupported assertions.

### Write and promotion boundary

- During case development, write only under `cases/<id>/` and temporary build
  directories. `cases/` is gitignored, so nothing there is recoverable through
  Git — back it up before any bulk rewrite, rename, or delete across bundles.
- Do not modify tracked corpus, generators, `registry/`, or `h5policy/tests/`.
  Do not use `h5policy-gencorpus` to rewrite a tracked destination.
- List proposed tracked changes as explicit promotion steps. Stop and let the
  user decide whether to promote them.

## Documentation

- Update relevant documentation when behavior, commands, APIs, paths, tools, or
  generated output change.
- Make new documentation contracts testable. Add or extend a documentation test
  when introducing behavior that can drift; do not add redundant CI wiring when
  an existing target already covers it.
- Run existing documentation checks, normally:

  ```sh
  cmake --build build --target docs-check
  ```

- If a required check cannot run, report what was skipped and why.

## Generated files

- Never edit generated files directly when a generation workflow exists.
- `docs/generated/*.md` is generated from `docs/spec/*.yml` and `pickles/*.pk`
  with `tools/pkdoc.py`. Edit the sources, regenerate, and run `docs-check`.

## Portable provenance

Records outlive the machine that produced them, so they must identify a build, a
specimen, or a tool without recording where this particular machine keeps it.
This constrains *how* to satisfy the CVE evidence rules, not whether to: both are
satisfiable at once.

- Name builds by role: **baseline** (Release, asserts off) and **candidate**
  (asserts live, sanitizers). Pin them with `settings_sha256`, `build_mode`, and
  `sanitizers`, which identify a build exactly, and say "workstation-local
  installs; paths not recorded". A path is not what makes a build reproducible.
- Identify a specimen by its sha256 and its in-repo bundle path, never by the
  external directory it arrived from.
- Inside the repo, write repo-relative paths. Outside it, keep the basename
  only — for a shared library, the soname.
- **If a generator emits a host path, fix the generator.** Editing its output
  alone leaves the next run to undo the fix. `tools/h5cve` and
  `h5policy/tools/h5policy-probe` each carry a `portable_path()` applied at
  emission for this reason; the values they hold internally stay absolute,
  because `h5cc` drives the sibling-lib lookup and the probe build-cache key.

`tools/check_hygiene.py` enforces both this section and the two `Never` rules
below, over tracked files, as part of `docs-check`. It cannot gate `cases/` —
that tree is gitignored scratch, regenerated per machine, so a failure there
would be unfixable by any commit; the `portable_path()` calls above are what
keep it clean.

## Boundaries

### Ask first

- Refactors that move ownership or public interfaces across multiple top-level
  packages.
- New runtime or build dependencies.
- Destructive data changes or migrations.

### Never

- Commit secrets, credentials, or tokens.
- Introduce `GHSA-*` identifiers **anywhere in the repository** — record fields,
  prose, comments, commit messages, file names, or directory names, in either
  the canonical `GHSA-xxxx-yyyy-zzzz` spelling or a `ghsa_xxxx_yyyy_zzzz` slug.
  They are not authoritative here. Use OSS-Fuzz identifiers when applicable.
- Record host paths — `$HOME`, build install prefixes, external specimen stores —
  in any file under `registry/`, `cases/`, or the tracked tree. See
  [Portable provenance](#portable-provenance).
- Use destructive Git operations unless explicitly requested.

## Verification

- Run tests appropriate to the changed surface, including documentation checks
  for documentation changes.
- Check generated artifacts against their sources when either changes.
- Report the commands run, failures, and any skipped checks in the handoff.

## References

- [CVE strategy for the HDF5 library](docs/A%20CVE%20strategy%20for%20the%20HDF5%20library.md)
- [What is bounded raw decode?](docs/What%20is%20bounded%20raw%20decode.md)
