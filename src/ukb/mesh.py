from textwrap import dedent
from pathlib import Path
from typing import Callable, Literal
from argparse import ArgumentParser
import shutil
import subprocess
import logging

from . import surface

logger = logging.getLogger(__name__)

# gmsh's 3D Delaunay boundary recovery fails sporadically ("PLC Error"), also for
# input it meshes fine on another attempt, so failed meshing is retried
MAX_ATTEMPTS = 3


def with_retries(create: Callable[[], None]) -> None:
    """Call ``create`` until it succeeds, at most ``MAX_ATTEMPTS`` times."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            create()
            return
        except Exception as e:
            if attempt == MAX_ATTEMPTS:
                raise
            logger.warning(f"Meshing failed ({e}), retrying ({attempt}/{MAX_ATTEMPTS})")


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


geo_template = dedent(
    """
 // merge STL files - each one will create a new surface:
{merges}
Coherence Mesh;

Mesh.Optimize = 1;
Mesh.OptimizeNetgen = {netgen};
Mesh.Smoothing = 1;

CreateTopology;

// Create geometry for all curves and surfaces:
CreateGeometry;

// Define the volumes. Since we did not create any new surface, the surface
// tags are the merge positions of the files
{volumes}

{physical}

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


def geo_script(
    files: dict[str, list[Path]],
    volumes: dict[str, list[str]],
    char_length_max: float,
    char_length_min: float,
    netgen: bool = True,
) -> str:
    """Return a gmsh .geo script that meshes the volumes enclosed by ``files``.

    Each merged file becomes one surface whose tag is its (1-based) merge
    position, which is used for the volumes and the physical groups. The
    Netgen optimizer is only enabled if ``netgen`` is true.
    """
    merges: list[str] = []
    tags: dict[str, list[int]] = {}
    for name, paths in files.items():
        tags[name] = list(range(len(merges) + 1, len(merges) + len(paths) + 1))
        merges.extend(f'Merge "{path.name}";' for path in paths)

    def join(values) -> str:
        return ", ".join(map(str, values))

    geo_volumes: list[str] = []
    physical: list[str] = []
    for i, surfaces in enumerate(volumes.values(), start=1):
        geo_volumes.append(f"Surface Loop({i}) = {{{join(t for s in surfaces for t in tags[s])}}};")
        geo_volumes.append(f"Volume({i}) = {{{i}}};")
    for name, surface_tags in tags.items():
        physical.append(
            f'Physical Surface("{name}", {len(physical) + 1}) = {{{join(surface_tags)}}};'
        )
    for i, name in enumerate(volumes, start=1):
        physical.append(f'Physical Volume("{name}", {len(physical) + 1}) = {{{i}}};')
    return geo_template.format(
        merges="\n".join(merges),
        volumes="\n".join(geo_volumes),
        physical="\n".join(physical),
        char_length_max=char_length_max,
        char_length_min=char_length_min,
        netgen=int(netgen),
    )


def find_gmsh() -> tuple[str, str] | None:
    """Return the path of a working gmsh binary and the output of ``gmsh -info``.

    Returns None if there is no gmsh on the PATH or it cannot be run (e.g. the
    launcher script installed by the gmsh wheel on Windows).
    """
    executable = shutil.which("gmsh")
    if executable is None:
        return None
    try:
        result = subprocess.run([executable, "-info"], capture_output=True, text=True)
    except OSError:
        return None
    return executable, result.stdout + result.stderr


