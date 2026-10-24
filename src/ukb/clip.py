from argparse import ArgumentParser
from pathlib import Path
from typing import Literal
import logging

from . import surface

logger = logging.getLogger(__name__)


def add_parser_arguments(parser: ArgumentParser) -> None:
    """Add parser arguments for clipping."

    Parameters
    ----------
    parser : ArgumentParser
        The argument parser to add arguments to.

    """
    parser.add_argument(
        "folder",
        type=Path,
        help="Directory to save the generated surfaces.",
    )
    parser.add_argument(
        "-c",
        "--case",
        choices=["ED", "ES"],
        default="ED",
        help="Case to clip the surfaces for.",
    )
    parser.add_argument(
        "-ox",
        "--origin-x",
        type=float,
        default=-13.612554383622273,
        help="Origin of the clipping plane in x direction.",
    )
    parser.add_argument(
        "-oy",
        "--origin-y",
        type=float,
        default=18.55767189380559,
        help="Origin of the clipping plane in y direction.",
    )
    parser.add_argument(
        "-oz",
        "--origin-z",
        type=float,
        default=15.135103714006394,
        help="Origin of the clipping plane in z direction.",
    )
    parser.add_argument(
        "-nx",
        "--normal-x",
        type=float,
        default=-0.7160843664428893,
        help="Normal of the clipping plane in x direction.",
    )
    parser.add_argument(
        "-ny",
        "--normal-y",
        type=float,
        default=0.544394641424108,
        help="Normal of the clipping plane in y direction.",
    )
    parser.add_argument(
        "-nz",
        "--normal-z",
        type=float,
        default=0.4368725838557541,
        help="Normal of the clipping plane in z direction.",
    )
    parser.add_argument(
        "-s",
        "--smooth",
        action="store_true",
        help="Smooth the RV surface.",
    )
    parser.add_argument(
        "-si",
        "--smooth-iter",
        type=int,
        default=100,
        help="Number of iterations to smooth the RV surface.",
    )
    parser.add_argument(
        "-sr",
        "--smooth-relaxation",
        type=float,
        default=0.1,
        help="Relaxation factor to smooth the RV surface.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print verbose output.",
    )


def default_origin() -> tuple[float, float, float]:
    return -13.612554383622273, 18.55767189380559, 15.135103714006394


def default_normal() -> tuple[float, float, float]:
    return -0.7160843664428893, 0.544394641424108, 0.4368725838557541


def main(
    folder: Path,
    case: Literal["ED", "ES"] = "ED",
    origin_x: float = -13.612554383622273,
    origin_y: float = 18.55767189380559,
    origin_z: float = 15.135103714006394,
    normal_x: float = -0.7160843664428893,
    normal_y: float = 0.544394641424108,
    normal_z: float = 0.4368725838557541,
    smooth: bool = True,
    smooth_iter: int = 100,
    smooth_relaxation: float = 0.1,
):
    """Main function to clip the surfaces.
    Parameters
    ----------
    folder : Path
        Directory to save the generated surfaces.
    case : Literal["ED", "ES"], optional
        Case to generate surfaces for. The default is "ED".
    origin_x : float, optional
        Origin of the clipping plane in x direction. The default is -13.612554383622273.
    origin_y : float, optional
        Origin of the clipping plane in y direction. The default is 18.55767189380559.
    origin_z : float, optional
        Origin of the clipping plane in z direction. The default is 15.135103714006394.
    normal_x : float, optional
        Normal of the clipping plane in x direction. The default is -0.7160843664428893.
    normal_y : float, optional
        Normal of the clipping plane in y direction. The default is 0.544394641424108.
    normal_z : float, optional
        Normal of the clipping plane in z direction. The default is 0.4368725838557541.
    smooth : bool, optional
        Smooth the RV surface. The default is True.
    smooth_iter : int, optional
        Number of iterations to smooth the RV surface. The default is 100.
    smooth_relaxation : float, optional
        Relaxation factor to smooth the RV surface. The default is 0.1.
    """
    # NOTE: clip() must be followed by triangulate(). VTK >= 9.7 emits quads
    # along the cut plane, and gmsh's PLY reader reads only three vertex indices
    # per face, so non-triangular faces desync the binary stream ("Wrong node
    # index") and are silently truncated in ASCII.
    origin = [origin_x, origin_y, origin_z]
    normal = [normal_x, normal_y, normal_z]

    logger.info(f"Folder: {folder}")
    logger.info(f"Case: {case}")
    logger.info(f"Origin: {origin}")
    logger.info(f"Normal: {normal}")

    try:
        import pyvista as pv
    except ImportError:
        logger.warning("pyvista not installed. Cannot crop surfaces.")
        return

    files = surface.read_manifest(folder, case)

    def read(name: str):
        logger.info(f"Reading {', '.join(map(str, files[name]))}")
        return pv.merge([pv.read(path) for path in files[name]])

    lv = read("LV_ENDO")
    lv_clip = lv.clip(normal=normal, origin=origin, invert=True).triangulate()
    lv_clip.compute_normals(inplace=True, flip_normals=False)
    pv.save_meshio(folder / "lv_clipped.ply", lv_clip)
    logger.info(f"Saved {folder / 'lv_clipped.ply'}")

    rv = read("RV_ENDO")
    if smooth:
        logger.info("Smoothing RV")
        rv = rv.smooth(n_iter=smooth_iter, relaxation_factor=smooth_relaxation)
    rv_clip = rv.clip(normal=normal, origin=origin, invert=True).triangulate()
    rv_clip.compute_normals(inplace=True, flip_normals=False)
    logger.info(f"Saving {folder / 'rv_clipped.ply'}")
    pv.save_meshio(folder / "rv_clipped.ply", rv_clip)

    epi = read("EPI")
    epi_clip = epi.clip(normal=normal, origin=origin, invert=True).triangulate()
    epi_clip.compute_normals(inplace=True, flip_normals=False)
    logger.info(f"Saving {folder / 'epi_clipped.ply'}")
    pv.save_meshio(folder / "epi_clipped.ply", epi_clip)
