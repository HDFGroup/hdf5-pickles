# II.B. Disk Format: Level 0B - File Driver Info

<a id="subsec_fmt4_boot_driver"></a>

Upstream: [HDF5 File Format Specification 4.0, section II.B](https://support.hdfgroup.org/documentation/hdf5/latest/_f_m_t4.html#subsec_fmt4_boot_driver) · Coverage: **Partial**

The driver information block stores optional virtual file driver
metadata for legacy superblock versions 0 and 1. It is present only
when the superblock's `drv_info_addr_raw` field is not HADDR_UNDEF.

The block begins with a small fixed header followed by an 8-byte
driver identifier and a driver-specific payload. This pickle decodes
the multi-file driver (`NCSAmult`) and family driver (`NCSAfami`)
payloads explicitly. Other driver identifiers are preserved as raw
bytes so callers can still inspect or skip the block safely.

## Driver Information Block

Pickle type: `file_drv_info`.

Driver Information Block referenced by version 0 and 1 superblocks when driver-specific file-access metadata is stored in the file.

**Layout: Driver Information Block**

<table class="format-layout">
  <thead><tr><th>byte</th><th>byte</th><th>byte</th><th>byte</th></tr></thead>
  <tbody>
    <tr><td>Version</td><td colspan="3">Reserved</td></tr>
    <tr><td colspan="4">Driver Information Size</td></tr>
    <tr><td colspan="4">Driver Identification</td></tr>
    <tr><td colspan="4">Driver Identification (continued)</td></tr>
    <tr><td colspan="4">Driver Information (variable size)</td></tr>
  </tbody>
</table>

**Fields: Driver Information Block**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Version | `version` | Driver information block format version. Must be 0. |
| Reserved | `reserved` | Reserved three-byte field. Must be zero. |
| Driver Info Size | `drv_info_size` | Size in bytes of the driver-specific payload. This count does not include the 8-byte driver identifier. |
| Driver ID | `drv_id` | 8-byte ASCII driver identifier. Known values handled here are `NCSAmult` for the multi-file driver and `NCSAfami` for the family driver. |
| Datatype | `dtype` | Derived driver type used for dispatch: 1 = `NCSAmult`, 2 = `NCSAfami`, 0 = unknown. |
| Driver Info | `drv_info` | Driver-specific payload selected from the `drv_id` value. |

### Multi

Pickle union arm: `multi`.

Payload for the multi-file driver (`NCSAmult`). The mapping assigns HDF5 metadata and raw-data usage classes to member files, followed by address ranges and padded member file names.

**Fields: Multi**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Member Mapping | `member_mapping` | Six-byte mapping from usage class to member file index: superblock, B-tree, raw data, global heap, local heap, and object header. Values 1 through 6 select member files. |
| Reserved | `reserved` | Reserved two-byte field. Must be zero. |
| N Members | `n_members` | Derived count of distinct non-zero member file indices in `member_mapping`. |
| Member Addrs | `member_addrs` | Array of `multi_drv_member_addr` records, one for each distinct mapped member file. |
| Member Names Raw | `member_names_raw` | Raw member file name bytes. Names are NUL-terminated and each encoded name is padded to an 8-byte boundary. |

### Fami

Pickle union arm: `fami`.

Payload for the family driver (`NCSAfami`).

**Fields: Fami**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Member Size | `member_size` | Size in bytes of each family member file. |

### Raw

Pickle union arm: `raw`.

Fallback payload for unrecognized driver identifiers. The bytes are retained without interpretation.

**Fields: Raw**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Data | `data` | Raw driver-specific payload bytes. |


## Multi Driver Member Address

Pickle type: `multi_drv_member_addr`.

Address range descriptor for one member file in the multi-file virtual file driver.

**Fields: Multi Driver Member Address**

| Field | Pickle identifier | Description |
|-------|-------------------|-------------|
| Start Address | `start_addr` | Virtual start address covered by this member file. |
| Eoa Address | `eoa_addr` | End-of-allocation address for this member file. |
