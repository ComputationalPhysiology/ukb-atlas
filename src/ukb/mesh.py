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
Merge "EPI_{case}.stl";
Merge "MV_{case}.stl";
Merge "AV_{case}.stl";
Merge "PV_{case}.stl";
Merge "TV_{case}.stl";
Coherence Mesh;

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
Physical Surface("RV", 2) = {{2}};
Physical Surface("EPI", 3) = {{3}};
Physical Surface("MV", 4) = {{4}};
Physical Surface("AV", 5) = {{5}};
Physical Surface("PV", 6) = {{6}};
Physical Surface("TV", 7) = {{7}};
Physical Volume("Wall", 8) = {{1}};

Mesh.CharacteristicLengthMax = {char_length_max};
Mesh.CharacteristicLengthMin = {char_length_min};
// Mesh.CharacteristicLengthFromCurvature = 1;
// Mesh.MinimumElementsPerTwoPi = 20;
// Mesh.AngleToleranceFacetOverlap = 0.04;
// Mesh.MeshSizeFromCurvature = 12;

OptimizeMesh "Gmsh";
// OptimizeNetgen 1;
Coherence Mesh;
// Set a threshold for optimizing tetrahedra that have a quality below; default 0.3
Mesh.OptimizeThreshold = 0.5;
Mesh.AngleToleranceFacetOverlap = 0.04;

// 3D mesh algorithm (1: Delaunay, 3: Initial mesh only,
// 4: Frontal, 7: MMG3D, 9: R-tree, 10: HXT); Default 1
Mesh.Algorithm3D = 1;
Coherence;
Mesh.MshFileVersion = 2.2;
"""
)


def create_mesh(outdir: Path, char_length_max: float, char_length_min: float, case: str) -> None:
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
        ["gmsh", geofile.name, "-3", "-o", mshfile.name],
        cwd=outdir,
    )
    logger.debug("Finished running gmsh")
