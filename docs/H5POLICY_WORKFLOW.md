# Assessing an HDF5 File with `h5policy`

`h5policy` is the read-only metadata preflight step to run before an HDF5
consumer opens a file from the assessed trust boundary. It parses the file with
GNU poke, independently of `libhdf5`, validates the reachable metadata it
understands, applies a security profile, and returns one JSON report.

An `accept` decision is deliberately narrow: it approves the metadata reached
under the selected profile. It does not approve dataset payloads, external
targets, plugins, decompression, a particular `libhdf5` build, or application
deserialization.

## Assessment boundary

During an assessment, `h5policy` does not:

- call `libhdf5`;
- load filter or VFD plugins;
- decompress or deserialize dataset payloads;
- open files named by external links, external storage, or VDS mappings;
- repair or write the input.

This makes the preflight suitable for hostile input, but it also defines how to
read the result. A later consumer can cross boundaries that `h5policy` only
identified in metadata. Those activations need their own controls.

## Workflow at a glance

```mermaid
flowchart LR
  profile["1. Select the profile"] --> open["2. Start a bounded,<br/>read-only analysis"]
  open --> geometry["3. Locate the superblock<br/>and establish geometry"]
  geometry --> walk["4. Validate reachable<br/>metadata and apply policy"]
  walk --> special["5. Complete cache-image replay<br/>or forensic-only checks"]
  special --> report["6. Classify findings<br/>and emit JSON"]
  report --> action["7. Check completeness,<br/>then decide what may proceed"]
```

### 1. Select the profile

Choose the profile from the file's trust context before looking at the desired
outcome. Changing profiles changes the assessment question; it is not a way to
turn an inconvenient rejection into an acceptance.

| Profile | Use in an assessment |
| --- | --- |
| `untrusted-strict` | Default for files that cross a trust boundary. It uses tight budgets and denies risky features by default. |
| `trusted-fast` | For files from a controlled source when external references, VDS, and filters are expected and separately controlled. |
| `legacy` | For compatibility investigation. It permits legacy features and broad data budgets, while retaining bounded analysis. |
| `forensic` | For deeper bounded diagnostics. It uses non-strict mapping, continues reporting, and performs its defined unreachable-metadata sweep without following external references. |

Corrupt metadata is rejected by every profile. The complete, implementation-
level profile contract is in
[`H5PolicyProfile`: Current Semantics](../h5policy/docs/H5PolicyProfile.md).

### 2. Run the bounded, read-only preflight

Run from the repository root. Capture standard output and the process status;
diagnostics remain on standard error.

```sh
if ./tools/h5policy --profile untrusted-strict suspect.h5 \
    > h5policy-report.json; then
    status=0
else
    status=$?
fi
python3 -m json.tool h5policy-report.json >/dev/null
printf 'h5policy status: %s\n' "$status"
```

Statuses `1` through `5` are normal policy verdicts when accompanied by a valid
JSON report. Command-line and file-open failures can also exit nonzero without
a report, so automation must never interpret the status alone. Require valid
JSON and a supported `schema_version` before using `decision`.

The selected profile supplies deterministic operation and time budgets. The
wrapper also imposes a hard wall-clock backstop. A budget or timeout does not
become an acceptance; it produces an explicit coverage-gap result.

### 3. Establish file geometry

The analyzer locates the HDF5 signature at a legal superblock offset, including
files with a user block. Before attacker-controlled widths can size later
mappings, it preflights the superblock's offset and length widths. It then
validates the superblock and establishes:

- the physical file size;
- the declared end-of-address value (EOA), when available;
- the effective address ceiling used by validation;
- the HDF5 base address used to translate format addresses to physical file
  offsets;
- any bytes physically trailing the declared EOA.

Trailing bytes are reported as geometry, not treated as corruption by
themselves.

### 4. Validate reachable metadata and apply policy

The reachable walk starts with the superblock extension, when present, and the
root object header. A bounded breadth-first traversal follows in-file metadata
references and deduplicates visited structures. As each structure is decoded,
`h5policy`:

- checks record envelopes, versions, lengths, address ranges, checksums, and
  record-local invariants;
- validates relationships among messages, indexes, heaps, object headers, and
  file-global metadata that it reaches;
- records security-relevant features such as external links, external storage,
  VDS mappings, filters, unknown messages, rank, and logical dataset size;
- charges metadata, objects, attributes, chunks, traversal depth, and walk work
  against the selected profile;
- emits stable findings with a class, code, object or metadata role, byte
  location when known, and typed comparison evidence when applicable.

