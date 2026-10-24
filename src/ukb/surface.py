from __future__ import annotations
from pathlib import Path
import os
import json
from argparse import ArgumentParser

import numpy as np
import logging
from typing import Literal

from . import atlas, template

logger = logging.getLogger(__name__)


def add_parser_arguments(parser: ArgumentParser) -> None:
    parser.add_argument(
        "folder",
        type=Path,
        help="Directory to save the generated surfaces.",
    )
    parser.add_argument(
        "-a",
        "--all",
        action="store_true",
        help=(
            "Use the the PCA atlas derived from all 4,329 subjects from the UK "
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
        help="Standard deviation to scale the mode by, by default 1.5",
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
        help="Case to generate surfaces for.",
    )
    parser.add_argument(
        "--burns-path",
        type=Path,
        default=None,
        help=(
            "Path to the burns atlas file. "
            "This will be a .mat file which will be loaded using scipy.io.loadmat. "
        ),
    )


def tolist(obj: np.ndarray | list) -> list:
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, list):
        return obj
    else:
        raise ValueError(f"Object of type {type(obj)} cannot be converted to list.")


def main(
    folder: Path,
    all: bool = False,
    mode: int = -1,
    std: float = 1.5,
    verbose: bool = False,
    cache_dir: Path = Path.home() / ".ukb",
    case: Literal["ED", "ES", "both"] = "ED",
    burns_path: Path | None = None,
    custom_points: atlas.Points | None = None,
    score: np.ndarray | None = None,
) -> None:
    """Main function to generate  surfas from the UK Biobank atlas.

    Parameters
    ----------
    folder : Path
        Directory to save the generated points.
    all : bool
        If true, download the PCA atlas derived from all 4,329 subjects
        from the UK Biobank Study. If false, downlaod PCA atlas derived
        from 630 healthy reference subjects from the UK Biobank Study
        (see [1]_) by default False
    mode : int
        Mode to generate points from. If -1, generate points from the mean
        shape. If between 0 and the number of modes, generate points from
        the specified mode. By default -1
    std : float
        Standard deviation to scale the mode by, by default 1.5
    verbose : bool
        If true, print verbose output.
    cache_dir : Path
        Directory to save the downloaded atlas.
    case : str
        Case to generate surfaces for.
    burns_path : Path | None
        Path to the burns atlas file. This will be a .mat file which will be loaded
        using scipy.io.loadmat.
    custom_points : atlas.Points | None
        If not None, use these points instead of generating points from the atlas.
    score : np.ndarray | None
        If not None, use these scores to generate points from the atlas instead of
        using the `mode` and `std` parameters. This will override the `mode` and
        `std` parameters if provided.

    """

    folder.mkdir(exist_ok=True, parents=True)

    args_json = json.dumps(
        {
            "folder": str(folder),
            "all": all,
            "mode": mode,
            "std": std,
            "verbose": verbose,
            "cache_dir": str(cache_dir),
            "case": case,
            "burns_path": str(burns_path) if burns_path else None,
            "custom_points": str(custom_points) if custom_points else None,
            "score": tolist(score) if score is not None else None,
        },
        indent=4,
        sort_keys=True,
        default=lambda o: str(o),
    )

    (folder / "parameters.json").write_text(args_json)

    if custom_points is not None:
        points = custom_points

    else:
        if burns_path is not None:
            if not burns_path.exists():
                raise ValueError(f"Burns path {burns_path} does not exist.")

            points = atlas.generate_points_burns(
                filename=burns_path,
                mode=mode,
                std=std,
                score=score,
            )
        else:
            cache_dir.mkdir(exist_ok=True, parents=True)
            filename = atlas.download_atlas(cache_dir, all=all)

            points = atlas.generate_points(
                filename=filename,
                mode=mode,
                std=std,
            )

    if case == "both":
        cases = ["ED", "ES"]
    else:
        cases = [case]

    num_nodes = template.load_template().num_nodes
    for c in cases:
        if getattr(points, c).shape != (num_nodes, 3):
            raise ValueError(
                f"Expected {c} points of shape ({num_nodes}, 3), got {getattr(points, c).shape}. "
                "Points with the valve centres removed (5806 nodes) from older versions are "
                "not supported."
            )

    geometry = "biv"
    recipe = RECIPES[geometry]
    files: dict[str, dict[str, list[str]]] = {}
    for c in cases:
        files[c] = {}
        for name, regions in recipe.items():
            # One file per region: gmsh fails to mesh the volume when e.g. the RV
            # septum and free wall are merged into a single surface
            files[c][name] = []
            for region in regions:
                path = folder / f"{region}_{c}.stl"
                template.extract(getattr(points, c), [region]).write(str(path))
                logger.info(f"Saved {path}")
                files[c][name].append(path.name)

    write_manifest(folder, geometry, files)


# Output surface name -> template regions it is made of
Recipe = dict[str, tuple[str, ...]]

BIV: Recipe = {
    "LV_ENDO": ("LV_ENDO",),
    "RV_ENDO": ("RV_SEPTUM", "RV_FREEWALL"),
    "EPI": ("LV_EPI", "RV_EPI"),
    "MV": ("MV",),
    "AV": ("AV",),
    "TV": ("TV",),
    "PV": ("PV",),
}
RECIPES: dict[str, Recipe] = {"biv": BIV}

MANIFEST = "surfaces.json"


def write_manifest(folder: Path, geometry: str, files: dict[str, dict[str, list[str]]]) -> None:
    """Record which surface files make up each surface, for each case.

    Cases from an earlier run with the same geometry are kept, so that ED and ES
    can be generated by separate calls.
    """
    path = folder / MANIFEST
    cases: dict[str, dict[str, list[str]]] = {}
    if path.exists():
        old = json.loads(path.read_text())
        if old.get("geometry") == geometry:
            cases = old["cases"]
    cases.update(files)
    path.write_text(json.dumps({"geometry": geometry, "cases": cases}, indent=4))


def read_manifest(folder: Path, case: str) -> dict[str, list[Path]]:
    """Return surface name -> surface files for the given case.

    Raises
    ------
    FileNotFoundError
        If no surfaces were generated for this case in ``folder``
    """
    path = Path(folder) / MANIFEST
    cases = json.loads(path.read_text())["cases"] if path.exists() else {}
    if case not in cases:
        raise FileNotFoundError(
            f"No surfaces for case {case} in {folder}. Run `ukb-atlas surf` first."
        )
    return {name: [Path(folder) / file for file in files] for name, files in cases[case].items()}
