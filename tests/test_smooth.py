from __future__ import annotations

import numpy as np
import pytest

import ukb.cli
from ukb import atlas, smooth, template


@pytest.fixture(scope="module")
def points(atlas_path):
    return atlas.generate_points(atlas_path, mode=-1, std=1.5).ED


def enclosed_volume(points: np.ndarray, faces: np.ndarray) -> float:
    p = points[faces]
    return abs(np.einsum("ij,ij->i", p[:, 0], np.cross(p[:, 1], p[:, 2])).sum()) / 6


def lv_cavity_volume(points: np.ndarray, tpl: template.Template) -> float:
    lv = template.extract(points, ["LV_ENDO", "MV_CAP", "AV_CAP"], template=tpl)
    return enclosed_volume(lv.points, lv.cells[0].data)


def test_control_faces():
    interior = smooth.load_control_faces().interior
    assert interior.shape == (smooth.NUM_CONTROL_FACES, 3, 3)
    assert len(np.unique(interior)) == interior.size


def test_face_grids_cover_the_wall(points):
    tpl = template.load_template()
    grids = smooth.face_grids(points)
    assert grids.shape == (smooth.NUM_CONTROL_FACES, 5, 5)
    face, _ = smooth.triangle_faces(tpl, grids)
    for region in ["LV_ENDO", "RV_SEPTUM", "RV_FREEWALL", "LV_EPI", "RV_EPI"]:
        assert (face[tpl.regions[region]] >= 0).all()
    for region in ["MV_CAP", "SEPTAL_BRIDGE"]:
        assert (face[tpl.regions[region]] < 0).all()


def test_splines_interpolate_the_nodes(points):
    grids = smooth.face_grids(points)
    i, j = np.meshgrid(np.arange(5), np.arange(5), indexing="ij")
    uv = np.stack([i.ravel(), j.ravel()], axis=1) / 4
    for grid in grids:
        values = smooth.evaluate(np.repeat(points[grid][None], len(uv), axis=0), uv)
        assert np.allclose(values, points[grid.ravel()])


def test_refine_keeps_the_template(points):
    tpl = template.load_template()
    refined_points, refined = smooth.refine(points, 2)
    assert np.array_equal(refined_points[: template.NUM_NODES], points)
    assert len(refined.faces) == 16 * len(tpl.faces)
    assert refined.num_nodes == len(refined_points)
    for name, rows in tpl.regions.items():
        assert len(refined.regions[name]) == 16 * len(rows)
    # Without the caps the refined template is still one closed surface
    wall = np.concatenate([refined.regions[r] for r in template.REGIONS[:9]])
    _, counts = template.edges_with_counts(refined.faces[wall])
    assert np.all(counts == 2)


def test_refine_converges(points):
    volumes = [lv_cavity_volume(*smooth.refine(points, level)) for level in range(4)]
    changes = np.diff(volumes)
    # The faceted surface is inside the convex parts of the smooth one
    assert np.all(changes > 0)
    # Each refinement brings the surface about four times closer
    assert np.all(changes[1:] < 0.35 * changes[:-1])


def test_refine_zero_and_negative(points):
    tpl = template.load_template()
    refined_points, refined = smooth.refine(points, 0)
    assert refined_points is points and refined is tpl
    with pytest.raises(ValueError, match="non-negative"):
        smooth.refine(points, -1)


def test_surf_refine(tmp_path, atlas_path):
    cache = str(atlas_path.parent)
    ukb.cli.main(["surf", str(tmp_path / "0"), "-g", "lv-closed", "--cache-dir", cache])
    ukb.cli.main(
        ["surf", str(tmp_path / "1"), "-g", "lv-closed", "--cache-dir", cache, "--refine", "1"]
    )
    meshio = pytest.importorskip("meshio")
    coarse = meshio.read(tmp_path / "0" / "LV_ENDO_ED.stl")
    fine = meshio.read(tmp_path / "1" / "LV_ENDO_ED.stl")
    assert len(fine.cells[0].data) == 4 * len(coarse.cells[0].data)
    ukb.cli.main(["mesh", str(tmp_path / "1"), "--order", "2"])
    assert (tmp_path / "1" / "ED.msh").exists()
