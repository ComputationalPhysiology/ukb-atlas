"""Smooth surfaces through the nodes of the atlas.

The biv-me template is the subdivision of a coarse control mesh: each of the 354
faces of the control mesh on the endocardium and epicardium is split into a grid
of 4 x 4 quads, each made of two triangles of the template. So the 5 x 5 nodes on
a face are samples of a smooth surface on a regular grid in the local coordinates
of the face. We interpolate them with a tensor product cubic spline on each face,
which goes through all the nodes. Along an edge of a face the spline only depends
on the 5 nodes on that edge, so the splines of neighbouring faces match.

The template is refined by splitting each triangle into four, placing the new
nodes on the splines. The triangles that are not on a face of the control mesh
(the valve rims and caps, and the septal bridge) are split at the midpoints of
their edges, except for the edges they share with the faces.

The element of the control mesh and the local coordinates of each node come from
the biv-me files vendored in ``data/biv-me`` (see the README there).
"""

from __future__ import annotations

import functools
import logging
from typing import NamedTuple

import numpy as np
from scipy.interpolate import CubicSpline
from scipy.optimize import linear_sum_assignment

from . import template

logger = logging.getLogger(__name__)

NUM_CONTROL_FACES = 354
#: Number of intervals of the grid of nodes along each side of a face
GRID = 4


class ControlFaces(NamedTuple):
    """The faces of the control mesh, with the nodes inside them.

    Parameters
    ----------
    interior : np.ndarray
        ``(354, 3, 3)`` interior nodes of each face, indexed by their grid
        position ``(i - 1, j - 1)`` in the face
    """

    interior: np.ndarray


@functools.cache
def load_control_faces() -> ControlFaces:
    """Load (and cache) the faces of the control mesh from the vendored biv-me files.

    Returns
    -------
    ControlFaces
        The interior nodes of each face

    Raises
    ------
    ValueError
        If the files do not match the expected structure
    """
    element = np.loadtxt(template.data_dir / "etVertexElementNum.txt", dtype=int)
    xi = np.loadtxt(template.data_dir / "etVertexXi.txt")
    if element.shape != (template.NUM_NODES,) or xi.shape != (template.NUM_NODES, 3):
        raise ValueError(f"Expected the local coordinates of {template.NUM_NODES} nodes")
    ij = np.rint(xi[:, :2] * GRID).astype(int)
    if not np.allclose(ij / GRID, xi[:, :2]):
        raise ValueError(f"Expected the nodes on a grid with spacing 1/{GRID} in each element")

    inside = np.flatnonzero((ij > 0).all(axis=1) & (ij < GRID).all(axis=1))
    # A face is an element of the control mesh and a side of it (xi3 = 0 or 1)
    sides = np.stack([element[inside], xi[inside, 2]], axis=1)
    keys, face = np.unique(sides, axis=0, return_inverse=True)
    if len(keys) != NUM_CONTROL_FACES:
        raise ValueError(f"Expected {NUM_CONTROL_FACES} faces of the control mesh, got {len(keys)}")
    interior = np.full((NUM_CONTROL_FACES, GRID - 1, GRID - 1), -1)
    interior[face.ravel(), ij[inside, 0] - 1, ij[inside, 1] - 1] = inside
    if (interior < 0).any():
        raise ValueError("Expected a node at each interior grid point of each face")
    return ControlFaces(interior=interior)


def lagrange(t: np.ndarray, nodes: np.ndarray) -> np.ndarray:
    """Values of the Lagrange polynomials on ``nodes`` at ``t``, shape ``(len(t), len(nodes))``."""
    values = np.ones((len(t), len(nodes)))
    for k, nk in enumerate(nodes):
        for m, nm in enumerate(nodes):
            if m != k:
                values[:, k] *= (t - nm) / (nk - nm)
    return values


def neighbours(faces: np.ndarray) -> dict[int, set[int]]:
    result: dict[int, set[int]] = {}
    for a, b in faces[:, [0, 1, 1, 2, 2, 0]].reshape(-1, 2).tolist():
        result.setdefault(a, set()).add(b)
        result.setdefault(b, set()).add(a)
    return result


