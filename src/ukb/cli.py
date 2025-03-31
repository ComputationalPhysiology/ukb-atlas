from __future__ import annotations
from typing import Sequence

import logging
import argparse

from . import surface, mesh, clip


def get_parser() -> argparse.ArgumentParser:
    description = (
        "UKB-atlas\n\n"
        "This is a command line interface for extracting "
        "surfaces and generating Bi-ventricular meshes from "
        "the UK Biobank atlas: https://www.cardiacatlas.org/biventricular-modes/"
    )

    parser = argparse.ArgumentParser(
        description=description, formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    subparsers = parser.add_subparsers(dest="command")

    surface_parser = subparsers.add_parser(
        "surf",
        help="Extract surfaces from the atlas",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    surface.add_parser_arguments(surface_parser)
    clip_parser = subparsers.add_parser(
        "clip", help="Clip the surfaces", formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    clip.add_parser_arguments(clip_parser)
    mesh_parser = subparsers.add_parser(
        "mesh",
        help="Generate mesh from the surfaces",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    mesh.add_parser_arguments(mesh_parser)

    return parser


def _disable_loggers():
    for libname in ["matplotlib"]:
        logging.getLogger(libname).setLevel(logging.WARNING)


def dispatch(parser: argparse.ArgumentParser, argv: Sequence[str] | None = None) -> int:
    args = vars(parser.parse_args(argv))
    logging.basicConfig(level=logging.DEBUG if args.pop("verbose") else logging.INFO)
    _disable_loggers()

    command = args.pop("command")
    if command is None:
        parser.error("Please specify a command")

    if command == "surf":
        surface.main(**args)
    elif command == "clip":
        clip.main(**args)
    elif command == "mesh":
        mesh.main(**args)
    else:
        parser.error(f"Unknown command {command}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = get_parser()
    return dispatch(parser, argv)


#
# parser = get_parser()
# args = vars(parser.parse_args(argv))

# logging.basicConfig(level=logging.DEBUG if args["verbose"] else logging.INFO)

#     if args["mesh"]:
#         mesh.create_mesh(
#             outdir=outdir,
#             char_length_max=args["char_length_max"],
#             char_length_min=args["char_length_min"],
#             name=case,
#             verbose=args["verbose"],
#         )

# return 0
