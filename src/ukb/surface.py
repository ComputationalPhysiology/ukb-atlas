from __future__ import annotations
from pathlib import Path
import meshio
import numpy as np
import logging
from typing import NamedTuple

logger = logging.getLogger(__name__)
here = Path(__file__).parent.absolute()

connectivity_file = here / "connectivity.txt"
connectivity = np.loadtxt(connectivity_file, dtype=int)


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