def face_grids(points: np.ndarray, tpl: template.Template | None = None) -> np.ndarray:
    """Return the ``(354, 5, 5)`` grid of nodes on each face of the control mesh.

    The nodes on the boundary of a face are stored with only one of the faces
    sharing them, so they are found from the template: the boundary nodes are the
    neighbours of the interior nodes closest to where the interior grid
    extrapolates to (each used once), and each corner is the common neighbour of
    the two boundary nodes next to it.

    Parameters
    ----------
    points : np.ndarray
        Node coordinates, shape ``(5810, 3)``
    tpl : template.Template | None
        Template to use, by default the vendored biv-me template

    Returns
    -------
    np.ndarray
        Node indices of the grid of each face

    Raises
    ------
    ValueError
        If a grid does not match the triangles of the template
    """
    tpl = tpl or template.load_template()
    template.check_points(points)
    interior = load_control_faces().interior
    nbrs = neighbours(tpl.faces)
    extrapolate = lagrange(np.arange(GRID + 1.0), np.arange(1.0, GRID))
    corners = [  # corner, its two neighbours on the boundary and the interior node next to it
        ((0, 0), (1, 0), (0, 1), (1, 1)),
        ((GRID, 0), (GRID - 1, 0), (GRID, 1), (GRID - 1, 1)),
        ((0, GRID), (1, GRID), (0, GRID - 1), (1, GRID - 1)),
        ((GRID, GRID), (GRID - 1, GRID), (GRID, GRID - 1), (GRID - 1, GRID - 1)),
    ]
    grids = np.full((NUM_CONTROL_FACES, GRID + 1, GRID + 1), -1)
    for f, inner in enumerate(interior):
        grid = grids[f]
        grid[1:GRID, 1:GRID] = inner
        expected = np.einsum("ia,jb,abx->ijx", extrapolate, extrapolate, points[inner])
        inner_set = set(inner.ravel().tolist())
        candidates = np.array(sorted(set().union(*(nbrs[n] for n in inner_set)) - inner_set))
        # Assign the boundary positions together, so that no node is used twice
        boundary = np.nonzero(grid < 0)
        distance = np.linalg.norm(
            expected[boundary][:, None, :] - points[candidates][None, :, :], axis=2
        )
        position, candidate = linear_sum_assignment(distance)
        grid[boundary[0][position], boundary[1][position]] = candidates[candidate]
        for corner, a, b, inside in corners:
            common = (nbrs[grid[a]] & nbrs[grid[b]]) - {grid[inside]}
            if len(common) == 1:
                grid[corner] = common.pop()
    check_grids(grids, tpl)
    return grids


def check_grids(grids: np.ndarray, tpl: template.Template) -> None:
    """Raise a ``ValueError`` unless each quad of each grid is two triangles of the template."""
    triangles = {tuple(t) for t in np.sort(tpl.faces, axis=1).tolist()}
    for f, grid in enumerate(grids):
        if len(np.unique(grid)) != (GRID + 1) ** 2:
            raise ValueError(f"The grid of face {f} of the control mesh has repeated nodes")
        for i in range(GRID):
            for j in range(GRID):
                a, b, c, d = grid[i, j], grid[i + 1, j], grid[i + 1, j + 1], grid[i, j + 1]
                splits = [((a, b, c), (a, c, d)), ((a, b, d), (b, c, d))]
                if not any(all(tuple(sorted(t)) in triangles for t in s) for s in splits):
                    raise ValueError(
                        f"The grid of face {f} of the control mesh does not match the template"
                    )


@functools.cache
def spline_weights() -> CubicSpline:
    """The (not-a-knot) cubic spline through ``GRID + 1`` equispaced values, as weights."""
    return CubicSpline(np.linspace(0, 1, GRID + 1), np.eye(GRID + 1))


def evaluate(grid_points: np.ndarray, uv: np.ndarray) -> np.ndarray:
    """Evaluate the splines of faces at local coordinates.

    Parameters
    ----------
    grid_points : np.ndarray
        ``(n, 5, 5, 3)`` coordinates of the grid of the face of each point
    uv : np.ndarray
        ``(n, 2)`` local coordinates of each point in its face

    Returns
    -------
    np.ndarray
        ``(n, 3)`` coordinates of the points
    """
    weights = spline_weights()
    return np.einsum("na,nb,nabx->nx", weights(uv[:, 0]), weights(uv[:, 1]), grid_points)


