from textwrap import dedent
from pathlib import Path
from typing import Literal
from argparse import ArgumentParser
import subprocess
import logging

logger = logging.getLogger(__name__)


def add_parser_arguments(parser: ArgumentParser) -> None:
    """Add parser arguments for mesh generation.

    Parameters
    ----------
    parser : ArgumentParser
        The argument parser to add arguments to.

    """
    parser.add_argument(
        "folder",
        type=Path,
        help="Directory to save the generated meshes.",
    )
    parser.add_argument(
        "--char_length_max",
        type=float,
        default=5.0,
        help="Maximum characteristic length of the mesh elements.",
    )
    parser.add_argument(
        "--char_length_min",
        type=float,
        default=5.0,
        help="Minimum characteristic length of the mesh elements.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print verbose output.",
    )
    parser.add_argument(
        "-c",
        "--case",
        choices=["ED", "ES", "both"],
        default="ED",
        help="Case to generate surfaces for.",
    )
    parser.add_argument(
        "--clipped",
        action="store_true",
        help="Create a clipped mesh.",
    )


template = dedent(
    """
 // merge VTK files - each one will create a new surface:
Merge "LV_{case}.stl";
Merge "RV_{case}.stl";
Merge "RVFW_{case}.stl";
Merge "EPI_{case}.stl";
Merge "MV_{case}.stl";
Merge "AV_{case}.stl";
Merge "PV_{case}.stl";
Merge "TV_{case}.stl";
Coherence Mesh;

Mesh.Optimize = 1;
Mesh.OptimizeNetgen = 1;
Mesh.Smoothing = 1;

CreateTopology;

// Create geometry for all curves and surfaces:
CreateGeometry;

// Define the volume (assuming there is no hole)
s() = Surface{{:}};
Surface Loop(1) = s();
Volume(1) = 1;

// Since we did not create any new surface, we can easily define physical groups
// (would need to inspect the result of ClassifySurfaces otherwise):
Physical Surface("LV", 1) = {{1}};
Physical Surface("RV", 2) = {{2, 3}};
Physical Surface("EPI", 3) = {{4}};
Physical Surface("MV", 4) = {{5}};
Physical Surface("AV", 5) = {{6}};
Physical Surface("PV", 6) = {{7}};
Physical Surface("TV", 7) = {{8}};
Physical Volume("Wall", 8) = {{1}};

Mesh.CharacteristicLengthMax = {char_length_max};
Mesh.CharacteristicLengthMin = {char_length_min};
// Mesh.CharacteristicLengthFromCurvature = 1;
// Mesh.MinimumElementsPerTwoPi = 20;
// Mesh.AngleToleranceFacetOverlap = 0.04;
// Mesh.MeshSizeFromCurvature = 12;

// OptimizeMesh "Gmsh";
// OptimizeNetgen 1;
// Coherence Mesh;
// Set a threshold for optimizing tetrahedra that have a quality below; default 0.3
// Mesh.OptimizeThreshold = 0.5;
// Mesh.AngleToleranceFacetOverlap = 0.04;

// 3D mesh algorithm (1: Delaunay, 3: Initial mesh only,
// 4: Frontal, 7: MMG3D, 9: R-tree, 10: HXT); Default 1
Mesh.Algorithm3D = 1;
Coherence;
Mesh.MshFileVersion = 2.2;
"""
)


def create_mesh_geo(
    folder: Path,
    char_length_max: float,
    char_length_min: float,
    case: Literal["ED", "ES", "both"] = "ED",
) -> None:
    """Convert a vtp file to a gmsh mesh file using the surface mesh
    representation. The surface mesh is coarsened using the gmsh
    algorithm.

    Parameters
    ----------
    vtp : Path
        Path to the vtp file
    output : Path
        Path to the output folder
    """
    geofile = folder / f"{case}.geo"
    logger.debug(f"Writing {geofile}")

    geofile.write_text(
        template.format(char_length_max=char_length_max, char_length_min=char_length_min, case=case)
    )
    mshfile = folder / f"{case}.msh"
    logger.debug(f"Create mesh {mshfile} using gmsh")
    subprocess.run(
        ["gmsh", geofile.name, "-2", "-3", "-o", mshfile.name],
        cwd=folder,
    )
    logger.debug("Finished running gmsh")