Policy, structural, resource, and coverage checks occur during the same bounded
walk. With continuation disabled, a rejecting finding stops the remaining
traversal. The `forensic` profile enables continuation by default; the
`--continue-after-rejection` option enables it explicitly for any profile. It
keeps collecting reachable diagnostics but does not weaken a check or change
the final decision's precedence.

### 5. Complete special validation paths

A metadata cache image is validated in two passes. The first pass validates the
image envelope, entries, dependencies, extents, and checksum. The second uses an
in-memory read overlay to replay every validated cached body through the normal
type-aware metadata decoders. Unreached cache clients remain an explicit
coverage gap; the input is never rewritten.

The `forensic` profile also performs its defined raw-byte sweep for hazardous
metadata outside the normal reachable graph. This is additional anomaly
detection, not payload decoding and not permission to follow an external
reference.

### 6. Classify findings and emit the report

Every finding contributes a class. If several classes occur, the highest
precedence determines the decision: internal error, corruption, policy,
resource, unsupported coverage, then warning. With no findings, the result is
acceptance. Finding order does not determine the result.

| Exit | Decision | Meaning |
| ---: | --- | --- |
| `0` | `accept` | Reachable metadata passed the selected profile. |
| `1` | `accept_with_warnings` | The file passed with non-rejecting findings that require review. |
| `2` | `reject_corrupt` | Metadata violated a structural invariant. |
| `3` | `reject_policy` | A recognized feature is denied by the selected profile. |
| `4` | `reject_resource` | A resource or denial-of-service limit was exceeded. |
| `5` | `unsupported_coverage_gap` | Validation stopped safely at an unsupported representation, compatibility guard, or analysis limit. |
| `70` | `internal_error` | The validator failed to produce a normal assessment. |

The JSON report is the assessment record. Preserve it with the exact command,
process status, tool revision, input hash, and trust context when the decision
supports an audit or release gate.

### 7. Interpret the report before acting

Read a report in this order:

1. Confirm it is valid JSON with a supported `schema_version`, the expected
   `profile`, and the intended input in `file`.
2. Read `decision`, but also require `analysis.complete` for a claim that the
   reachable walk completed without dropping findings. Use `walk_started`,
   `walk_completed`, `stop_reason`, and `findings_truncated` to explain an
   incomplete result.
3. Check `analysis.extent_overlap_truncated`. When true, the overall walk may be
   complete while the bounded raw-data-versus-metadata overlap check has only
   partial coverage.
4. Review every `findings[]` entry. Use `code` as the stable identifier;
   `object`, `offset`, and optional `evidence` identify what produced it.
5. Review `features` for activations the eventual consumer may perform and
   `metrics` for the size and shape of the analyzed graph.
6. Confirm the `boundary` object is compatible with the intended next step. Its
   `false` values record operations the assessment did not perform.

An empty finding list is not a substitute for this sequence. In particular, a
tool failure, incomplete walk, unexpected profile, or unsupported report schema
must not be treated as a clean file.

`analysis.complete` is a per-file traversal statement. It means the implemented
walk finished for this input without dropping findings; it does not mean that
every HDF5 representation or every security invariant has been implemented and
verified.

## Evidence base and finding provenance

The evidence is layered so the oracle does not prove itself by repeating its
own decision. Each layer supports a different claim:

