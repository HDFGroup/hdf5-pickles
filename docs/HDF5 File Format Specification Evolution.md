# HDF5 File Format Specification: Feature/Provenance Matrix

**Scope.** Cross-reference of on-disk structures across the five published format specification
versions (1.0, 1.1, 2.0, 3.0, 4.0), with the library release that motivated each structure and,
where one exists, the public RFC or design document. Intended as a provenance/audit aid: given a
structure signature or message type found in a file, the matrix identifies the spec version that
introduced it and the minimum library generation that can have written it.

**Spec ↔ library mapping.**

| Spec version | Primary library releases | Era | Superblock versions defined |
|---|---|---|---|
| 1.0 | HDF5 1.0 – 1.2 | 1998–2001 | 0 |
| 1.1 | HDF5 1.4 – 1.6 | 2001–2007 | 0, 1 |
| 2.0 | HDF5 1.8 | 2008 | 0, 1, 2 |
| 3.0 | HDF5 1.10, 1.12 | 2016 / 2020 | 0, 1, 2, 3 |
| 4.0 | HDF5 2.0 | 2025 | 0, 1, 2, 3 |

Legend: **●** introduced · **◐** revised/extended (new version of the structure) · **○** unchanged
carry-forward · **✝** retained for compatibility but superseded · — not present.

---

## 1. Core infrastructure

| Structure | 1.0 | 1.1 | 2.0 | 3.0 | 4.0 | Introduced by / for | RFC / design doc |
|---|---|---|---|---|---|---|---|
| Superblock v0 (signature, offsets/lengths params) | ● | ○ | ✝ | ✝ | ✝ | HDF5 1.0 | Original format spec |
| Superblock v1 (adds Indexed Storage Internal Node K) | — | ● | ✝ | ✝ | ✝ | HDF5 1.4/1.6 (non-default btree K) | Spec 1.1 erratum-level change |
| Superblock v2 (compact; checksum; superblock extension) | — | — | ● | ○ | ○ | HDF5 1.8 | 1.8 file-format revision docs ⚠ |
| Superblock v3 (SWMR flag in consistency bits) | — | — | — | ● | ○ | HDF5 1.10 (SWMR) | SWMR design docs (Koziol et al.) ⚠ |
| Driver Information Block (Multi/Family VFD data) | ◐* | ● | ◐ | ○ | ○ | HDF5 1.4/1.6 | — (*mentioned in 1.0, fully specified in 1.1) |
| Superblock Extension (object header holding SB messages) | — | — | ● | ◐ | ○ | HDF5 1.8; extended in 1.10 (File Space Info) | — |
| Jenkins lookup3 checksums on metadata blocks | — | — | ● | ○ | ○ | HDF5 1.8 (metadata integrity) | — |

## 2. Group storage / link infrastructure

| Structure | 1.0 | 1.1 | 2.0 | 3.0 | 4.0 | Introduced by / for | RFC / design doc |
|---|---|---|---|---|---|---|---|
| Symbol Table Node (`SNOD`) + Local Heap (`HEAP`) groups | ● | ○ | ✝ | ✝ | ✝ | HDF5 1.0 ("old-style" groups) | Original format spec |
| Symbol Table Entry (w/ scratch-pad cache) | ● | ◐ | ✝ | ✝ | ✝ | HDF5 1.0 | Original format spec |
| Link message (soft/hard/external, per-link encoding) | — | — | ● | ○ | ○ | HDF5 1.8 (new group format; external links) | 1.8 "group revisions" design docs ⚠ |
| Link Info / Group Info messages | — | — | ● | ○ | ○ | HDF5 1.8 (compact vs. dense groups) | 1.8 "group revisions" design docs ⚠ |
| Fractal heap (`FRHP`/`FHDB`/`FHIB`) for dense links | — | — | ● | ○ | ○ | HDF5 1.8 (scalable groups, creation order) | Fractal heap design doc (Koziol) ⚠ |
| Creation-order link indexing (v2 B-tree types 5–6) | — | — | ● | ○ | ○ | HDF5 1.8 | — |

## 3. B-trees and indexing

