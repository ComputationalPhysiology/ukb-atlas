from __future__ import annotations
import typing
import json
from pathlib import Path
import logging
import argparse

from . import atlas, surface, mesh


def get_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate surfaces and meshes from UK Biobank atlas."
    )
    parser.add_argument(
        "outdir",
        type=Path,
        help="Directory to save the generated surfaces and meshes.",
    )
    parser.add_argument(
        "-a",
        "--all",
        action="store_true",
        help="Download the PCA atlas derived from all 4,329 subjects from the UK Biobank Study.",
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
        "--mesh",
        action="store_true",
        help="Create gmsh mesh files from the generated surfaces.",
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

    return parser


def main(argv: typing.Sequence[str] | None = None) -> int:
    parser = get_parser()
    args = vars(parser.parse_args(argv))

    logging.basicConfig(level=logging.DEBUG if args["verbose"] else logging.INFO)

    outdir = args["outdir"]
    outdir.mkdir(exist_ok=True, parents=True)

    (outdir / "parameters.json").write_text(
        json.dumps(
            args,
            indent=4,
            default=lambda o: str(o),
        )
    )

    filename = atlas.download_atlas(outdir, args["all"])

    points = atlas.generate_points(filename=filename, mode=args["mode"], std=args["std"])

    for case in ["ED", "ES"]:
        epi = surface.get_epi_mesh(points=getattr(points, case))
        epi.write(str(outdir / f"EPI_{case}.stl"))

        for valve in ["MV", "AV", "TV", "PV"]:
            valve_mesh = surface.get_valve_mesh(surface_name=valve, points=getattr(points, case))
            valve_mesh.write(str(outdir / f"{valve}_{case}.stl"))

        for chamber in ["LV", "RV", "RVFW"]:
            chamber_mesh = surface.get_chamber_mesh(
                surface_name=chamber, points=getattr(points, case)
            )
            chamber_mesh.write(str(outdir / f"{chamber}_{case}.stl"))

        if args["mesh"]:
            mesh.create_mesh(
                outdir=outdir,
                char_length_max=args["char_length_max"],
                char_length_min=args["char_length_min"],
                case=case,
                verbose=args["verbose"],
            )

    return 0