def create_mesh_geo(
    folder: Path,
    char_length_max: float,
    char_length_min: float,
    case: Literal["ED", "ES", "both"] = "ED",
) -> None:
    """Create a mesh by writing a .geo file and running the gmsh binary.

    Parameters
    ----------
    folder : Path
        Folder with the surfaces generated by ``ukb-atlas surf``
    char_length_max : float
        Maximum characteristic length of the mesh elements
    char_length_min : float
        Minimum characteristic length of the mesh elements
    case : str
        Case name, by default "ED"
    """
    files, volumes = surface.read_manifest(folder, case)
    geofile = folder / f"{case}.geo"
    logger.debug(f"Writing {geofile}")
    gmsh_binary = find_gmsh()
    if gmsh_binary is None:
        raise RuntimeError(
            "Could not run gmsh. Install the gmsh Python API (pip install gmsh) or the gmsh binary."
        )
    executable, info = gmsh_binary
    # Not all gmsh builds (e.g. some Linux distributions) include Netgen
    netgen = "Netgen" in info
    if not netgen:
        logger.warning("gmsh is built without Netgen, skipping Netgen optimization")
    geofile.write_text(geo_script(files, volumes, char_length_max, char_length_min, netgen))

    mshfile = folder / f"{case}.msh"
    logger.debug(f"Create mesh {mshfile} using gmsh")

    def create() -> None:
        result = subprocess.run(
            [executable, geofile.name, "-2", "-3", "-o", mshfile.name],
            cwd=folder,
            capture_output=True,
            text=True,
        )
        logger.debug(result.stdout)
        if result.returncode != 0:
            raise RuntimeError(f"gmsh failed to create {mshfile}:\n{result.stdout}{result.stderr}")

    with_retries(create)
    logger.info(f"Created mesh {mshfile}")


def set_mesh_options(gmsh, char_length_max: float, char_length_min: float) -> None:
    gmsh.option.setNumber("Mesh.Optimize", 1)
    # Not all gmsh builds (e.g. some Linux distributions) include Netgen
    if "Netgen" in gmsh.option.getString("General.BuildOptions"):
        gmsh.option.setNumber("Mesh.OptimizeNetgen", 1)
    else:
        logger.warning("gmsh is built without Netgen, skipping Netgen optimization")
    gmsh.option.setNumber("Mesh.Smoothing", 1)
    gmsh.option.setNumber("Mesh.CharacteristicLengthMax", char_length_max)
    gmsh.option.setNumber("Mesh.CharacteristicLengthMin", char_length_min)
    gmsh.option.setNumber("Mesh.Algorithm3D", 1)


