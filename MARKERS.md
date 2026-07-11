# Marker List

The `h5markers` tool scans the concrete on-disk identifiers defined in the
[HDF5 file format specification](https://support.hdfgroup.org/documentation/hdf5/latest/_f_m_t4.html),
the implementation-defined metadata cache image signature in
[HDF5](https://github.com/HDFGroup/hdf5/blob/2.1.1/src/H5Cimage.c), and both the
[Onion revision-history RFC](https://support.hdfgroup.org/releases/hdf5/documentation/rfc/Onion_VFD_RFC_211122.pdf)
and the [current Onion implementation](https://github.com/HDFGroup/hdf5/blob/2.1.1/src/H5FDonion_history.h).

> Notice that there are multiple versions of the HDF5 file format specification, usually released in conjunction with major HDF5 library releases, and the set of markers grew over time. For example, the version 1 object header does not have marker, and chunk indexes like single chunk and implicit do not have markers. Depending on its modification history, an HDF5 file may contain a subset of the markers listed below. The `h5markers` tool will report all markers it finds, regardless of the version of the HDF5 file format specification they were introduced in.

Unless noted otherwise, each 4-character marker matches its own name spelled out as
literal ASCII bytes (e.g. `TREE` matches the four bytes `54 52 45 45`).

## HDF5 file format markers

- `HDF5_SIGNATURE` = `89 48 44 46 0D 0A 1A 0A` - HDF5 file signature
- `NCSAmult` - Multi VFD driver identifier (8 bytes)
- `NCSAfami` - Family VFD driver identifier (8 bytes)
- `TREE` - Version 1 B-tree node
- `BTHD` - Version 2 B-tree header
- `BTIN` - Version 2 B-tree internal node
- `BTLF` - Version 2 B-tree leaf node
- `SNOD` - Symbol table node
- `HEAP` - Local heap
- `GCOL` - Global heap collection
- `FRHP` - Fractal heap header
- `FHDB` - Fractal heap direct block
- `FHIB` - Fractal heap indirect block
- `FSHD` - Free-space manager header
- `FSSE` - Free-space section information
- `SMTB` - Shared Object Header Message table
- `SMLI` - Shared message record list
- `OHDR` - Version 2 object header
- `OCHK` - Version 2 object header continuation block
- `MDCI` - Metadata cache image block
- `FAHD` - Fixed Array header
- `FADB` - Fixed Array data block
- `EAHD` - Extensible Array header
- `EAIB` - Extensible Array index block
- `EASB` - Extensible Array secondary block
- `EADB` - Extensible Array data block

## Onion revision-history markers

- `OHDH` - Onion History Data Header
- `OWHR` - Onion Whole-History Record (RFC spelling)
- `OWHS` - Onion Whole-History Summary (current HDF5 implementation)
- `ORRS` - Onion Revision Record Signature