| Evidence layer | Authoritative artifacts | What it supports |
| --- | --- | --- |
| Format interpretation | Executable [`pickles/`](../pickles/) and [`h5policy/pickles/`](../h5policy/pickles/) definitions, mapped to the format reference by [`docs/spec/`](spec/) | Which bytes and relationships the independent GNU poke parser reads. Generated-document checks catch structural drift between definitions and prose; they do not prove the HDF5 specification itself complete or defect-free. |
| Security invariant model | [`registry/validation-coverage.yml`](../registry/validation-coverage.yml) and the [CVE strategy](A%20CVE%20strategy%20for%20the%20HDF5%20library.md) | The named invariant, its scope and semantic boundary, the coordinating validator, expected finding, fixtures, mutation targets, and known migration backlog. |
| Finding classification | The sharded [finding catalog and message routes](../registry/findings/README.md) | For every catalogued code: its record family, invariant, scope, severity/classification, format versions, implementation emit sites, and stable message. Reviewed routes disambiguate shared codes from the emitted message rather than guessing a family. |
| Curated regression evidence | [`h5policy/tests/expected/`](../h5policy/tests/expected/) and the [corpus contract](../h5policy/tests/README.md) | Valid and malformed fixtures pin decisions, exit codes, required findings, evidence locations where declared, geometry, metrics, and forbidden outcomes. Typed mutation recipes self-check that they reach their intended invariant. |
| Independent differential evidence | [`h5policy-diff`](../h5policy/tools/h5policy-diff) | An independent comparison with `libhdf5` through h5py and optional HDF5 tools. It detects unsafe acceptances, unsupported corruption accusations, and selected structural disagreements; agreement is corroboration, not a proof that both implementations are correct. |
| Exact-build behavioral evidence | The [probe](../h5policy/tools/probe/README.md), canary matrix, and generated [`registry/libhdf5-evidence.yml`](../registry/libhdf5-evidence.yml) | What one identified `libhdf5` build actually opened, rejected, activated, or crashed on. This evidence is version-specific and supplements the oracle; it never determines the oracle's finding class. |
| Assurance measurements | [`registry/verification-coverage.yml`](../registry/verification-coverage.yml), [`registry/truncation-sweep.json`](../registry/truncation-sweep.json), and [`registry/lazy-validation.json`](../registry/lazy-validation.json) | How much boundary, truncation, progress, activation, differential, fuzzing, and lazy-validation evidence exists for each family. A `partial`, `absent`, or `not_assessed` status remains visible. |

### From bytes to a classified finding

The classification chain is:

```text
file bytes
  -> bounded decoder and semantic check
  -> named invariant
  -> finding code, class, location, and optional typed evidence
  -> catalog record (or reviewed message route for a shared code)
  -> class-precedence decision
```

The report carries the finding code and runtime class. The registry supplies
the stable semantic attribution. For a code emitted by several walkers, the
message route is part of the evidence: an unmatched ambiguous message names no
family and is a registry failure, not permission to use a convenient fallback.

Invariant rationale can come from a normative format constraint, checked
arithmetic or graph-safety reasoning, a source-level audit of a consumer
precondition, or a reproduced vulnerability or differential result. The
manifest's strategy, tests, fuzz targets, and backlog fields—and the tracked
[`registry/cases/`](../registry/cases/) records—retain those distinctions. A
native-library observation may motivate or corroborate an invariant, but the
oracle still needs an independent semantic rule.

### How the class is justified

The finding class identifies which assessment boundary failed. It is not
inferred from whether the selected `libhdf5` happens to accept or reject the
specimen.

| Report class | Required basis |
| --- | --- |
| `corrupt` | The encoded metadata violates a checked structural, arithmetic, aggregate, or reference-graph invariant required for the representation to be internally consistent and safely consumable. |
| `policy` | The metadata is structurally recognized, but the selected profile denies the feature or activation boundary. |
| `resource` | The declared shape or reachable graph exceeds a selected data/resource envelope or matches a defined denial-of-service condition. |
| `unsupported` | The analyzer cannot establish the required validation claim because decoding coverage, compatibility, or bounded analysis ended. This is a refusal, not corruption and not acceptance. |
| `warning` | The profile accepts the metadata, but the report identifies an activation or advisory condition the next consumer must review. |
| `internal` | The profile or validator failed. This class describes the tool, not evidence that the file is corrupt. |

For example, `H5_CORRUPT_DATASPACE_NELEM_OVERFLOW` traces through
[`registry/findings/catalog/dataspace_dimension.yml`](../registry/findings/catalog/dataspace_dimension.yml)
to the local-decode `dataspace.nelem_product` invariant and its emit site in
`h5_dataspace.pk`. The validation manifest names the malformed product fixture
and the family canary. The tracked exact-build evidence separately records that
`libhdf5` 2.3.0 rejected that fixture. The arithmetic invariant is
source-derived, its classification mapping is curated, and the corpus and
exact-build outcomes are measured corroboration.

Registry checks currently account for **320 finding codes** and **0 semantic-
backlog entries**. Static enumeration resolves **980 in-pickle message
variants**, with **0 unrouted** and **0 unanalyzable** variants. That is complete
classification coverage for the current emission surface, not complete
invariant coverage for the HDF5 format.

## How complete is invariant coverage?

It is broad and explicitly measured, but it is not complete.

The current invariant manifest contains **392 named invariants across 16
selected record families**. Those families are security-oriented groupings,
not a claim that every legal HDF5 representation, payload behavior, or
application activation has been modeled.

