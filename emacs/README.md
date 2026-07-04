# hdf5-poke.el

`hdf5-poke.el` is an Emacs 30+ front end for inspecting HDF5 files through the
GNU poke pickles in this repository.  It starts GNU poke directly and loads
`pickles/hdf5_poke_emacs.pk`.

## Setup

Add the module to your Emacs config:

```elisp
(add-to-list 'load-path "/path/to/hdf5-pickles/emacs")
(require 'hdf5-poke)
(setq hdf5-poke-pickles-directory "/path/to/hdf5-pickles/pickles")
```

Or with `use-package`:

```elisp
(use-package hdf5-poke
  :load-path "/path/to/hdf5-pickles/emacs"
  :custom
  (hdf5-poke-pickles-directory "/path/to/hdf5-pickles/pickles"))
```

GNU poke must be on `exec-path`, or set:

```elisp
(setq hdf5-poke-program "/path/to/poke")
```

## Use

Start with:

```elisp
M-x hdf5-poke-open-file
```

Important keys:

- `s`: refresh superblock overview.
- `b`: browse links from the root group.
- `T`: open the expandable HDF5 tree rooted at `/`.
- `P`: open object-header messages by absolute HDF5 path.
- `B`: list group links by absolute HDF5 path.
- `D`: preview a dataset by absolute HDF5 path.
- `r`: open root object-header messages.
- `L`: list links for the current or requested object header.
- `o` or `m`: open messages at an object-header offset.
- `c`: open a chunk index at an offset.
- `d`: preview the selected/current dataset when its storage is supported.
- `RET`: open the selected message detail, follow a link path, or open chunk bytes.
- `g`: jump to a raw offset view.
- `v`: pretty-print the current object header or chunk-index metadata.
- `p`: switch to the backing GNU poke process buffer.

Link and message buffers carry breadcrumb buttons for path-oriented browsing.
Path commands resolve hard links from `/`, so users can enter paths such as
`/group/dset_00` instead of object-header offsets.

The tree buffer expands group links with `TAB`, opens nodes with `RET`, and can
list links or preview datasets from the selected node.  Nodes are typed lazily as
groups, datasets, or unknown objects from object-header metadata.  Hard-link
cycles are marked and are not expanded recursively.

The object-header message table adds an `Open chunk index` action for chunked
layout messages.  Version 1 chunk B-trees and v2 chunk B-trees use the layout
`ndims` value; the action passes it automatically.  Chunk tables show both the
stored scaled coordinates and logical element coordinates when layout chunk
dimensions are available.

Datatype message details include a nested datatype tree for compound, array,
enum, and variable-length datatypes.  Compound members show their byte offsets,
array nodes show dimensions, and leaf datatypes show byte order, signedness, and
precision when available.

Dataset preview is read-only.  It currently supports small fixed-point
little-endian datasets stored as compact object-header data or contiguous raw
data, up to `hdf5-poke-preview-max-bytes`.  Preview buffers show shape,
datatype signedness, decoded values, and raw bytes.

## Reliability

Protocol requests are tracked with a per-request timeout
(`hdf5-poke-request-timeout`, default 15 seconds; 0 disables it).  If GNU poke
does not answer in time, or the poke process dies with requests in flight, the
affected requests are failed with a message in the echo area and the session
command log instead of leaving a buffer hanging forever.  A late response that
arrives after a timeout is ignored safely.

## Source Layout

- `hdf5-poke.el`: public entry point; keep `(require 'hdf5-poke)` stable.
- `hdf5-poke-core.el`: foundational layer with no UI coupling -- customization,
  buffer-local state, the GNU poke process and protocol (requests, timeouts,
  parsing), and pure data/path helpers.
- `hdf5-poke-ui.el`: the inspector UI -- major modes and keymaps, the overview,
  message, link, chunk, raw, detail and dataset-preview renderers, the
  expandable path tree, and the interactive commands.  These layers are
  mutually recursive (a rendered button triggers a command; a command renders),
  so they share one file and need no forward declarations.

## Tests

Run parser and renderer tests, and process-level smoke tests against generated
HDF5 fixtures:

```sh
cmake -S . -B build
cmake --build build --target emacs-check
```

Fixture generation requires `h5py` and `numpy`; the process tests require GNU poke.

## Current Limits

Writes are currently disabled.

Dataset previews are intentionally narrow: filtered, chunked, floating-point,
compound, variable-length, and large datasets are reported as unsupported rather
than decoded.
