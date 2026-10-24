"""The biventricular template triangulation from biv-me.

The UK Biobank atlas only stores node coordinates. The triangulation, and the
anatomical region each triangle belongs to, come from the biv-me template files
vendored in ``data/biv-me`` (see the README there for provenance).
"""

from __future__ import annotations

import functools
import logging
from pathlib import Path
from typing import Iterable, NamedTuple

import meshio
import numpy as np

logger = logging.getLogger(__name__)
here = Path(__file__).parent.absolute()
data_dir = here / "data" / "biv-me"

NUM_NODES = 5810
NUM_FACES = 11760
NUM_BRIDGE_FACES = 160

VALVES = ("MV", "AV", "TV", "PV")
REGIONS = (
    "LV_ENDO",
    "RV_SEPTUM",
    "RV_FREEWALL",
    "RV_EPI",
    "LV_EPI",
    "MV",
    "AV",
    "TV",
    "PV",
    "MV_CAP",
    "AV_CAP",
    "TV_CAP",
    "PV_CAP",
    "SEPTAL_BRIDGE",
)

# biv-me material name -> region name
MATERIALS = {
    "LV_ENDOCARDIAL": "LV_ENDO",
    "RV_SEPTUM": "RV_SEPTUM",
    "RV_FREEWALL": "RV_FREEWALL",
    "RV_EPICARDIAL": "RV_EPI",
    "LV_EPICARDIAL": "LV_EPI",
    "MITRAL_VALVE_CUT": "MV",
    "AORTA_VALVE_CUT": "AV",
    "TRICUSPID_VALVE_CUT": "TV",
    "PULMONARY_VALVE__CUT": "PV",
    "MITRAL_VALVE": "MV_CAP",
    "AORTA_VALVE": "AV_CAP",
    "TRICUSPID_VALVE": "TV_CAP",
    "PULMONARY_VALVE": "PV_CAP",
}

# Endocardial regions whose boundary is closed off by each valve
ENDOCARDIUM = {
    "MV": ("LV_ENDO",),
    "AV": ("LV_ENDO",),
    "TV": ("RV_SEPTUM", "RV_FREEWALL"),
    "PV": ("RV_SEPTUM", "RV_FREEWALL"),
}


class Template(NamedTuple):
    """Labelled biventricular template.

    Attributes
    ----------
    faces : np.ndarray
        Triangles (0-based node indices), the 11760 triangles of
        ``ETIndicesSorted.txt`` followed by the 160 septal bridge triangles.
    regions : dict[str, np.ndarray]
        Region name -> row indices into ``faces``.
    rings : dict[str, np.ndarray]
        Valve -> ordered loop of the nodes shared by the endocardium, the valve
        rim and the valve cap.
    centres : dict[str, int]
        Valve -> centre node of the valve cap.
    insertion : np.ndarray
        Nodes on the RV insertion line (shared by RV septum and RV free wall).
    epi_seam : np.ndarray
        Nodes shared by the LV and RV epicardium.
    num_nodes : int
        Number of nodes in the template.
    """

    faces: np.ndarray
    regions: dict[str, np.ndarray]
    rings: dict[str, np.ndarray]
    centres: dict[str, int]
    insertion: np.ndarray
    epi_seam: np.ndarray
    num_nodes: int