| Structure | 1.0 | 1.1 | 2.0 | 3.0 | 4.0 | Introduced by / for | RFC / design doc |
|---|---|---|---|---|---|---|---|
| v1 B-link tree (`TREE`; group + chunk index) | ● | ◐ | ✝ | ✝ | ✝ | HDF5 1.0 (Lehman/Yao B-link trees) | Original format spec |
| Chunk B-tree key extra dimension (offset-in-type, always 0) | — | ● | ○ | ○ | ○ | HDF5 1.4/1.6 (reserved, never used) | — (vestigial) |
| v2 B-tree (`BTHD`/`BTIN`/`BTLF`; record counts, checksums) | — | — | ● | ◐ | ○ | HDF5 1.8; new record types in 1.10 | — (spec notes v1 deletion bugs as motive) |
| v2 B-tree record types 10–11 (non-/filtered dataset chunks) | — | — | — | ● | ○ | HDF5 1.10 (chunk indexing under SWMR) | — |
| Fixed Array chunk index (`FAHD`/`FADB`) | — | — | — | ● | ○ | HDF5 1.10 | — |
| Extensible Array chunk index (`EAHD`/`EAIB`/`EASB`/`EADB`) | — | — | — | ● | ○ | HDF5 1.10 (append-mostly datasets, SWMR) | Extensible array data structure paper/RFC ⚠ |
| Single Chunk / Implicit indexes (index-less layouts) | — | — | — | ● | ○ | HDF5 1.10 (space optimization) | — |

## 4. Object headers and messages

| Structure | 1.0 | 1.1 | 2.0 | 3.0 | 4.0 | Introduced by / for | RFC / design doc |
|---|---|---|---|---|---|---|---|
| Object header v1 (typed-message container) | ● | ◐ | ✝ | ✝ | ✝ | HDF5 1.0 — the central extension mechanism | Original format spec |
| Object header v2 (`OHDR`; checksums, times, attr phase-change) | — | — | ● | ○ | ○ | HDF5 1.8 | — |
| Shared message ad-hoc flag (global heap based) | ● | ◐ | ✝ | ✝ | ✝ | HDF5 1.0 | Original format spec |
| Shared Object Header Message tables (`SMTB`/`SMLI`, SOHM) | — | — | ● | ○ | ○ | HDF5 1.8 (dedup of datatypes/dataspaces) | SOHM design docs ⚠ |
| Attribute message | ● | ◐ | ◐ | ○ | ○ | HDF5 1.0; v2 in 1.6 era, v3 (charset) in 1.8 | — |
| Attribute Info message + dense attribute storage | — | — | ● | ○ | ○ | HDF5 1.8 (break 64 KB header limit) | — |
| Fill value message (old) / new versioned fill value | ● | ◐ | ◐ | ○ | ○ | Split specified in 1.1; v3 in 1.8 | — |
| Object comment / name message | ● | ○ | ○ | ○ | ○ | HDF5 1.0 | Original format spec |
| Object modification time (old datetime string → new message) | ● | ◐ | ○ | ○ | ○ | 1.0 string form; binary message 1.6 era | — |
| Bogus message (format testing) | — | — | ● | ○ | ○ | Library test infrastructure | — |

## 5. Datatypes

| Structure | 1.0 | 1.1 | 2.0 | 3.0 | 4.0 | Introduced by / for | RFC / design doc |
|---|---|---|---|---|---|---|---|
| Datatype message v1 (fixed/float/string/bitfield/opaque/compound/reference/enum/VL) | ● | ◐ | ○ | ○ | ○ | HDF5 1.0 (machine-described types) | Original format spec |
| Datatype v2 (compound member packing) | — | ● | ○ | ○ | ○ | HDF5 1.4/1.6 | — |
| Array datatype class (10) | — | ● | ○ | ○ | ○ | HDF5 1.4 | — |
| Datatype v3 (VAX float support, encoding fixes) | — | — | ● | ○ | ○ | HDF5 1.8 | — |
| Datatype v4 (revised reference types) | — | — | — | ● | ○ | HDF5 1.12 (new references) | RFC: Update to HDF5 References ⚠ |
| Datatype v5 + Complex class (11) | — | — | — | — | ● | HDF5 2.0 (`H5T_COMPLEX`) | Henderson, *RFC: Adding support for 16-bit floating point and Complex number datatypes to HDF5*, Jan 2024 (Zenodo 10.5281/zenodo.10666895); precursor: Soumagne, *RFC: New Datatypes*, THG 2015-04-29 |

## 6. Dataspace, layout, storage

