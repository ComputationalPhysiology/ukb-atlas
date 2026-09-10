# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

`ukb-atlas` turns the UK Biobank biventricular PCA atlas (https://www.cardiacatlas.org/biventricular-modes/)
into STL surfaces, labelled point clouds, and gmsh volume meshes. The Python package lives in
`src/ukb` and installs a single console script, `ukb-atlas` (entry point `ukb.cli:main`).

## Commands

```bash
python -m pip install -e ".[test,dev]"   # dev install (test extra pulls in pyvista + gmsh)
pre-commit install                        # ruff (lint+format) and mypy run on commit

python -m pytest                          # full test suite
python -m pytest tests/test_ukb.py::test_generate_mesh -v          # single test
python -m pytest "tests/test_ukb.py::test_pointcloud[.tsv-both]"   # single parametrized case
python -m pytest --cov=ukb --cov-report term-missing               # as CI runs it

pre-commit run --all                      # lint/format/typecheck everything
mypy                                      # config in pyproject: files = src/ukb, tests

jupyter-book build -W --keep-going .      # docs (needs the `docs` extra; ToC in _toc.yml)
bump-my-version bump patch                # version lives only in pyproject.toml; commits + tags
```

Tests download the real ~30 MB atlas once per session via the `atlas_path` session fixture, so the
first run needs network access. `UKB_CACHE_DIR` (default `~/.ukb`) controls where the atlas is cached.

## Architecture

The pipeline is strictly file-based — each CLI subcommand reads what the previous one wrote into a
shared `folder`, so stages can be run and re-run independently:

```
atlas.py  →  surface.py   →  clip.py      →  mesh.py
(PCA h5)     *_ED.stl        *_clipped.ply    ED.msh / ED_clipped.msh
             pointcloud.py → ED_pointcloud.tsv
```

- **`atlas.py`** — downloads and caches the atlas, then reconstructs coordinates from the PCA
  decomposition in `compute_S`: mean `MU`, or `MU + std*sqrt(LATENT[mode])*COEFF[mode]`, or a full
  score vector. It handles two on-disk layouts: the UKB `.h5` (`COEFF` is `(modes, N)`) and the Burns
  `.mat` (`COEFF` is `(N, modes)`, loaded through `scipy.io.loadmat`, nested under `pca200`) —
  `compute_S` distinguishes them by comparing `COEFF.shape[0]` against `LATENT.size`. The returned
  `Points` NamedTuple splits the flat vector in half: first half ED, second half ES.
- **`surface.py`** — the geometry definition. `connectivity.txt` (11616 triangles, shipped as package
  data) is a fixed triangulation of the atlas template; the `surfaces` dict maps each anatomical
  region (LV, RV, RVFW, EPI, MV, AV, TV, PV) to explicit vertex- and face-index ranges into that
  template. Surfaces are extracted by slicing those ranges and remapping to local node numbering.
  EPI is the exception: it is built by *removing* triangles that touch any valve vertex.
- **`pointcloud.py`** — labels each node by which `surfaces` entry contains it and writes TSV/CSV.
- **`clip.py` / `mesh.py`** — clip cuts the outflow tracts with a pyvista plane (hard-coded default
  origin/normal), merging RV+RVFW first; mesh merges the surfaces in gmsh, builds a volume, and
  tags physical groups. The clipped path adds a `BASE` plane surface closing the cut.

### Index bookkeeping (the main correctness trap)

`generate_points` deletes `atlas.unwanted_nodes = (5630, 5655, 5696, 5729)` from the raw coordinate
array, which shifts every later node index. The ranges in `surfaces` are *original* indices, valid
against `connectivity.txt`. Anything indexing into the array returned by `generate_points` must go
through `Surface.post_deletion_vertex_indices`, which applies the shift. Getting this wrong silently
mislabels regions rather than raising.

### CLI convention

`cli.py` owns only the subparser wiring. Each of `surface`, `clip`, `mesh`, `pointcloud` exposes
`add_parser_arguments(parser)` and `main(**kwargs)`; `dispatch` parses argv into a dict, pops
`command` and `verbose`, and splats the rest into the module's `main`. So **argparse dest names must
match the `main` signature exactly** — adding a flag without the matching keyword raises a TypeError
at runtime. Add a new subcommand by writing that pair and registering it in `get_parser`/`dispatch`.

`surface.main` and `pointcloud.main` both dump their resolved arguments to `folder/parameters.json`
for provenance; keep that in sync when adding options.

### Optional dependencies

`pyvista` and `gmsh` are optional extras, imported lazily inside functions. `clip.main` logs a
warning and returns if pyvista is missing; `mesh.main` falls back to writing a `.geo` file and
shelling out to the `gmsh` binary (`create_mesh_geo`), while the clipped path re-raises. Preserve
this lazy-import pattern — importing either at module scope breaks installs without the extras.

## Conventions

- ruff: line length 100, target py310, rules `E`/`F`. Python floor is 3.10; CI matrix runs 3.10 and
  3.14 on Linux/macOS/Windows, so avoid newer syntax and use `from __future__ import annotations`.
- numpydoc-style docstrings; module-level `logger = logging.getLogger(__name__)` for all user output.