**12 families are marked `covered`, 4 `partial`, and 0 `coverage_gap`.** A
covered vertical slice requires the validator, fixtures, entry-point driver,
and CI gate together. The family-level `validators.h5policy` claim is `enforced`
for 15 families and `partial` for 1, the cache-image dependency-graph family.
The difference is intentional: a check can exist in the oracle while its
complete evidence and migration slice remains partial.

The covered set is `object_header_continuation`, `external_file_list`,
`external_link`, `virtual_dataset`, `datatypes`, `btree_heap_index`,
`dataset_layout_filter_fill`, `dataspace_dimension`, `address_space_bounds`,
`chunk_index`, `message_envelope`, and `validation_controls`.

The stronger §12 verification score is lower. Of **176 assurance slots**, **57
are `met`, 67 `partial`, 26 `not_assessed`, and 26 `absent`**. These are eleven
requirements applied to each of the 16 families; they are not a percentage of
the HDF5 specification. Major visible gaps include:

- dedicated typed fuzz targets for only 2 of 16 families and no repository
  OSS-Fuzz integration. The mutation engine is per-family by construction -- a
  locator plus a recipe table -- so a family gains targets only when someone
  writes its locator, and a recipe earns its place only by holding on seeds
  other than the one it was developed against;
- family-by-family boundary, overflow/allocation, nesting, and progress cases
  that are still partial or not assessed. Reviewed fixture annotations now
  classify most of these: `count_and_extent_boundaries` is `not_assessed` for
  only 2 families of 16, but `met` for 1, so what the sweep mostly established
  is which boundary values the corpus genuinely lacks -- `n` and `n_minus_1` are
  thin almost everywhere, and `allocation_budget` exists for one family;
- truncation coverage that is met for 12 families, sampled/partial for 4, and
  absent for 0;
- lazy-validation behavior measured for the oracle as a whole, but not yet
  discharged independently for every family;
- no-activation-on-failure evidence met for 10 families and partial for 6 where
  the selected native build still activates an external resource, crashes, or
  fails to terminate.

Every registered family has an exact-build canary contract. In the tracked
measurement for `libhdf5` 2.3.0, **7 families are measured `enforced`, 9
`partial`, 0 `diverges`, and 0 `unmeasured`**. This describes that native build,
not `h5policy` coverage, and must not be generalized to another build without
remeasurement.

Finally, inventory coverage and input coverage are different. The oracle walks
only metadata reachable under the selected mode, plus the forensic profile's
defined sweep. Dataset payloads, decompressed heap bodies, external targets,
and application-level decoding remain outside the boundary. Recognized but
unimplemented representations produce `unsupported_coverage_gap`; malformed
content reachable only through an out-of-scope payload can coexist with an
`accept`. Use the report's completion and boundary fields together with the
registry status when stating what an assessment established.

## Acting on the decision

| Result | Normal action |
| --- | --- |
| Complete `accept` | Permit only the next step allowed by the selected profile and the documented boundary. Keep payload and external-resource controls in place. |
| Complete `accept_with_warnings` | Review each warning and its activation boundary before allowing the consumer operation. |
| `reject_corrupt` | Do not pass the file to the normal consumer path. Preserve it for investigation or use the separate evidence-gated repair workflow. |
| `reject_policy` | Keep the file out of this trust path. Change the profile only after an explicit trust and feature-policy decision. |
| `reject_resource` | Treat the shape as unsafe for the selected resource envelope. Do not blindly raise limits on attacker-controlled input. |
| `unsupported_coverage_gap` | Treat the file as not approved. Use containment or an independent bounded analysis for the uncovered representation. |
| `internal_error`, missing JSON, or incomplete acceptance | Treat the assessment as failed, preserve diagnostics, and investigate the validator before allowing the file onward. |

## Deeper investigation

For a broader diagnostic report, rerun the original input without modifying it:

```sh
./tools/h5policy --profile forensic --continue-after-rejection suspect.h5 \
    > h5policy-forensic.json
```

This run answers a different, investigation-oriented question. It does not
replace the original profile result. Use [`h5explain`](../h5explain/README.md)
to navigate to reported objects and offsets without duplicating policy logic.

If the question is what a particular `libhdf5` build actually opens or
activates, collect supplementary evidence with the
[exact-build probe](../h5policy/tools/probe/README.md). Probe outcomes are not
`h5policy` decisions. Payload decoding, plugin execution, external targets, and
application deserialization likewise require controls and measurements outside
this metadata-only workflow.

For the complete report contract, validation inventory, and current coverage
boundaries, see the [main `h5policy` guide](../h5policy/README.md).
