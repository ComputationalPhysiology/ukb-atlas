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
CI (`.github/workflows/main.yml`) installs only the `test` extra and, on Ubuntu, the system `gmsh`
binary and `libgl1-mesa-dev` (needed by pyvista).

## Architecture

The pipeline is strictly file-based — each CLI subcommand reads what the previous one wrote into a
shared `folder`, so stages can be run and re-run independently:

```
atlas.py  →  surface.py   →  clip.py      →  mesh.py
(PCA h5)     *_ED.stl +      *_clipped.ply    ED.msh / ED_clipped.msh
             surfaces.json
             pointcloud.py → ED_pointcloud.tsv
```

- **`atlas.py`** — downloads the atlas from the `atlas-data` GitHub release of this repo (the
  cardiacatlas.org links are broken), streaming to a `.part` file and checking it against the
  SHA-256 in `ATLAS_FILES` before moving it into the cache — replacing a release asset means
  updating that hash. It then reconstructs coordinates from the PCA decomposition in `compute_S`:
  mean `MU`, or `MU + std*sqrt(LATENT[mode])*COEFF[mode]`, or a full score vector.
  It handles two on-disk layouts: the UKB `.h5` (`COEFF` is `(modes, N)`) and the Burns
  `.mat` (`COEFF` is `(N, modes)`, loaded through `scipy.io.loadmat`, nested under `pca200`) —
  `compute_S` distinguishes them by comparing `COEFF.shape[0]` against `LATENT.size`. The returned
  `Points` NamedTuple splits the flat vector in half: first half ED, second half ES. Both arrays
  have all 5810 template nodes. `--all` (the all-subjects UKB atlas) deliberately raises
  `NotImplementedError` (`atlas.ALL_NOT_SUPPORTED`): it is a 5352-node subset of the template with
  the aortic/pulmonary outflow tracts removed, and supporting it is not planned.
- **`template.py`** — the geometry definition. The triangulation and per-triangle region labels
  come from the biv-me template files vendored verbatim in `src/ukb/data/biv-me/` (Apache-2.0,
  provenance in the README there; excluded from pre-commit so they stay byte-identical).
  `load_template()` (cached) validates the files and returns a `Template`: `faces`, `regions`
  (region name → face rows; `LV_ENDO, RV_SEPTUM, RV_FREEWALL, LV_EPI, RV_EPI`, valve rims
  `MV/AV/TV/PV`, valve caps `*_CAP` fanned to the valve centre nodes, and `SEPTAL_BRIDGE` joining
  the RV insertion line to the LV/RV epicardial seam), plus `rings`, `centres`, `insertion`,
  `epi_seam`. `extract(points, regions)` returns one compacted triangle mesh.
- **`surface.py`** — a *recipe* (`Recipe(surfaces, volumes)` in `RECIPES`: `biv`, `biv-closed`,
  `lv`, `lv-closed`, selected with `surf --geometry`) maps each mesh surface name to template
  regions and each volume name to the surfaces enclosing it (closed variants add valve caps and
  `LV_CAVITY`/`RV_CAVITY`). `surf` writes one STL per region (`{REGION}_{case}.stl`) and a `surfaces.json` manifest
  mapping surface name → files per case, plus the volumes; `read_manifest` returns
  `(files, volumes)` and is how later stages find them. Regions are
  kept in separate files on purpose: gmsh fails to mesh the volume when the RV septum and free wall
  are one surface. New geometries (LV-only, closed valves) should be new recipes.
- **`pointcloud.py`** — labels every node by template region with the fixed integer mapping
  `LABELS` (first entry wins for shared nodes) and writes TSV/CSV.
- **`clip.py` / `mesh.py`** — clip merges each surface's files, cuts the outflow tracts with a
  pyvista plane (hard-coded default origin/normal); mesh merges the manifest's files in gmsh, builds
  one gmsh volume per manifest volume (conforming where they share surfaces), and names
  physical groups after the manifest. `clip` only supports the biv geometries. The
  clipped path adds a `BASE` plane surface closing the cut. Mesh paths always `gmsh.finalize()` —
  a leaked gmsh session corrupts later meshes in the same process (e.g. in tests).

### Node numbering

All indices are raw atlas node indices (0–5809); nothing is deleted or shifted. The four valve
centres (MV 5630, AV 5655, TV 5696, PV 5729) are only used by the cap regions.

### CLI convention

Subcommand names differ from module names: `surf` → `surface.py`, `points` → `pointcloud.py`
(`clip` and `mesh` match).

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

- ruff: line length 100, target py311, rules `E`/`F`. Python floor is 3.11; use
  `from __future__ import annotations`.
- numpydoc-style docstrings; module-level `logger = logging.getLogger(__name__)` for all user output.
