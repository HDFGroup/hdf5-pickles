#!/usr/bin/env python3
"""Generate HDF5 fixtures for the Emacs GNU poke smoke tests."""

from __future__ import annotations

import argparse
from pathlib import Path

import h5py
import numpy as np


HERE = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "output_dir",
        nargs="?",
        type=Path,
        default=HERE,
        help="Directory where generated .h5 fixtures are written.",
    )
    return parser.parse_args()


def old_style_group(path: Path) -> None:
    """Create a v1-style group backed by a symbol table."""
    with h5py.File(path, "w", libver="earliest") as h5:
        group = h5.create_group("group")
        for index in range(32):
            group.create_dataset(
                f"dset_{index:02d}",
                data=np.arange(4, dtype=np.int16) + index,
            )


def dense_group(path: Path) -> None:
    """Create a v2 dense group backed by a fractal heap and v2 B-tree."""
    with h5py.File(path, "w", libver="latest") as h5:
        group = h5.create_group("group")
        for index in range(32):
            group.create_dataset(
                f"dset_{index:02d}",
                data=np.arange(4, dtype=np.int16) + index,
            )


def chunk_v1_btree(path: Path) -> None:
    """Create a chunked dataset using the classic v1 B-tree chunk index."""
    data = np.arange(64, dtype=np.int32).reshape(8, 8)
    with h5py.File(path, "w", libver="earliest") as h5:
        h5.create_dataset("data", data=data, chunks=(4, 4), compression="gzip")


def chunk_fixed_array(path: Path) -> None:
    """Create a fixed-size v2 chunked dataset using a fixed-array index."""
    data = np.arange(12, dtype=np.int16)
    with h5py.File(path, "w", libver="latest") as h5:
        h5.create_dataset("data", data=data, chunks=(3,))


def chunk_extensible_array(path: Path) -> None:
    """Create a one-dimensional unlimited dataset using an extensible array."""
    with h5py.File(path, "w", libver="latest") as h5:
        data = h5.create_dataset(
            "data",
            shape=(0,),
            maxshape=(None,),
            chunks=(3,),
            dtype=np.int16,
        )
        data.resize((9,))
        data[...] = np.arange(9, dtype=np.int16)


def chunk_v2_btree(path: Path) -> None:
    """Create a multidimensional unlimited dataset using a v2 B-tree index."""
    with h5py.File(path, "w", libver="latest") as h5:
        data = h5.create_dataset(
            "data",
            shape=(0, 0),
            maxshape=(None, None),
            chunks=(2, 2),
            dtype=np.int32,
            compression="gzip",
        )
        data.resize((4, 4))
        data[...] = np.arange(16, dtype=np.int32).reshape(4, 4)


def nested_datatypes(path: Path) -> None:
    """Create datasets with nested compound and array datatypes."""
    inner = np.dtype([("x", "<i2"), ("y", "<f4")])
    compound = np.dtype(
        [
            ("id", "<u4"),
            ("inner", inner),
            ("samples", "<i2", (3,)),
        ]
    )
    data = np.zeros(2, dtype=compound)
    data["id"] = [1, 2]
    data["inner"]["x"] = [10, 20]
    data["inner"]["y"] = [1.5, 2.5]
    data["samples"] = [[1, 2, 3], [4, 5, 6]]

    with h5py.File(path, "w", libver="latest") as h5:
        h5.create_dataset("compound", data=data)


def userblock_latest(path: Path) -> None:
    """Create a modern file whose superblock starts after a 512-byte user block."""
    with h5py.File(path, "w", libver="latest", userblock_size=512) as h5:
        group = h5.create_group("group")
        group.create_dataset("data", data=np.arange(4, dtype=np.int16))


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    fixtures = {
        "old_style_group.h5": old_style_group,
        "dense_group.h5": dense_group,
        "chunk_v1_btree.h5": chunk_v1_btree,
        "chunk_fixed_array.h5": chunk_fixed_array,
        "chunk_extensible_array.h5": chunk_extensible_array,
        "chunk_v2_btree.h5": chunk_v2_btree,
        "nested_datatypes.h5": nested_datatypes,
        "userblock_latest.h5": userblock_latest,
    }

    for name, writer in fixtures.items():
        path = output_dir / name
        writer(path)
        print(path)


if __name__ == "__main__":
    main()
