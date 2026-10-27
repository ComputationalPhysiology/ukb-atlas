from __future__ import annotations
from pathlib import Path
import os
import json
from argparse import ArgumentParser

import numpy as np
import logging
from typing import Literal, NamedTuple

from . import atlas, smooth, template

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
            "Use the PCA atlas derived from all 4,329 subjects from the UK "
            "Biobank Study. Currently NOT supported (raises an error). By default we "
            "use the PCA atlas derived from 630 healthy reference subjects from the "
            "UK Biobank Study"
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
        "-g",
        "--geometry",
        choices=list(RECIPES),
        default="biv",
        help=(
            "Geometry to generate surfaces for: biventricular (biv) or LV only (lv), with "
            "open valves, or with the valves closed by caps so that the cavities are "
            "closed surfaces (biv-closed, lv-closed)."
        ),
    )
    parser.add_argument(
        "--refine",
        type=int,
        default=0,
        help=(
            "Number of times to refine the surfaces by splitting each triangle into four. "
            "The new nodes are placed on smooth surfaces through the nodes of the atlas, "
            "which makes the surfaces closer to the smooth shape of the atlas. This is useful "
            "for meshes of higher order. By default 0"
        ),
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
    geometry: str = "biv",
    refine: int = 0,
) -> None:
    """Main function to generate  surfas from the UK Biobank atlas.

    Parameters
    ----------
    folder : Path
        Directory to save the generated points.
    all : bool
        Use the PCA atlas derived from all 4,329 subjects from the UK Biobank
        Study. This is not supported and raises a ``NotImplementedError``. If
        false (default), use the PCA atlas derived from 630 healthy reference
        subjects from the UK Biobank Study (see [1]_)
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
    geometry : str
        Name of the geometry (see ``RECIPES``) to generate surfaces for, by
        default "biv"
    refine : int
        Number of times to refine the surfaces, placing the new nodes on smooth
        surfaces through the nodes of the atlas (see ``ukb.smooth``), by default 0

    """

    if all:
        raise NotImplementedError(atlas.ALL_NOT_SUPPORTED)

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
            "geometry": geometry,
            "refine": refine,
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

    for c in cases:
        template.check_points(getattr(points, c), name=f"{c} points")

    recipe = RECIPES[geometry]
    files: dict[str, dict[str, list[str]]] = {}
    for c in cases:
        files[c] = {}
        case_points, case_template = smooth.refine(getattr(points, c), refine)
        for name, regions in recipe.surfaces.items():
            # One file per region: gmsh fails to mesh the volume when e.g. the RV
            # septum and free wall are merged into a single surface
            files[c][name] = []
            for region in regions:
                path = folder / f"{region}_{c}.stl"
                template.extract(case_points, [region], template=case_template).write(str(path))
                logger.info(f"Saved {path}")
                files[c][name].append(path.name)

    write_manifest(folder, geometry, recipe.volumes, files)


class Recipe(NamedTuple):
    """A geometry made of template regions.

    Parameters
    ----------
    surfaces : dict[str, tuple[str, ...]]
        Physical surface name -> template regions it is made of
    volumes : dict[str, tuple[str, ...]]
        Physical volume name -> names of the surfaces enclosing it
    """

    surfaces: dict[str, tuple[str, ...]]
    volumes: dict[str, tuple[str, ...]]


VALVE_CAPS = {
    "MV_CAP": ("MV_CAP",),
    "AV_CAP": ("AV_CAP",),
    "TV_CAP": ("TV_CAP",),
    "PV_CAP": ("PV_CAP",),
}

BIV = Recipe(
    surfaces={
        "LV_ENDO": ("LV_ENDO",),
        "RV_ENDO": ("RV_SEPTUM", "RV_FREEWALL"),
        "EPI": ("LV_EPI", "RV_EPI"),
        "MV": ("MV",),
        "AV": ("AV",),
        "TV": ("TV",),
        "PV": ("PV",),
    },
    volumes={"Wall": ("LV_ENDO", "RV_ENDO", "EPI", "MV", "AV", "TV", "PV")},
)
BIV_CLOSED = Recipe(
    surfaces=BIV.surfaces | VALVE_CAPS,
    volumes=BIV.volumes
    | {
        "LV_CAVITY": ("LV_ENDO", "MV_CAP", "AV_CAP"),
        "RV_CAVITY": ("RV_ENDO", "TV_CAP", "PV_CAP"),
    },
)
# The LV wall is closed on the RV side by the RV septal surface and the septal
# bridge cutting through the wall along the RV insertion
LV = Recipe(
    surfaces={
        "LV_ENDO": ("LV_ENDO",),
        "EPI": ("LV_EPI",),
        "RV_SEPTUM": ("RV_SEPTUM",),
        "SEPTAL_BRIDGE": ("SEPTAL_BRIDGE",),
        "MV": ("MV",),
        "AV": ("AV",),
    },
    volumes={"Wall": ("LV_ENDO", "EPI", "RV_SEPTUM", "SEPTAL_BRIDGE", "MV", "AV")},
)
LV_CLOSED = Recipe(
    surfaces=LV.surfaces | {"MV_CAP": ("MV_CAP",), "AV_CAP": ("AV_CAP",)},
    volumes=LV.volumes | {"LV_CAVITY": ("LV_ENDO", "MV_CAP", "AV_CAP")},
)
RECIPES: dict[str, Recipe] = {
    "biv": BIV,
    "biv-closed": BIV_CLOSED,
    "lv": LV,
    "lv-closed": LV_CLOSED,
}

MANIFEST = "surfaces.json"


def write_manifest(
    folder: Path,
    geometry: str,
    volumes: dict[str, tuple[str, ...]],
    files: dict[str, dict[str, list[str]]],
) -> None:
    """Record the volumes of the geometry and which files make up each surface,
    for each case.

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
    manifest = {"geometry": geometry, "volumes": volumes, "cases": cases}
    path.write_text(json.dumps(manifest, indent=4))


def read_manifest(folder: Path, case: str) -> tuple[dict[str, list[Path]], dict[str, list[str]]]:
    """Return the surface files and volumes for the given case.

    Returns
    -------
    files : dict[str, list[Path]]
        Surface name -> files the surface is made of
    volumes : dict[str, list[str]]
        Volume name -> names of the surfaces enclosing it

    Raises
    ------
    FileNotFoundError
        If no surfaces were generated for this case in ``folder``
    """
    path = Path(folder) / MANIFEST
    manifest = json.loads(path.read_text()) if path.exists() else {"cases": {}}
    cases = manifest["cases"]
    if case not in cases:
        raise FileNotFoundError(
            f"No surfaces for case {case} in {folder}. Run `ukb-atlas surf` first."
        )
    files = {name: [Path(folder) / file for file in files] for name, files in cases[case].items()}
    # Manifests written by v1.5.0 do not record the volumes
    volumes = manifest.get("volumes") or RECIPES[manifest["geometry"]].volumes
    return files, {name: list(surfaces) for name, surfaces in volumes.items()}
