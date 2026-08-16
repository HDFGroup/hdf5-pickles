# AGENTS instructions

## Scope

- The CVE workflow below applies only when a task involves a vulnerability
  specimen, advisory, OSS-Fuzz finding, or explicit CVE-case analysis.
- The documentation, generated-file, portable-provenance, boundary, and
  verification rules apply to every task.

## Companion repository: hdf5-ssp-sig

[`HDFGroup/hdf5-ssp-sig`](https://github.com/HDFGroup/hdf5-ssp-sig) is the
policy and audit consumer of selected H5Policy technical evidence. Do not
assume it is checked out at any particular local path.

- Producer contract in this repository: `registry/ssp-control-evidence.yml`
- Producer validator in this repository: `tools/check_ssp_control_evidence.py`
- Consumer contract in the SSP repository:
  `audit/registry/h5policy-control-evidence.json`

The contract is supplementary technical evidence, never a complete SSP-control
attestation. An SSP release-proof import must pin the producer revision and
contract digest, retain the producer-check output, and document SSP review of
the evidence it does not cover. When changing either contract, validate this
repository and the SSP consumer when it is available; otherwise report the
consumer check as skipped.

## Task modes

Classify the task before writing. The rows below resolve the write boundary when
the general documentation rule and the CVE workflow would otherwise overlap.

| Task | Permitted writes | Completion boundary |
| --- | --- | --- |
| Ordinary implementation or documentation | Files required by the requested change, subject to generated-file and boundary rules | Run the checks in [Verification](#verification) for the changed surface. |
| CVE case development | `cases/<id>/` and temporary build directories only | Complete the case bundle and its local hygiene check; do not promote tracked changes. |
| CVE promotion | None until the user approves the explicit promotion list | After approval, make only the listed tracked changes and run their verification. |

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
- `github-advisory.md` — the private repository-advisory handoff draft created
  by `h5cve init`; it is never an authorization to submit or publish.
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

### Private repository-advisory draft

For a repository security advisory, complete `cases/<id>/github-advisory.md`
after triage and verification. Its headings mirror the private draft form:

- title and whether an existing CVE identifier is supplied or one will be
  requested later;
- description with summary, impact, patches, workarounds, and references;
- one affected-product block per disjoint vulnerable range, naming ecosystem,
  package, affected and patched versions, and vulnerable functions;
- severity and CVSS vector, weaknesses, and optional credited contributors.

Use the form's version-range syntax: one lower/upper-bound range such as
`>= lower, < upper` per affected-product block, with a separate block for each
disjoint range. Do not create a draft, invite collaborators, request an
identifier, or publish an advisory without explicit user authorization. The
repository form requires appropriate repository permissions; if the user lacks
them, hand off the completed local draft to an authorized maintainer instead.

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
- A promotion must not add a tracked reference to a case artifact, including a
  specimen, probe, log, or report under `cases/<id>/`. Promote a reproducible
  fixture, generator, checksum-backed provenance record, or an explicit `n/a`
  limitation instead. Before promotion, inspect added tracked lines with
  `git diff -- <promotion paths> | rg '^\+.*cases/[A-Za-z0-9_][A-Za-z0-9_.-]*/'`.
- Before handing off a bundle, run `python3 tools/check_hygiene.py --paths
  cases/<id>` and correct every reported portable-provenance or identifier
  violation.

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
- `registry/libhdf5-evidence.yml` is generated by `h5cve evidence` (do not
  hand-edit) and carries a per-family measured verdict. Regenerating it — e.g.
  to record a new fixture or to re-measure a libhdf5 version — can flip a family
  verdict, and `check_registry.py` requires each family's hand-maintained
  `validators.hdf5` claim in `registry/validation-coverage.yml` to equal the
  measured verdict. So a measurement refresh cascades: reconcile the affected
  `validators.hdf5` claims (and any `registry/ssp-control-evidence.yml` rows that
  cite that family's verdict) in the same change, and keep the contract's pinned
  `libhdf5_version` matching the build you measured.

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

`tools/check_hygiene.py` enforces the portable-path and prohibited-identifier
rules over tracked files as part of `docs-check`. Its default does not gate all
of `cases/`: that tree is gitignored scratch, regenerated per machine, so a
failure there would be unfixable by any commit. The explicit per-bundle command
in [Write and promotion boundary](#write-and-promotion-boundary) closes that
gap before handoff; `portable_path()` remains the generator-side prevention.

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

Choose checks from this matrix in addition to narrow tests that exercise the
changed behavior. If a listed command cannot run, report the omission and why.

| Changed surface | Required verification |
| --- | --- |
| Markdown, command examples, or documentation behavior | `cmake --build build --target docs-check` |
| `docs/spec/*.yml`, `pickles/*.pk`, or `docs/generated/*.md` | Regenerate with the documented workflow, then run `cmake --build build --target docs-check` |
| `registry/`, `registry/findings/`, or finding routes | `python3 tools/check_registry.py`; also run `docs-check` when documentation changed |
| `h5policy/` validators, wrappers, or corpus expectations | The focused test plus `h5policy/tests/run.sh` when the change affects shared validation behavior |
| `tools/h5cve`, provenance emitters, or hygiene tooling | The focused test plus `python3 tools/check_quickstart.py` when its canary inventory contract is affected |
| Repository-advisory draft generation | `python3 tools/check_advisory_draft.py` and `python3 tools/check_hygiene.py --paths cases/<id>` for the real bundle |
| CVE bundle under `cases/<id>/` | `python3 tools/check_hygiene.py --paths cases/<id>` and the measured case commands |

- Run tests appropriate to the changed surface, including documentation checks
  for documentation changes.
- Check generated artifacts against their sources when either changes.
- Report the commands run, failures, and any skipped checks in the handoff.

## References

- [CVE strategy for the HDF5 library](docs/A%20CVE%20strategy%20for%20the%20HDF5%20library.md)
- [What is bounded raw decode?](docs/What%20is%20bounded%20raw%20decode.md)
