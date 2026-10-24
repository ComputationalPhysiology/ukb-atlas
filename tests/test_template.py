from __future__ import annotations

import shutil
from collections import Counter
from pathlib import Path

import numpy as np
import pytest

from ukb import template

DATA_DIR = Path(template.__file__).parent / "data" / "biv-me"
FILES = ("ETIndicesSorted.txt", "ETIndicesMaterials.txt", "thru_wall_et_indices.txt")


def edge_counts(faces: np.ndarray) -> Counter:
    edges = np.sort(faces[:, [0, 1, 1, 2, 2, 0]].reshape(-1, 2), axis=1)
    return Counter(map(tuple, edges))


def copy_template(tmp_path: Path) -> list[Path]:
    paths = []
    for name in FILES:
        shutil.copy(DATA_DIR / name, tmp_path / name)
        paths.append(tmp_path / name)
    return paths


def test_template_sizes():
    t = template.load_template()
    assert t.num_nodes == 5810
    assert len(t.faces) == 11760 + 160
    assert set(t.regions) == set(template.REGIONS)
    assert {v: len(r) for v, r in t.rings.items()} == {"MV": 48, "AV": 24, "TV": 40, "PV": 32}
    assert t.centres == {"MV": 5630, "AV": 5655, "TV": 5696, "PV": 5729}
    assert len(t.insertion) == 80
    assert len(t.epi_seam) == 80


def test_rings_are_ordered_loops():
    t = template.load_template()
    for valve, ring in t.rings.items():
        cap = t.faces[t.regions[f"{valve}_CAP"]]
        edges = set(edge_counts(cap))
        for a, b in zip(ring, np.roll(ring, -1)):
            assert tuple(sorted((a, b))) in edges


@pytest.mark.parametrize(
    "regions, n_faces",
    [
        (["LV_ENDO"], 3072),
        (["RV_SEPTUM", "RV_FREEWALL"], 3680),
        (["LV_EPI", "RV_EPI"], 4576),
        (["MV"], 96),
        (["AV"], 48),
        (["TV"], 80),
        (["PV"], 64),
        (["MV_CAP"], 48),
        (["SEPTAL_BRIDGE"], 160),
    ],
)
def test_extract_face_counts(regions, n_faces):
    points = np.random.default_rng(0).random((5810, 3))
    mesh = template.extract(points, regions)
    cells = mesh.cells[0].data
    assert cells.shape == (n_faces, 3)
    assert cells.max() < len(mesh.points)
    assert len(np.unique(cells)) == len(mesh.points)


def test_extract_keeps_coordinates():
    points = np.random.default_rng(1).random((5810, 3))
    t = template.load_template()
    mesh = template.extract(points, ["AV"])
    faces = t.faces[t.regions["AV"]]
    assert np.allclose(mesh.points[mesh.cells[0].data], points[faces])


@pytest.mark.parametrize(
    "regions",
    [
        ["LV_ENDO", "MV_CAP", "AV_CAP"],
        ["RV_SEPTUM", "RV_FREEWALL", "TV_CAP", "PV_CAP"],
    ],
)
def test_closed_cavities(regions):
    t = template.load_template()
    faces = t.faces[np.concatenate([t.regions[r] for r in regions])]
    assert set(edge_counts(faces).values()) == {2}


def test_matches_legacy_connectivity():
    t = template.load_template()
    legacy = np.loadtxt(Path(template.__file__).parent / "connectivity.txt", dtype=int)
    raw = np.setdiff1d(np.arange(5810), [5630, 5655, 5696, 5729])[legacy]
    caps = np.concatenate([t.regions[f"{v}_CAP"] for v in template.VALVES])
    bridge = t.regions["SEPTAL_BRIDGE"]
    keep = np.setdiff1d(np.arange(len(t.faces)), np.concatenate([caps, bridge]))
    ours = t.faces[keep]
    assert {tuple(sorted(f)) for f in ours} == {tuple(sorted(f)) for f in raw}
    # Same orientation: each legacy triangle is a cyclic rotation of ours
    rotations = {tuple(np.roll(f, i)) for f in ours for i in range(3)}
    assert all(tuple(f) in rotations for f in raw)


def test_corrupt_template_raises(tmp_path):
    sorted_file, materials_file, bridge_file = copy_template(tmp_path)
    # Replace the first triangle by a copy of the second one
    lines = sorted_file.read_text().splitlines()
    sorted_file.write_text("\n".join([lines[1]] + lines[1:]) + "\n")
    with pytest.raises(ValueError, match="manifold"):
        template.build_template(sorted_file, materials_file, bridge_file)


def test_unknown_material_raises(tmp_path):
    sorted_file, materials_file, bridge_file = copy_template(tmp_path)
    materials_file.write_text(materials_file.read_text().replace("RV_SEPTUM", "FOO", 1))
    with pytest.raises(ValueError, match="FOO"):
        template.build_template(sorted_file, materials_file, bridge_file)


def test_extract_unknown_region_raises():
    with pytest.raises(ValueError, match="FOO"):
        template.extract(np.zeros((5810, 3)), ["FOO"])
