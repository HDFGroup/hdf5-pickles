# Priority list for developing pickles of file format primitives
An HDF5 file is made up of the following objects:
- A superblock
- Object headers (prefix + messages)
- Object data
- B-tree nodes
- Indexes for chunked datasets
- Heap blocks
- Free space

Development will be based on format specification version 3 
(https://support.hdfgroup.org/documentation/hdf5/latest/_f_m_t3.html) but excluding the changes for HDF5 library v2.0 as listed in section I.B.
Pickles developed for the specification will be pushed to the
repository https://github.com/HDFGroup/hdf5-pickles/.  

The following primitives are identified and will be tackled in the following order. Each pickle needs to be verified for correctness with an HDF5 file containing the respective messages.
1. Superblock: there are 4 versions of the superblock
2. Object header: it is composed of a prefix and a set of messages:
    * There are two versions of the object header prefixes—version 1 and version 2
    * There is a total of 24 object header messages:
        * The Bogus Message is excluded as it is used for testing the HDF5 Library’s response to an “unknown” message type and should never be encountered in a valid HDF5 file.
	    * There is the Metadata Cache Image Message which is implemented in the library but has not been documented.
    * I will divide the messages into two sets. The first set I will tackle is:
        1. Nil Message
        2. Dataspace Message
        3. Link Info Message
        4. Fill Value (Old) Message
        5. Fill Value Message
        6. Link Message
        7. External Data Files Message
        8. Data Layout Message
        9. Group Info Message
        10. Filter Pipeline Message
        11. Object Comment Message
        12. Object Modification Time (Old) Message
        13. Shared Message Table Message
        14. Symbol Table message
        15. Object Modification Time message
        16. B-tree ‘K’ Values message
        17. Driver Info message
        18. Attribute Info message
        19. Object Reference Count message
        20. File Space Info message
        21. Metadata Cache Image message
    * The second set consists of messages that are relatively more complex.  They will be handled a bit later or in-between development of other pickles:
        1. Object Header Continuation message
        2. Attribute message
        3. Datatype message

Then the remaining primitives will be handled as below:
1. Version 1 and 2 B-trees
2. Group symbol table nodes
3. The 5 chunk indexes
4. Local heap/global heap/fractal heap
5. Free-space manager
6. Shared object header message table

I anticipate work for the following areas:
* Refactor/comments as needed for the pickles while development is in progress
* Instruction guide for download/build/install Poke
* Instruction guide on how to load pickles/using associated methods/functions for mapping primitives to an HDF5 file via poke editor
* Resolve discrepancies between coding and the format specification that are noted during development
* Add Metadata Cache Message to the format specification
* Incorporate info for handling shared messages that are implemented in the library
~
~
~
