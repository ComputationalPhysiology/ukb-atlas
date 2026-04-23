from __future__ import annotations

import json
import logging
import os
from argparse import ArgumentParser
from pathlib import Path
from typing import Literal

from . import atlas
from .surface import surfaces

import numpy as np

logger = logging.getLogger(__name__)


def add_parser_arguments(parser: ArgumentParser) -> None:
    parser.add_argument(
        "folder",
        type=Path,
        help="Directory to save the generated point clouds.",
    )
    parser.add_argument(
        "-a",
        "--all",
        action="store_true",
        help=(
            "Use the PCA atlas derived from all 4,329 subjects from the UK "
            "Biobank Study. By default we use the PCA atlas derived from 630 healthy "
            "reference subjects from the UK Biobank Study"
        ),
    )
    parser.add_argument(
        "-m",
        "--mode",
        type=int,
        default=-1,
        help=(
            "Mode to generate points from. If -1, generate points from the mean "
            "shape. If between 0 and the number of modes, generate points from "
            "the specified mode. By default -1"
        ),
    )
    parser.add_argument(
        "-s",
        "--std",
        type=float,
        default=1.5,
        help="Standard deviation to scale the mode by. By default 1.5",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print verbose output.",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=os.environ.get("UKB_CACHE_DIR", Path.home() / ".ukb"),
        help=(
            "Directory to save the downloaded atlas. "
            "Can also be set with the UKB_CACHE_DIR environment variable. "
            "By default ~/.ukb"
        ),
    )
    parser.add_argument(
        "-c",
        "--case",
        choices=["ED", "ES", "both"],
        default="ED",
        help="Case to export point cloud for.",
    )
    parser.add_argument(
        "--suffix",
        type=str,
        default=".tsv",
        help='Suffix for the output files. By default ".tsv". Can be changed to ".csv".',
    )


def get_point_cloud(
    points: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, dict[int, str]]:
    """Return a labelled point cloud from a post-deletion points array.

    Parameters
    ----------
    points:
        Array of shape ``(N, 3)`` as returned by
        :func:`ukb.atlas.generate_points` (ED or ES field).

    Returns
    -------
    points : np.ndarray, shape (M, 3)
        Labelled points only (unlabelled nodes dropped).  ``M <= N``.
    labels : np.ndarray, shape (M,), dtype int
        Integer label for each point.  Labels start at ``1``; there is no
        ``0`` entry in the returned array.
        When a node falls in multiple surface regions the last entry in
        :data:`surfaces` (in iteration order) wins.
    label_names : dict[int, str]
        Mapping from integer label to surface name.
    """
    labels = np.zeros(len(points), dtype=int)
    label_names: dict[int, str] = {}

    for i, (name, surface) in enumerate(surfaces.items(), start=1):
        label_names[i] = name
        idx = surface.post_deletion_vertex_indices
        idx = idx[idx < len(points)]
        labels[idx] = i

    keep = labels != 0
    return points[keep], labels[keep], label_names


def main(
    folder: Path,
    all: bool = False,
    mode: int = -1,
    std: float = 1.5,
    verbose: bool = False,
    cache_dir: Path = Path.home() / ".ukb",
    case: Literal["ED", "ES", "both"] = "ED",
    suffix: str = ".tsv",
) -> None:
    """Export labelled point clouds from the UK Biobank atlas.

    For each requested case (ED, ES, or both) writes one file:
    - ``{case}_pointcloud{suffix}`` - file with columns
      ``x``, ``y``, ``z``, ``label`` (integer), ``region`` (surface name).

    Parameters
    ----------
    folder : Path
        Directory to save the generated point clouds.
    all : bool
        If true, use the PCA atlas derived from all 4,329 subjects.
    mode : int
        PCA mode to generate points from. -1 = mean shape.
    std : float
        Standard deviation to scale the mode by.
    verbose : bool
        If true, print verbose output.
    cache_dir : Path
        Directory where the atlas is cached / downloaded to.
    case : str
        Which cardiac phase(s) to export: ``"ED"``, ``"ES"``, or ``"both"``.
    suffix : str
        Suffix for the output files. By default ``".tsv"`` (tab-separated).
        Can be changed to ``".csv"`` (comma-separated).
    """
    folder = Path(folder)
    folder.mkdir(exist_ok=True, parents=True)

    params = {
        "folder": str(folder),
        "all": all,
        "mode": mode,
        "std": std,
        "verbose": verbose,
        "cache_dir": str(cache_dir),
        "case": case,
    }
    (folder / "parameters.json").write_text(json.dumps(params, indent=4, sort_keys=True))

    cache_dir = Path(cache_dir)
    cache_dir.mkdir(exist_ok=True, parents=True)
    filename = atlas.download_atlas(cache_dir, all=all)
    pts = atlas.generate_points(filename=filename, mode=mode, std=std)

    cases = ["ED", "ES"] if case == "both" else [case]

    for c in cases:
        points, labels, label_names = get_point_cloud(getattr(pts, c))

        out_path = folder / f"{c}_pointcloud{suffix}"
        delimiter = "\t" if suffix == ".tsv" else ","
        with out_path.open("w") as f:
            f.write(f"x{delimiter}y{delimiter}z{delimiter}label{delimiter}region\n")
            for (x, y, z), label in zip(points, labels):
                f.write(
                    f"{x}{delimiter}{y}{delimiter}{z}{delimiter}{label}{delimiter}{label_names[label]}\n"
                )
        logger.info(f"Saved {out_path}")
