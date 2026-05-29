# II.B. Disk Format: Driver Information Block

The driver information block stores optional virtual file driver
metadata for legacy superblock versions 0 and 1. It is present only
when the superblock's `drv_info_addr_raw` field is not `HADDR_UNDEF`.

The block begins with a small fixed header followed by an 8-byte
driver identifier and a driver-specific payload. This pickle decodes
the multi-file driver (`NCSAmult`) and family driver (`NCSAfami`)
payloads explicitly. Other driver identifiers are preserved as raw
bytes so callers can still inspect or skip the block safely.

## `multi_drv_member_addr`

Address range descriptor for one member file in the multi-file virtual file driver.

| Field | Description |
|-------|-------------|
| `start_addr` | Virtual start address covered by this member file. |
| `eoa_addr` | End-of-allocation address for this member file. |


## `drv_info_blk`

Driver Information Block referenced by version 0 and 1 superblocks when driver-specific file-access metadata is stored in the file.

| Field | Description |
|-------|-------------|
| `version` | Driver information block format version. Must be 0. |
| `reserved` | Reserved three-byte field. Must be zero. |
| `drv_info_size` | Size in bytes of the driver-specific payload. This count does not include the 8-byte driver identifier. |
| `drv_id` | 8-byte ASCII driver identifier. Known values handled here are `NCSAmult` for the multi-file driver and `NCSAfami` for the family driver. |
| `dtype` | Derived driver type used for dispatch: 1 = `NCSAmult`, 2 = `NCSAfami`, 0 = unknown. |
| `drv_info` | Driver-specific payload selected from the `drv_id` value. |

### `multi`

Payload for the multi-file driver (`NCSAmult`). The mapping assigns HDF5 metadata and raw-data usage classes to member files, followed by address ranges and padded member file names.

| Field | Description |
|-------|-------------|
| `member_mapping` | Six-byte mapping from usage class to member file index: superblock, B-tree, raw data, global heap, local heap, and object header. Values 1 through 6 select member files. |
| `reserved` | Reserved two-byte field. Must be zero. |
| `n_members` | Derived count of distinct non-zero member file indices in `member_mapping`. |
| `member_addrs` | Array of `multi_drv_member_addr` records, one for each distinct mapped member file. |
| `member_names_raw` | Raw member file name bytes. Names are NUL-terminated and each encoded name is padded to an 8-byte boundary. |

### `fami`

Payload for the family driver (`NCSAfami`).

| Field | Description |
|-------|-------------|
| `member_size` | Size in bytes of each family member file. |

### `raw`

Fallback payload for unrecognized driver identifiers. The bytes are retained without interpretation.

| Field | Description |
|-------|-------------|
| `data` | Raw driver-specific payload bytes. |


