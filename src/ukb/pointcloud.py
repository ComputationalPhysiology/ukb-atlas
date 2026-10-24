from __future__ import annotations

import json
import logging
import os
from argparse import ArgumentParser
from pathlib import Path
from typing import Literal

from . import atlas, template

import numpy as np

logger = logging.getLogger(__name__)

# Integer label of each template region in the point cloud. Nodes shared by
# several regions get the label of the region listed first.
LABELS = {
    "MV": 1,
    "AV": 2,
    "TV": 3,
    "PV": 4,
    "LV_ENDO": 5,
    "RV_SEPTUM": 6,
    "RV_FREEWALL": 7,
    "LV_EPI": 8,
    "RV_EPI": 9,
    "MV_CAP": 10,
    "AV_CAP": 11,
    "TV_CAP": 12,
    "PV_CAP": 13,
}


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
    """Return a labelled point cloud.

    Parameters
    ----------
    points:
        Array of shape ``(5810, 3)`` as returned by
        :func:`ukb.atlas.generate_points` (ED or ES field).

    Returns
    -------
    points : np.ndarray, shape (5810, 3)
        The points, unchanged.
    labels : np.ndarray, shape (5810,), dtype int
        Integer label for each point, see :data:`LABELS`. When a node belongs
        to several regions the region listed first in :data:`LABELS` wins.
    label_names : dict[int, str]
        Mapping from integer label to region name.
    """
    t = template.load_template()
    labels = np.zeros(len(points), dtype=int)
    # Assign in reverse so that higher priority regions overwrite lower ones
    for name, label in reversed(LABELS.items()):
        labels[np.unique(t.faces[t.regions[name]])] = label

    label_names = {label: name for name, label in LABELS.items()}
    return points, labels, label_names


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
    assert suffix in {".tsv", ".csv"}, "Suffix must be either .tsv or .csv"
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