def triangle_faces(tpl: template.Template, grids: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return the face of the control mesh that each triangle is on (-1 if none), and
    the local coordinates of its nodes in that face, shape ``(num_triangles, 3, 2)``."""
    where: dict[int, dict[int, tuple[float, float]]] = {}
    for f, grid in enumerate(grids):
        for i in range(GRID + 1):
            for j in range(GRID + 1):
                where.setdefault(int(grid[i, j]), {})[f] = (i / GRID, j / GRID)
    face = np.full(len(tpl.faces), -1)
    uv = np.zeros((len(tpl.faces), 3, 2))
    for t, triangle in enumerate(tpl.faces.tolist()):
        common = functools.reduce(set.intersection, (set(where.get(n, {})) for n in triangle))
        if common:
            face[t] = min(common)
            uv[t] = [where[n][face[t]] for n in triangle]
    return face, uv


def refine(
    points: np.ndarray, levels: int, tpl: template.Template | None = None
) -> tuple[np.ndarray, template.Template]:
    """Refine the template by splitting each triangle into four ``levels`` times.

    The new nodes on the endocardium and epicardium are placed on the splines
    through the nodes of the atlas (see the module documentation). The nodes of the
    template keep their indices, and the new nodes are added after them.

    Parameters
    ----------
    points : np.ndarray
        Node coordinates, shape ``(5810, 3)``
    levels : int
        Number of times to refine
    tpl : template.Template | None
        Template to use, by default the vendored biv-me template

    Returns
    -------
    tuple[np.ndarray, template.Template]
        The coordinates of the nodes of the refined template, and the refined template
    """
    tpl = tpl or template.load_template()
    if levels < 0:
        raise ValueError(f"The number of refinements must be non-negative, got {levels}")
    if levels == 0:
        return points, tpl

    grids = face_grids(points, tpl)
    grid_points = points[grids]
    face, uv = triangle_faces(tpl, grids)
    faces = tpl.faces
    for _ in range(levels):
        edges = np.sort(faces[:, [0, 1, 1, 2, 2, 0]].reshape(-1, 3, 2), axis=2)
        unique, edge = np.unique(edges.reshape(-1, 2), axis=0, return_inverse=True)
        edge = edge.reshape(-1, 3)
        mid = 0.5 * (points[unique[:, 0]] + points[unique[:, 1]])
        # Local coordinates of the midpoints of edges 01, 12 and 20 of each triangle
        mid_uv = 0.5 * (uv + uv[:, [1, 2, 0]])
        on_face = np.flatnonzero(face >= 0)
        rows, first = np.unique(edge[on_face].ravel(), return_index=True)
        triangle, k = np.divmod(first, 3)
        triangle = on_face[triangle]
        mid[rows] = evaluate(grid_points[face[triangle]], mid_uv[triangle, k])

        m01, m12, m20 = (len(points) + edge).T
        a, b, c = faces.T
        faces = np.stack(
            [(a, m01, m20), (m01, b, m12), (m20, m12, c), (m01, m12, m20)], axis=1
        ).transpose(2, 1, 0)
        faces = faces.reshape(-1, 3)
        u01, u12, u20 = mid_uv.transpose(1, 0, 2)
        ua, ub, uc = uv.transpose(1, 0, 2)
        uv = np.stack(
            [
                np.stack([ua, u01, u20], axis=1),
                np.stack([u01, ub, u12], axis=1),
                np.stack([u20, u12, uc], axis=1),
                np.stack([u01, u12, u20], axis=1),
            ],
            axis=1,
        ).reshape(-1, 3, 2)
        face = np.repeat(face, 4)
        points = np.vstack([points, mid])

    # The children of triangle t are the triangles 4^levels * t, ..., 4^levels * (t + 1) - 1
    n = 4**levels
    regions = {
        name: (n * rows[:, None] + np.arange(n)).ravel() for name, rows in tpl.regions.items()
    }
    refined = tpl._replace(faces=faces, regions=regions, num_nodes=len(points))
    logger.debug(f"Refined the template {levels} times to {len(faces)} triangles")
    return points, refined
