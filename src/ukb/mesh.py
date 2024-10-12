from textwrap import dedent
from pathlib import Path
import subprocess
import logging

logger = logging.getLogger(__name__)

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
    outdir: Path, char_length_max: float, char_length_min: float, case: str
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
    geofile = outdir / f"{case}.geo"
    logger.debug(f"Writing {geofile}")

    geofile.write_text(
        template.format(char_length_max=char_length_max, char_length_min=char_length_min, case=case)
    )
    mshfile = outdir / f"{case}.msh"
    logger.debug(f"Create mesh {mshfile} using gmsh")
    subprocess.run(
        ["gmsh", geofile.name, "-2", "-3", "-o", mshfile.name],
        cwd=outdir,
    )
    logger.debug("Finished running gmsh")


def create_mesh(
    outdir: Path, char_length_max: float, char_length_min: float, case: str, verbose: bool = False
) -> None:
    """Create a gmsh mesh file from the surface mesh representation.

    Parameters
    ----------
    outdir : Path
        Path to the output folder
    char_length_max : float
        Maximum characteristic length of the mesh elements
    char_length_min : float
        Minimum characteristic length of the mesh elements
    case : str
        Case name
    verbose : bool, optional
        Print verbose output, by default False
    """
    logger.info(f"Creating mesh for {case} with {char_length_max=}, {char_length_min=}")
    try:
        import gmsh

    except ImportError:
        logger.warning("gmsh python API not installed. Try subprocess.")
        return create_mesh_geo(outdir, char_length_max, char_length_min, case)

    gmsh.initialize()
    if not verbose:
        gmsh.option.setNumber("General.Verbosity", 0)

    # Merge all surfaces
    gmsh.merge(f"{outdir}/LV_{case}.stl")
    gmsh.merge(f"{outdir}/RV_{case}.stl")
    gmsh.merge(f"{outdir}/RVFW_{case}.stl")
    gmsh.merge(f"{outdir}/MV_{case}.stl")
    gmsh.merge(f"{outdir}/AV_{case}.stl")
    gmsh.merge(f"{outdir}/PV_{case}.stl")
    gmsh.merge(f"{outdir}/TV_{case}.stl")
    gmsh.merge(f"{outdir}/EPI_{case}.stl")
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
    gmsh.write(f"{outdir}/{case}.msh")
    logger.info(f"Created mesh {outdir}/{case}.msh")
    gmsh.finalize()
