# H5Lens HDF5 File Format Reference

This reference describes the HDF5 on-disk structures implemented by the
H5Lens GNU poke pickles. It follows the organization of the upstream
[HDF5 File Format Specification](https://support.hdfgroup.org/documentation/hdf5/latest/_f_m_t4.html),
moving from file-level metadata through shared infrastructure to data-object
metadata and specialized encodings.

The pages are generated from executable definitions in [`pickles/`](../../pickles/)
and prose sidecars in [`docs/spec/`](../spec/). They document H5Lens's current
coverage rather than reproducing the complete upstream specification.

## Contents

1. **II. Disk Format: Level 0 — File Metadata**
   1. [II.A. Format Signature and Superblock](superblock.md)
   2. [II.B. File Driver Information](drv_info.md)
2. **III. Disk Format: Level 1 — File Infrastructure**
   1. **III.A. B-trees and B-tree Nodes**
      1. [III.A.1. Version 1 B-trees](v1_btree.md)
      2. [III.A.2. Version 2 B-trees](v2_btree.md)
   2. [III.B–C. Group Symbol Table Nodes and Entries](stab.md)
   3. [III.D. Local Heaps](lheap.md)
   4. [III.E. Global Heaps](gheap.md)
   5. [III.F. Virtual Dataset Global Heap Blocks](vds.md)
   6. [III.G. Fractal Heaps](fheap.md)
   7. [III.H. Free-space Manager](fsm.md)
   8. [III.I. Shared Object Header Message Tables](sohm.md)
3. **IV. Disk Format: Level 2 — Data Objects**
   1. **IV.A. Data Object Headers**
      1. [IV.A.1–2. Object Header Prefixes and Messages](ohdr_msgs.md)
4. **VII. Appendix C — Dataset Chunk Indexes**
   1. [VII.C. Fixed Array Index](farray.md)
   2. [VII.D. Extensible Array Index](earray.md)
5. **VIII. Appendix D — Standalone Encodings**
   1. [VIII.A. Dataspace Encoding](dspace_enc.md)
   2. [VIII.B. Datatype Encoding](dtype_enc.md)
   3. [VIII.C–D. Reference Encoding](ref_enc.md)

## Reading the reference

Each page begins with the role of the structure and then presents the decoded
types as field tables. Names shown in code style are the identifiers used by
the corresponding poke definition, so a reader can move directly from the
reference to the executable implementation.

To regenerate these pages or validate the prose sidecars against the pickle
definitions, see the [documentation workflow](../README.md).