def main(
    folder: Path,
    case: Literal["ED", "ES", "both"] = "ED",
    char_length_max: float = 5.0,
    char_length_min: float = 5.0,
    verbose: bool = False,
    clipped: bool = False,
) -> None:
    """Create a gmsh mesh file from the surface mesh representation.

    Parameters
    ----------
    folder : Path
        Path to the output folder
    case : str
        Case name, by default "ED"
    char_length_max : float
        Maximum characteristic length of the mesh elements, by default 5.0
    char_length_min : float
        Minimum characteristic length of the mesh elements, by default 5.0
    verbose : bool, optional
        Print verbose output, by default False
    clipped : bool, optional
        Create a clipped mesh, by default False
    """
    if clipped:
        return create_clipped_mesh(
            folder=folder,
            case=case,
            char_length_max=char_length_max,
            char_length_min=char_length_min,
        )
    logger.info(f"Creating mesh for {case} with {char_length_max=}, {char_length_min=}")
    try:
        import gmsh

    except ImportError:
        logger.warning("gmsh python API not installed. Try subprocess.")
        return create_mesh_geo(folder, char_length_max, char_length_min, case)

    gmsh.initialize()
    if not verbose:
        gmsh.option.setNumber("General.Verbosity", 0)

    # Merge all surfaces
    gmsh.merge(f"{folder}/LV_{case}.stl")
    gmsh.merge(f"{folder}/RV_{case}.stl")
    gmsh.merge(f"{folder}/RVFW_{case}.stl")
    gmsh.merge(f"{folder}/MV_{case}.stl")
    gmsh.merge(f"{folder}/AV_{case}.stl")
    gmsh.merge(f"{folder}/PV_{case}.stl")
    gmsh.merge(f"{folder}/TV_{case}.stl")
    gmsh.merge(f"{folder}/EPI_{case}.stl")
    gmsh.model.mesh.removeDuplicateNodes()
    gmsh.model.mesh.create_topology()
    gmsh.model.mesh.create_geometry()
    surfaces = gmsh.model.getEntities(2)

    gmsh.model.geo.addSurfaceLoop([s[1] for s in surfaces], 1)
    vol = gmsh.model.geo.addVolume([1], 1)
    gmsh.model.geo.synchronize()

    physical_groups = {
        "LV": [1],
        "RV": [2, 3],
        "MV": [4],
        "AV": [5],
        "PV": [6],
        "TV": [7],
        "EPI": [8],
    }
    for name, tag in physical_groups.items():
        p = gmsh.model.addPhysicalGroup(2, tag)
        gmsh.model.setPhysicalName(2, p, name)

    p = gmsh.model.addPhysicalGroup(3, [vol], 9)
    gmsh.model.setPhysicalName(3, p, "Wall")

    gmsh.option.setNumber("Mesh.Optimize", 1)
    gmsh.option.setNumber("Mesh.OptimizeNetgen", 1)
    gmsh.option.setNumber("Mesh.Smoothing", 1)
    gmsh.option.setNumber("Mesh.CharacteristicLengthMax", char_length_max)
    gmsh.option.setNumber("Mesh.CharacteristicLengthMin", char_length_min)
    gmsh.option.setNumber("Mesh.Algorithm3D", 1)

    gmsh.model.geo.synchronize()
    gmsh.model.mesh.generate(3)
    gmsh.write(f"{folder}/{case}.msh")
    logger.info(f"Created mesh {folder}/{case}.msh")
    gmsh.finalize()


def create_clipped_mesh(
    folder: Path,
    case: Literal["ED", "ES", "both"] = "ED",
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
    logger.info(f"Creating clipped mesh for {case} with {char_length_max=}, {char_length_min=}")
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

    p = gmsh.model.addPhysicalGroup(3, [vol], 5)
    gmsh.model.setPhysicalName(3, p, "Wall")

    gmsh.option.setNumber("Mesh.Optimize", 1)
    gmsh.option.setNumber("Mesh.OptimizeNetgen", 1)
    gmsh.option.setNumber("Mesh.Smoothing", 1)
    gmsh.option.setNumber("Mesh.CharacteristicLengthMax", char_length_max)
    gmsh.option.setNumber("Mesh.CharacteristicLengthMin", char_length_min)
    gmsh.option.setNumber("Mesh.Algorithm3D", 1)
    gmsh.model.geo.synchronize()
    gmsh.model.mesh.generate(3)
    outfile = (folder / f"{case}_clipped").with_suffix(".msh")
    gmsh.write(str(outfile))
    logger.info(f"Created mesh {outfile}")
    gmsh.finalize()
