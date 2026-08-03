# H5Lens HDF5 File Format Reference

This reference describes the HDF5 on-disk structures implemented by the
H5Lens GNU poke pickles. Its hierarchy and terminology follow the upstream
HDF5 File Format Specification Version 4.0, while its coverage statements
describe the executable definitions that are actually present in H5Lens.

Canonical organization: [HDF5 File Format Specification Version 4.0](https://support.hdfgroup.org/documentation/hdf5/latest/_f_m_t4.html) (reviewed 2026-08-01).

Coverage labels describe H5Lens, not the upstream specification:

- **Covered** — an executable pickle definition and field documentation exist.
- **Partial** — only part of the upstream section or its variants is documented.
- **Not covered** — there is no first-class H5Lens format page yet.

## Contents

- I. Introduction — Not Covered
  - I.A. This Document — Not Covered
  - I.B. Changes for HDF5 2.0 — Not Covered
  - I.C. Changes for HDF5 1.12 — Not Covered
  - I.D. Changes for HDF5 1.10 — Not Covered
- II. Disk Format: Level 0 - File Metadata — Partial
  - [II.A. Disk Format: Level 0A - Format Signature and Superblock](superblock.md#subsec_fmt4_boot_super) — Covered
  - [II.B. Disk Format: Level 0B - File Driver Info](drv_info.md#subsec_fmt4_boot_driver) — Partial
  - II.C. Disk Format: Level 0C - Superblock Extension — Not Covered
- III. Disk Format: Level 1 - File Infrastructure — Partial
  - III.A. Disk Format: Level 1A - B-trees and B-tree Nodes — Covered
    - [III.A.1. Disk Format: Level 1A1 - Version 1 B-trees](v1_btree.md#subsubsec_fmt4_infra_btrees_v1) — Covered
    - [III.A.2. Disk Format: Level 1A2 - Version 2 B-trees](v2_btree.md#subsubsec_fmt4_infra_btrees_v2) — Covered
  - [III.B. Disk Format: Level 1B - Group Symbol Table Nodes](stab.md#subsec_fmt4_infra_symboltable) — Covered
  - [III.C. Disk Format: Level 1C - Symbol Table Entry](stab.md#subsec_fmt4_infra_symboltableentry) — Covered
  - [III.D. Disk Format: Level 1D - Local Heaps](lheap.md#subsec_fmt4_infra_localheap) — Covered
  - [III.E. Disk Format: Level 1E - Global Heap](gheap.md#subsec_fmt4_infra_globalheap) — Covered
  - [III.F. Disk Format: Level 1F - Global Heap Block for Virtual Datasets](vds.md#subsec_fmt4_infra_globalheapvds) — Covered
  - [III.G. Disk Format: Level 1G - Fractal Heap](fheap.md#subsec_fmt4_infra_fractalheap) — Covered
  - [III.H. Disk Format: Level 1H - Free-space Index](fsm.md#subsec_fmt4_infra_freespaceindex) — Partial
  - [III.I. Disk Format: Level 1I - Shared Object Header Message (SOHM) Master Table](sohm.md#subsec_fmt4_infra_sohm) — Covered
- IV. Disk Format: Level 2 - Data Objects — Partial
  - IV.A. Disk Format: Level 2A - Data Object Headers — Partial
    - [IV.A.1. Disk Format: Level 2A1 - Data Object Header Prefix](ohdr_msgs.md#subsec_fmt4_dataobject_hdr_prefix) — Covered
    - [IV.A.2. Disk Format: Level 2A2 - Data Object Header Shared Message Encoding](ohdr_msgs.md) — Partial
    - [IV.A.3. Disk Format: Level 2A3 - Data Object Header Messages](ohdr_msgs.md) — Partial
      - [IV.A.3.a. The NIL Message](ohdr_msgs.md#subsubsec_fmt4_dataobject_hdr_msg_nil) — Covered
      - [IV.A.3.b. The Dataspace Message](ohdr_msgs.md#subsubsec_fmt4_dataobject_hdr_msg_simple) — Covered
      - [IV.A.3.c. The Link Info Message](ohdr_msgs.md#subsubsec_fmt4_dataobject_hdr_msg_linkinfo) — Covered
      - [IV.A.3.d. The Datatype Message](ohdr_msgs.md#subsubsec_fmt4_dataobject_hdr_msg_dtmessage) — Covered
      - [IV.A.3.e. Data Storage - Fill Value (Old) Message](ohdr_msgs.md#subsubsec_fmt4_dataobject_hdr_msg_ofvmessage) — Covered
      - [IV.A.3.f. The Data Storage - Fill Value Message](ohdr_msgs.md#subsubsec_fmt4_dataobject_hdr_msg_fvmessage) — Covered
      - [IV.A.3.g. The Link Message](ohdr_msgs.md#subsubsec_fmt4_dataobject_hdr_msg_link) — Covered
      - [IV.A.3.h. The Data Storage - External Data Files Message](ohdr_msgs.md#subsubsec_fmt4_dataobject_hdr_msg_external) — Covered
      - [IV.A.3.i. The Data Layout Message](ohdr_msgs.md#subsubsec_fmt4_dataobject_hdr_msg_layout) — Covered
      - IV.A.3.j. The Bogus Message — Not Covered
      - [IV.A.3.k. The Group Info Message](ohdr_msgs.md#subsubsec_fmt4_dataobject_hdr_msg_groupinfo) — Covered
      - [IV.A.3.l. The Data Storage - Filter Pipeline Message](ohdr_msgs.md#subsubsec_fmt4_dataobject_hdr_msg_filter) — Covered
      - [IV.A.3.m. The Attribute Message](ohdr_msgs.md#subsubsec_fmt4_dataobject_hdr_msg_attribute) — Covered
      - [IV.A.3.n. The Object Comment Message](ohdr_msgs.md#subsubsec_fmt4_dataobject_hdr_msg_comment) — Covered
      - [IV.A.3.o. The Object Modification Time (Old) Message](ohdr_msgs.md#subsubsec_fmt4_dataobject_hdr_msg_omodified) — Covered
      - [IV.A.3.p. The Shared Message Table Message](ohdr_msgs.md#subsubsec_fmt4_dataobject_hdr_msg_shared) — Covered
      - [IV.A.3.q. The Object Header Continuation Message](ohdr_msgs.md#subsubsec_fmt4_dataobject_hdr_msg_continuation) — Covered
      - [IV.A.3.r. The Symbol Table Message](ohdr_msgs.md#subsubsec_fmt4_dataobject_hdr_msg_stmgroup) — Covered
      - [IV.A.3.s. The Object Modification Time Message](ohdr_msgs.md#subsubsec_fmt4_dataobject_hdr_msg_mod) — Covered
      - [IV.A.3.t. The B-tree ‘K’ Values Message](ohdr_msgs.md#subsubsec_fmt4_dataobject_hdr_msg_btreek) — Covered
      - [IV.A.3.u. The Driver Info Message](ohdr_msgs.md#subsubsec_fmt4_dataobject_hdr_msg_drvinfo) — Covered
      - [IV.A.3.v. The Attribute Info Message](ohdr_msgs.md#subsubsec_fmt4_dataobject_hdr_msg_attrinfo) — Covered
      - [IV.A.3.w. The Object Reference Count Message](ohdr_msgs.md#subsubsec_fmt4_dataobject_hdr_msg_refcount) — Covered
      - [IV.A.3.x. The File Space Info Message](ohdr_msgs.md#subsubsec_fmt4_dataobject_hdr_msg_fsinfo) — Covered
  - [IV.B. Disk Format: Level 2B - Data Object Data Storage](ohdr_msgs.md#subsubsec_fmt4_dataobject_hdr_msg_layout) — Partial
- V. Appendix A: Definitions — Not Covered
- VI. Appendix B: File Space Allocation Types — Not Covered
- VII. Appendix C: Types of Indexes for Dataset Chunks — Covered
  - [VII.A. The Single Chunk Index](ohdr_msgs.md#subsubsec_fmt4_dataobject_hdr_msg_layout) — Covered
  - [VII.B. The Implicit Index](ohdr_msgs.md#subsubsec_fmt4_dataobject_hdr_msg_layout) — Covered
  - [VII.C. The Fixed Array Index](farray.md#subsec_fmt4_appendixc_fixedarr) — Covered
  - [VII.D. The Extensible Array Index](earray.md#subsec_fmt4_appendixc_extarr) — Covered
  - [VII.E. The Version 2 B-trees Index](v2_btree.md) — Partial
- VIII. Appendix D: Encoding for Dataspace, Datatype, and Reference — Covered
  - [VIII.A. Dataspace Encoding](dspace_enc.md#subsec_fmt4_appendixd_encode) — Covered
  - [VIII.B. Datatype Encoding](dtype_enc.md#subsec_fmt4_appendixd_encodet) — Covered
  - [VIII.C. Reference Encoding (Revised)](ref_enc.md#subsec_fmt4_appendixd_encoderv) — Covered
  - [VIII.D. Reference Encoding (Backward Compatibility)](ref_enc.md#subsec_fmt4_appendixd_encodedp) — Covered

## H5Lens extensions

- [Metadata Cache Image Message](ohdr_msgs.md#h5lens_metadata_cache_image_message)

## Reading and maintaining the reference

Specification names are shown first; executable GNU poke identifiers are shown
alongside them. Pages are generated from [`pickles/`](../../pickles/) and
[`docs/spec/`](../spec/). See the [documentation workflow](../README.md) to
regenerate the pages and validate their mappings.