def main(
    folder: Path,
    case: Literal["ED", "ES", "both"] = "ED",
    char_length_max: float = 5.0,
    char_length_min: float = 5.0,
    verbose: bool = False,
    clipped: bool = False,
) -> None:
    """Create a gmsh mesh file from the surface mesh representation.

    The surfaces listed for ``case`` in the manifest written by ``ukb-atlas surf``
    are merged, and each becomes a physical surface with the same name. The
    enclosed volume is the physical volume "Wall".

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
    if case == "both":
        if clipped:
            raise ValueError("The clipped surfaces are for a single case; use --case ED or ES")
        for c in ("ED", "ES"):
            main(folder, c, char_length_max, char_length_min, verbose, clipped)
        return
    if clipped:
        return create_clipped_mesh(
            folder=folder,
            case=case,
            char_length_max=char_length_max,
            char_length_min=char_length_min,
        )
    files, volumes = surface.read_manifest(folder, case)
    logger.info(f"Creating mesh for {case} with {char_length_max=}, {char_length_min=}")
    try:
        import gmsh

    except ImportError:
        logger.warning("gmsh python API not installed. Try subprocess.")
        return create_mesh_geo(folder, char_length_max, char_length_min, case)

    def create() -> None:
        gmsh.initialize()
        try:
            if not verbose:
                gmsh.option.setNumber("General.Verbosity", 0)

            # Merge all surfaces, recording which surface entities each file created
            tags: dict[str, list[int]] = {}
            for name, paths in files.items():
                before = set(gmsh.model.getEntities(2))
                for path in paths:
                    gmsh.merge(str(path))
                tags[name] = sorted(tag for _, tag in set(gmsh.model.getEntities(2)) - before)

            num_surfaces = len(gmsh.model.getEntities(2))
            gmsh.model.mesh.removeDuplicateNodes()
            gmsh.model.mesh.create_topology()
            gmsh.model.mesh.create_geometry()
            surfaces = gmsh.model.getEntities(2)
            if len(surfaces) != num_surfaces:
                raise RuntimeError(
                    "gmsh changed the surfaces while merging; physical groups would be wrong"
                )

            # One volume per declared volume; volumes sharing a surface (e.g. the wall
            # and a cavity sharing the endocardium) give a conforming mesh
            volume_tags = {}
            for name, volume_surfaces in volumes.items():
                loop = gmsh.model.geo.addSurfaceLoop([t for s in volume_surfaces for t in tags[s]])
                volume_tags[name] = gmsh.model.geo.addVolume([loop])
            gmsh.model.geo.synchronize()

            for name, surface_tags in tags.items():
                p = gmsh.model.addPhysicalGroup(2, surface_tags)
                gmsh.model.setPhysicalName(2, p, name)

            for name, volume_tag in volume_tags.items():
                p = gmsh.model.addPhysicalGroup(3, [volume_tag])
                gmsh.model.setPhysicalName(3, p, name)

            set_mesh_options(gmsh, char_length_max, char_length_min)
            gmsh.model.geo.synchronize()
            gmsh.model.mesh.generate(3)
            gmsh.write(f"{folder}/{case}.msh")
            logger.info(f"Created mesh {folder}/{case}.msh")
        finally:
            gmsh.finalize()

    with_retries(create)


def create_clipped_mesh(
    folder: Path,
    case: Literal["ED", "ES", "both"] = "ED",
    char_length_max: float = 5.0,
    char_length_min: float = 5.0,
    verbose: bool = False,
) -> None:
    """Create a gmsh mesh from the clipped surfaces written by ``ukb-atlas clip``.

    Parameters
    ----------
    folder : Path
        Path to the output folder
    case : str
        Case name
    char_length_max : float
        Maximum characteristic length of the mesh elements
    char_length_min : float
        Minimum characteristic length of the mesh elements
    verbose : bool, optional
        Print verbose output, by default False
    """
    logger.info(f"Creating clipped mesh for {case} with {char_length_max=}, {char_length_min=}")
    import gmsh

    def create() -> None:
        gmsh.initialize()
        try:
            if not verbose:
                gmsh.option.setNumber("General.Verbosity", 0)

            # Merge all surfaces
            tags: dict[str, list[int]] = {}
            for name, filename in [
                ("LV_ENDO", "lv_clipped.ply"),
                ("RV_ENDO", "rv_clipped.ply"),
                ("EPI", "epi_clipped.ply"),
            ]:
                before = set(gmsh.model.getEntities(2))
                gmsh.merge(f"{folder}/{filename}")
                tags[name] = sorted(tag for _, tag in set(gmsh.model.getEntities(2)) - before)

            gmsh.model.mesh.removeDuplicateNodes()
            gmsh.model.mesh.create_topology()
            gmsh.model.mesh.create_geometry()

            # Close the base with a plane surface bounded by the cut curves
            curves = gmsh.model.getEntities(1)
            base_ring = gmsh.model.geo.addCurveLoop([c[1] for c in curves])
            tags["BASE"] = [gmsh.model.geo.addPlaneSurface([base_ring])]
            gmsh.model.geo.synchronize()

            surfaces = gmsh.model.getEntities(2)
            loop = gmsh.model.geo.addSurfaceLoop([s[1] for s in surfaces])
            vol = gmsh.model.geo.addVolume([loop])
            gmsh.model.geo.synchronize()

            for name, surface_tags in tags.items():
                p = gmsh.model.addPhysicalGroup(2, surface_tags)
                gmsh.model.setPhysicalName(2, p, name)

            p = gmsh.model.addPhysicalGroup(3, [vol])
            gmsh.model.setPhysicalName(3, p, "Wall")

            set_mesh_options(gmsh, char_length_max, char_length_min)
            gmsh.model.geo.synchronize()
            gmsh.model.mesh.generate(3)
            outfile = (folder / f"{case}_clipped").with_suffix(".msh")
            gmsh.write(str(outfile))
            logger.info(f"Created mesh {outfile}")
        finally:
            gmsh.finalize()

    with_retries(create)
