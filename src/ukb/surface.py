from __future__ import annotations
from pathlib import Path
import os
import json
from argparse import ArgumentParser

import meshio
import numpy as np
import logging
from typing import NamedTuple, Literal

logger = logging.getLogger(__name__)
here = Path(__file__).parent.absolute()

connectivity_file = here / "connectivity.txt"
connectivity = np.loadtxt(connectivity_file, dtype=int)


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


def main(
    folder: Path,
    all: bool = False,
    mode: int = -1,
    std: float = 1.5,
    verbose: bool = False,
    cache_dir: Path = Path.home() / ".ukb",
    case: Literal["ED", "ES", "both"] = "ED",
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
        },
        indent=4,
        sort_keys=True,
        default=lambda o: str(o),
    )

    cache_dir.mkdir(exist_ok=True, parents=True)
    (folder / "parameters.json").write_text(args_json)

    from . import atlas

    filename = atlas.download_atlas(cache_dir, all=all)

    points = atlas.generate_points(filename=filename, mode=mode, std=std)

    if case == "both":
        cases = ["ED", "ES"]
    else:
        cases = [case]

    for c in cases:
        epi = get_epi_mesh(
            points=getattr(points, c),
        )
        epi.write(str(folder / f"EPI_{c}.stl"))
        logger.info(f"Saved {folder / f'EPI_{c}.stl'}")

        for valve in ["MV", "AV", "TV", "PV"]:
            valve_mesh = get_valve_mesh(surface_name=valve, points=getattr(points, c))
            valve_mesh.write(str(folder / f"{valve}_{c}.stl"))
            logger.info(f"Saved {folder / f'{valve}_{c}.stl'}")

        for chamber in ["LV", "RV", "RVFW"]:
            chamber_mesh = get_chamber_mesh(
                surface_name=chamber,
                points=getattr(points, c),
            )
            chamber_mesh.write(str(folder / f"{chamber}_{c}.stl"))
            logger.info(f"Saved {folder / f'{chamber}_{c}.stl'}")


class Surface(NamedTuple):
    name: str
    vertex_range: list[tuple[int, int]]
    face_range: list[tuple[int, int]]

    @property
    def vertex_indices(self):
        return np.concatenate([np.arange(start, end) for start, end in self.vertex_range])

    @property
    def face_indices(self):
        return np.concatenate([np.arange(start, end) for start, end in self.face_range])


# surfaces = {
#     "LV": Surface("LV", [(0, 1500)], [(0, 3072)]),
#     "RV": Surface(
#         "RV",
#         [(1500, 2165), (2165, 3224), (5729, 5806)],
#         [(3072, 4480), (4480, 6752)],
#     ),
#     "EPI": Surface("Epi", [(3224, 5582)], [(6752, 11616)]),
#     "MV": Surface("MV", [(5582, 5630)], [(6752, 11616)]),
#     "AV": Surface("AV", [(5630, 5653)], [(6752, 11616)]),
#     "TV": Surface("TV", [(5654, 5694)], [(6752, 11616)]),
#     "PV": Surface("PV", [(5694, 5729)], [(6752, 11616)]),
# }
surfaces = {
    "LV": Surface("LV", [(0, 1500)], [(0, 3072)]),
    "RV": Surface(
        "RV",
        [(1500, 2165), (2165, 3224)],
        [(3072, 4480)],
    ),
    "RVFW": Surface(
        "RVFW",
        [(5729, 5808)],
        [(4480, 6752)],
    ),
    "EPI": Surface("Epi", [(3224, 5582)], [(6752, 11616)]),
    "MV": Surface("MV", [(5582, 5629)], [(6752, 11616)]),
    "AV": Surface("AV", [(5630, 5653)], [(6752, 11616)]),
    "TV": Surface("TV", [(5654, 5693)], [(6752, 11616)]),
    "PV": Surface("PV", [(5694, 5729)], [(6752, 11616)]),
}


def get_mesh(faces, points, rows_to_keep) -> meshio.Mesh:
    triangle_data_local = faces[rows_to_keep]

    node_indices_that_we_need = np.unique(triangle_data_local)
    node_data_local = points[node_indices_that_we_need, :]

    node_id_map_original_to_local = {
        original: local for local, original in enumerate(node_indices_that_we_need)
    }

    # now apply the mapping to the triangle_data
    for i in range(triangle_data_local.shape[0]):
        triangle_data_local[i, 0] = node_id_map_original_to_local[triangle_data_local[i, 0]]
        triangle_data_local[i, 1] = node_id_map_original_to_local[triangle_data_local[i, 1]]
        triangle_data_local[i, 2] = node_id_map_original_to_local[triangle_data_local[i, 2]]

    # node_indices_that_we_need = np.unique(triangle_data_local)
    # node_data_local = points[node_indices_that_we_need, :]

    return meshio.Mesh(points=node_data_local, cells=[("triangle", triangle_data_local)])


def get_epi_mesh(points: np.ndarray) -> meshio.Mesh:
    logger.debug("Getting EPI mesh")
    faces = connectivity[surfaces["EPI"].face_indices, :]
    triangle_should_be_removed = np.zeros(faces.shape[0], dtype=bool)
    for valve_name in ["MV", "AV", "TV", "PV"]:
        for start, end in surfaces[valve_name].vertex_range:
            triangle_should_be_removed |= np.any(
                np.logical_and(
                    faces >= start,
                    faces <= end,
                ),
                axis=1,
            )

    triangle_should_be_kept = np.logical_not(triangle_should_be_removed)
    rows_to_keep = np.flatnonzero(triangle_should_be_kept)
    return get_mesh(faces, points, rows_to_keep)


def get_valve_mesh(surface_name: str, points: np.ndarray) -> meshio.Mesh:
    logger.debug(f"Getting valve mesh for {surface_name}")
    faces = connectivity[surfaces[surface_name].face_indices, :]
    triangle_should_be_kept = np.zeros(faces.shape[0], dtype=bool)

    for start, end in surfaces[surface_name].vertex_range:
        triangle_should_be_kept |= np.any(
            np.logical_and(
                faces >= start,
                faces <= end,
            ),
            axis=1,
        )

    rows_to_keep = np.flatnonzero(triangle_should_be_kept)

    return get_mesh(faces, points, rows_to_keep)


def get_chamber_mesh(surface_name: str, points: np.ndarray) -> meshio.Mesh:
    logger.debug(f"Getting chamber mesh for {surface_name}")
    faces = connectivity[surfaces[surface_name].face_indices, :]
    triangle_should_be_kept = np.ones(faces.shape[0], dtype=bool)
    rows_to_keep = np.flatnonzero(triangle_should_be_kept)
    return get_mesh(faces, points, rows_to_keep)