| Structure | 1.0 | 1.1 | 2.0 | 3.0 | 4.0 | Introduced by / for | RFC / design doc |
|---|---|---|---|---|---|---|---|
| Dataspace message v1 (simple; permutation indices unimpl.) | ● | ○ | ◐ | ○ | ○ | HDF5 1.0 | Original format spec |
| Dataspace v2 (drops perm. indices; adds NULL space type) | — | — | ● | ○ | ○ | HDF5 1.8 | — |
| "Complex dataspace" (promised, never defined) | ● | ● | — | — | — | HDF5 1.0 aspiration; removed from later specs | — (abandoned) |
| Data layout message v1–2 (contiguous/chunked/compact) | ● | ◐ | ◐ | ○ | ○ | HDF5 1.0; v3 reorganization in 1.6/1.8 | — |
| Data layout v4 (virtual class; per-index-type encodings) | — | — | — | ● | ○ | HDF5 1.10 (VDS + chunk indexes) | Koziol, Pourmal, Fortner, *RFC: HDF5 Virtual Dataset*, 2014 |
| Global heap (`GCOL`; VL data, old references) | ● | ○ | ○ | ◐ | ○ | HDF5 1.0; extended for VDS blocks in 1.10 | Original format spec |
| Global Heap Block for Virtual Datasets (`VHDB`) | — | — | — | ● | ○ | HDF5 1.10 (VDS mapping storage) | VDS RFC (above) |
| External file list (`EFL` + local heap) | ● | ○ | ○ | ○ | ○ | HDF5 1.0 | Original format spec |
| Filter pipeline message (v1 → v2) | ● | ◐ | ◐ | ○ | ○ | HDF5 1.0 (deflate); v2 encoding in 1.8 | — |
| Free-space manager (`FSHD`/`FSSE`) + File Space Info msg | —* | —* | — | ● | ○ | HDF5 1.10 (*1.0/1.1 declared free-space format "undefined") | *RFC: HDF5 File Space Management* (THG; FileSpaceManagement.pdf) |

## 7. References

| Structure | 1.0 | 1.1 | 2.0 | 3.0 | 4.0 | Introduced by / for | RFC / design doc |
|---|---|---|---|---|---|---|---|
| Object + dataset-region references (global-heap based) | ● | ◐ | ○ | ✝ | ✝ | HDF5 1.0/1.2 | Original format spec |
| Revised reference encoding (`RV` blobs; attr/external refs) | — | — | — | ● | ○ | HDF5 1.12 | RFC: Update to HDF5 References ⚠ |

---

## Reading the matrix for audit purposes

1. **Minimum-writer inference.** Any structure marked ● in column 3.0 or later cannot appear in a
   file produced by a pre-1.10 library; e.g., presence of `FSHD`, `EAHD`, `FAHD`, `VHDB`, layout v4,
   or superblock v3 bounds the writer at ≥ 1.10. Datatype class 11 bounds it at ≥ 2.0.
2. **Compatibility fossils.** Structures marked ✝ remain fully specified and legal in 4.0-era
   files; their presence indicates either an old writer or a library-version-bounds setting
   (`H5Pset_libver_bounds`) pinned low — relevant when reasoning about reproducibility claims.
3. **Signature inventory.** Four-character signatures by introduction: 1.0 — `TREE`, `SNOD`,
   `HEAP`, `GCOL`; 2.0 — `OHDR`, `OCHK`, `FRHP`, `FHDB`, `FHIB`, `BTHD`, `BTIN`, `BTLF`, `SMTB`,
   `SMLI`; 3.0 — `FSHD`, `FSSE`, `FAHD`, `FADB`, `EAHD`, `EAIB`, `EASB`, `EADB`, `VHDB`.
   A signature scan of a file therefore yields a quick lower bound on format generation.

## Caveats

- Entries marked **⚠** are best-effort attributions to design documents whose exact titles,
  numbers, or dates should be verified against the [HDF Group RFC archive](https://support.hdfgroup.org/documentation/hdf5/latest/_r_f_c.html)
  before citation in formal audit artifacts. The VDS, File Space Management, New Datatypes, and Complex/float16 RFCs were verified
  against public sources; the 1.8-era design documents (group revisions, fractal heap, SOHM, SWMR)
  circulated in various forms and are less uniformly archived.
- Spec 3.0 and 4.0 as currently published on support.hdfgroup.org both incorporate the HDF5 2.0
  change list; the substantive 3.0→4.0 delta is datatype message v5 and the Complex class (11).
- The spec ↔ library mapping is approximate at the edges: 1.1-era structures phased in across
  1.4/1.6, and 2.0 structures are written by 1.8+ only when the "latest format" bounds are enabled.
