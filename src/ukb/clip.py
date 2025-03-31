from argparse import ArgumentParser
from pathlib import Path
from typing import Literal
import logging

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
        choices=["ED", "ES", "both"],
        default="ED",
        help="Case to generate surfaces for.",
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


def main(
    folder: Path,
    case: Literal["ED", "ES", "both"] = "ED",
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
    case : Literal["ED", "ES", "both"], optional
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

    lvfname = folder / f"LV_{case}.stl"
    assert lvfname.exists(), f"File {lvfname} does not exist. Please check the path."
    logger.info(f"Reading {lvfname}")
    lv = pv.read(lvfname)
    lv_clip = lv.clip(normal=normal, origin=origin, invert=True)
    lv_clip.compute_normals(inplace=True, flip_normals=False)
    pv.save_meshio(folder / "lv_clipped.ply", lv_clip)
    logger.info(f"Saved {folder / 'lv_clipped.ply'}")

    rvfname = folder / f"RV_{case}.stl"
    assert rvfname.exists(), f"File {rvfname} does not exist. Please check the path."
    logger.info(f"Reading {rvfname}")
    rv_sept = pv.read(rvfname)
    rv_sept.compute_normals(inplace=True, flip_normals=False)

    rv_fw_fname = folder / f"RVFW_{case}.stl"
    assert rv_fw_fname.exists(), f"File {rv_fw_fname} does not exist. Please check the path."
    logger.info(f"Reading {rv_fw_fname}")
    rv_fw = pv.read(rv_fw_fname)
    logger.info("Merging RV and RVFW")
    rv = rv_sept + rv_fw
    if smooth:
        logger.info("Smoothing RV")
        rv = rv.smooth(n_iter=smooth_iter, relaxation_factor=smooth_relaxation)
    rv_clip = rv.clip(normal=normal, origin=origin, invert=True)
    rv_clip.compute_normals(inplace=True, flip_normals=False)
    logger.info(f"Saving {folder / 'rv_clipped.ply'}")
    pv.save_meshio(folder / "rv_clipped.ply", rv_clip)

    epi_fname = folder / f"EPI_{case}.stl"
    assert epi_fname.exists(), f"File {epi_fname} does not exist. Please check the path."
    logger.info(f"Reading {epi_fname}")
    epi = pv.read(epi_fname)
    epi_clip = epi.clip(normal=normal, origin=origin, invert=True)
    epi_clip.compute_normals(inplace=True, flip_normals=False)
    logger.info(f"Saving {folder / 'epi_clipped.ply'}")
    pv.save_meshio(folder / "epi_clipped.ply", epi_clip)


def create_clipped_mesh(
    folder: Path,
    name: str = "clipped",
    char_length_max: float = 5.0,
    char_length_min: float = 5.0,
    verbose: bool = False,
) -> None:
    """Create a gmsh mesh file from the surface mesh representation.

    Parameters
    ----------
    folder : Path
        Path to the output folde
    name : str
        Case name
    char_length_max : float
        Maximum characteristic length of the mesh elements
    char_length_min : float
        Minimum characteristic length of the mesh elements
    verbose : bool, optional
        Print verbose output, by default False
    """
    logger.info(f"Creating mesh for {name} with {char_length_max=}, {char_length_min=}")
    try:
        import gmsh

    except ImportError:
        logger.warning("gmsh python API not installed. Try subprocess.")
        # return create_mesh_geo(folder, char_length_max, char_length_min, name)
        raise
    gmsh.initialize()
    if not verbose:
        gmsh.option.setNumber("General.Verbosity", 0)

    # Merge all surfaces
    gmsh.merge(f"{folder}/lv_clipped.ply")
    gmsh.merge(f"{folder}/rv_clipped.ply")
    gmsh.merge(f"{folder}/epi_clipped.ply")

    gmsh.model.mesh.removeDuplicateNodes()
    gmsh.model.mesh.create_topology()
    gmsh.model.mesh.create_geometry()
    surfaces = gmsh.model.getEntities(2)

    # Create base plane
    base_ring = gmsh.model.geo.addCurveLoop([s[1] for s in surfaces], 1)

    gmsh.model.geo.addPlaneSurface([base_ring], 4)
    gmsh.model.geo.synchronize()

    surfaces = gmsh.model.getEntities(2)
    gmsh.model.geo.addSurfaceLoop([s[1] for s in surfaces], 1)
    vol = gmsh.model.geo.addVolume([1], 1)
    gmsh.model.geo.synchronize()

    gmsh.model.geo.synchronize()
    physical_groups = {
        "LV": [1],
        "RV": [2],
        "EPI": [3],
        "BASE": [4],
    }
    for n, tag in physical_groups.items():
        p = gmsh.model.addPhysicalGroup(2, tag)
        gmsh.model.setPhysicalName(2, p, n)

    p = gmsh.model.addPhysicalGroup(3, [vol], 4)
    gmsh.model.setPhysicalName(3, p, "Wall")

    gmsh.option.setNumber("Mesh.Optimize", 1)
    gmsh.option.setNumber("Mesh.OptimizeNetgen", 1)
    gmsh.option.setNumber("Mesh.Smoothing", 1)
    gmsh.option.setNumber("Mesh.CharacteristicLengthMax", char_length_max)
    gmsh.option.setNumber("Mesh.CharacteristicLengthMin", char_length_min)
    gmsh.option.setNumber("Mesh.Algorithm3D", 1)
    gmsh.model.geo.synchronize()
    gmsh.model.mesh.generate(3)
    outfile = (folder / f"{name}").with_suffix(".msh")
    gmsh.write(str(outfile))
    logger.info(f"Created mesh {outfile}")
    gmsh.finalize()