def edges_with_counts(faces: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return the unique (sorted) edges of ``faces`` and how many triangles use each."""
    edges = np.sort(faces[:, [0, 1, 1, 2, 2, 0]].reshape(-1, 2), axis=1)
    return np.unique(edges, axis=0, return_counts=True)


def boundary_edges(faces: np.ndarray) -> np.ndarray:
    edges, counts = edges_with_counts(faces)
    return edges[counts == 1]


def order_loop(edges: np.ndarray) -> np.ndarray:
    """Order the nodes of a single closed loop given by its edges."""
    neighbours: dict[int, list[int]] = {}
    for a, b in edges.tolist():
        neighbours.setdefault(a, []).append(b)
        neighbours.setdefault(b, []).append(a)
    if any(len(n) != 2 for n in neighbours.values()):
        raise ValueError("Edges do not form a simple closed loop")

    start = min(neighbours)
    loop = [start]
    prev, current = start, neighbours[start][0]
    while current != start:
        loop.append(current)
        a, b = neighbours[current]
        prev, current = current, (b if a == prev else a)
    if len(loop) != len(neighbours):
        raise ValueError("Edges form more than one loop")
    return np.array(loop)


def read_materials(materials_file: Path) -> np.ndarray:
    labels = []
    for i, line in enumerate(materials_file.read_text().splitlines()):
        if not line.strip():
            continue
        index, material = line.split()
        if int(index) != i:
            raise ValueError(f"Expected triangle index {i} in {materials_file}, got {index}")
        if material not in MATERIALS:
            raise ValueError(f"Unknown material {material!r} in {materials_file}")
        labels.append(MATERIALS[material])
    return np.array(labels)


def build_template(sorted_file: Path, materials_file: Path, bridge_file: Path) -> Template:
    """Load the template from the biv-me files and validate it.

    Parameters
    ----------
    sorted_file : Path
        ``ETIndicesSorted.txt`` (1-based triangles)
    materials_file : Path
        ``ETIndicesMaterials.txt`` (one material per triangle)
    bridge_file : Path
        ``thru_wall_et_indices.txt`` (1-based triangles)

    Returns
    -------
    Template
        The labelled template

    Raises
    ------
    ValueError
        If the files are inconsistent with each other or with the expected topology
    """
    faces = np.loadtxt(sorted_file, dtype=int) - 1
    bridge = np.loadtxt(bridge_file, dtype=int) - 1
    labels = read_materials(materials_file)

    if faces.shape != (NUM_FACES, 3):
        raise ValueError(f"Expected {NUM_FACES} triangles in {sorted_file}, got {faces.shape}")
    if bridge.shape != (NUM_BRIDGE_FACES, 3):
        raise ValueError(
            f"Expected {NUM_BRIDGE_FACES} triangles in {bridge_file}, got {bridge.shape}"
        )
    if len(labels) != NUM_FACES:
        raise ValueError(f"Expected {NUM_FACES} materials in {materials_file}, got {len(labels)}")
    for name, f in [(sorted_file, faces), (bridge_file, bridge)]:
        if f.min() < 0 or f.max() >= NUM_NODES:
            raise ValueError(f"Node indices in {name} must be between 1 and {NUM_NODES}")

    regions = {name: np.flatnonzero(labels == name) for name in MATERIALS.values()}
    regions["SEPTAL_BRIDGE"] = NUM_FACES + np.arange(NUM_BRIDGE_FACES)
    all_faces = np.vstack([faces, bridge])

    def nodes(*names: str) -> np.ndarray:
        return np.unique(all_faces[np.concatenate([regions[n] for n in names])])

    # Without the caps the template is one closed surface
    wall = np.concatenate([regions[r] for r in REGIONS[:9]])
    _, counts = edges_with_counts(all_faces[wall])
    if not np.all(counts == 2):
        raise ValueError("Template surface (without valve caps) is not a closed manifold")

    rings: dict[str, np.ndarray] = {}
    centres: dict[str, int] = {}
    for valve in VALVES:
        cap = all_faces[regions[f"{valve}_CAP"]]
        centre = functools.reduce(np.intersect1d, cap)
        if len(centre) != 1:
            raise ValueError(f"{valve} cap is not a fan around a single centre node")
        centres[valve] = int(centre[0])
        rings[valve] = order_loop(boundary_edges(cap))

    for endo in set(ENDOCARDIUM.values()):
        endo_boundary = np.unique(
            boundary_edges(all_faces[np.concatenate([regions[r] for r in endo])])
        )
        valve_rings = np.concatenate([rings[v] for v, e in ENDOCARDIUM.items() if e == endo])
        if not np.array_equal(endo_boundary, np.sort(valve_rings)):
            raise ValueError(f"Boundary of {'+'.join(endo)} does not match the valve caps")

    all_rings = np.concatenate(list(rings.values()))
    insertion = np.setdiff1d(np.intersect1d(nodes("RV_SEPTUM"), nodes("RV_FREEWALL")), all_rings)
    epi_seam = np.intersect1d(nodes("LV_EPI"), nodes("RV_EPI"))
    if not np.array_equal(nodes("SEPTAL_BRIDGE"), np.union1d(insertion, epi_seam)):
        raise ValueError("Septal bridge does not connect the RV insertion line to the epi seam")

    return Template(
        faces=all_faces,
        regions=regions,
        rings=rings,
        centres=centres,
        insertion=insertion,
        epi_seam=epi_seam,
        num_nodes=NUM_NODES,
    )


@functools.cache
def load_template() -> Template:
    """Load (and cache) the vendored biv-me template."""
    logger.debug(f"Loading template from {data_dir}")
    return build_template(
        data_dir / "ETIndicesSorted.txt",
        data_dir / "ETIndicesMaterials.txt",
        data_dir / "thru_wall_et_indices.txt",
    )


def check_points(points: np.ndarray, name: str = "points") -> None:
    """Raise a ``ValueError`` unless ``points`` has one row per template node.

    Parameters
    ----------
    points : np.ndarray
        Node coordinates
    name : str
        Name of the points used in the error message
    """
    if points.shape == (NUM_NODES, 3):
        return
    msg = f"Expected {name} of shape ({NUM_NODES}, 3), got {points.shape}."
    if len(points) == 5806:
        msg += (
            " Points with the valve centres removed (5806 nodes) from older versions are "
            "not supported."
        )
    elif len(points) == 5352:
        msg += (
            " The atlas of all UK Biobank subjects (--all) has 5352 nodes and does not match "
            "the biv-me template."
        )
    raise ValueError(msg)


def extract(
    points: np.ndarray, regions: Iterable[str], template: Template | None = None
) -> meshio.Mesh:
    """Extract the surface made up of the given template regions.

    Parameters
    ----------
    points : np.ndarray
        Node coordinates, shape ``(5810, 3)``
    regions : Iterable[str]
        Names of the regions (see ``REGIONS``) to include
    template : Template | None
        Template to use, by default the vendored biv-me template

    Returns
    -------
    meshio.Mesh
        Triangle mesh with local node numbering
    """
    template = template or load_template()
    regions = list(regions)
    unknown = [r for r in regions if r not in template.regions]
    if unknown:
        raise ValueError(f"Unknown regions {unknown}, expected some of {REGIONS}")

    faces = template.faces[np.concatenate([template.regions[r] for r in regions])]
    used, local = np.unique(faces, return_inverse=True)
    return meshio.Mesh(points=points[used], cells=[("triangle", local.reshape(-1, 3))])
