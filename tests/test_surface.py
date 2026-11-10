from __future__ import annotations

import json

import numpy as np
import pytest

from ukb import surface, template


@pytest.mark.parametrize("name", list(surface.RECIPES))
def test_recipe_regions_known(name):
    for regions in surface.RECIPES[name].surfaces.values():
        assert set(regions) <= set(template.REGIONS)


@pytest.mark.parametrize("name", list(surface.RECIPES))
def test_recipe_volume_surfaces_known(name):
    recipe = surface.RECIPES[name]
    for surfaces in recipe.volumes.values():
        assert set(surfaces) <= set(recipe.surfaces)


@pytest.mark.parametrize(
    "name, volume", [(n, v) for n, r in surface.RECIPES.items() for v in r.volumes]
)
def test_recipe_volumes_closed(name, volume):
    recipe = surface.RECIPES[name]
    t = template.load_template()
    regions = [r for s in recipe.volumes[volume] for r in recipe.surfaces[s]]
    faces = t.faces[np.concatenate([t.regions[r] for r in regions])]
    _, counts = template.edges_with_counts(faces)
    assert np.all(counts == 2)


def test_recipe_names():
    assert set(surface.RECIPES) == {"biv", "biv-closed", "lv", "lv-closed"}
    assert set(surface.RECIPES["biv"].volumes) == {"Wall"}
    assert set(surface.RECIPES["lv"].volumes) == {"Wall"}
    assert set(surface.RECIPES["biv-closed"].volumes) == {"Wall", "LV_CAVITY", "RV_CAVITY"}
    assert set(surface.RECIPES["lv-closed"].volumes) == {"Wall", "LV_CAVITY"}
    assert surface.RECIPES["biv-closed"].volumes["Wall"] == surface.RECIPES["biv"].volumes["Wall"]
    assert surface.RECIPES["lv-closed"].volumes["Wall"] == surface.RECIPES["lv"].volumes["Wall"]
    assert set(surface.RECIPES["lv"].surfaces) == {
        "LV_ENDO",
        "EPI",
        "RV_SEPTUM",
        "SEPTAL_BRIDGE",
        "MV",
        "AV",
    }
    assert surface.RECIPES["lv"].surfaces["EPI"] == ("LV_EPI",)


def test_manifest_geometry_change_replaces_cases(tmp_path):
    biv, lv = surface.RECIPES["biv"], surface.RECIPES["lv"]
    surface.write_manifest(tmp_path, "biv", biv.volumes, {"ED": {"LV_ENDO": ["LV_ENDO_ED.stl"]}})
    surface.write_manifest(tmp_path, "lv", lv.volumes, {"ES": {"LV_ENDO": ["LV_ENDO_ES.stl"]}})
    manifest = json.loads((tmp_path / surface.MANIFEST).read_text())
    assert manifest["geometry"] == "lv"
    assert set(manifest["cases"]) == {"ES"}
    files, volumes = surface.read_manifest(tmp_path, "ES")
    assert files == {"LV_ENDO": [tmp_path / "LV_ENDO_ES.stl"]}
    assert volumes == {name: list(s) for name, s in lv.volumes.items()}


def test_read_manifest_without_volumes(tmp_path):
    # Manifests written by v1.5.0 have no "volumes"
    manifest = {"geometry": "biv", "cases": {"ED": {"LV_ENDO": ["LV_ENDO_ED.stl"]}}}
    (tmp_path / surface.MANIFEST).write_text(json.dumps(manifest))
    _, volumes = surface.read_manifest(tmp_path, "ED")
    assert volumes == {name: list(s) for name, s in surface.BIV.volumes.items()}


@pytest.mark.parametrize("refine", [0, 1])
def test_surf_writes_landmarks(tmp_path, atlas_path, refine):
    import json

    import ukb.cli

    ukb.cli.main(
        [
            "surf",
            str(tmp_path),
            "--case",
            "ED",
            "--cache-dir",
            str(atlas_path.parent),
            "--refine",
            str(refine),
        ]
    )
    path = tmp_path / "landmarks_ED.json"
    lm = json.loads(path.read_text())
    assert set(lm) == {"insertion", "rv_freewall", "rv_septum", "valves"}
    assert len(lm["insertion"]) == 80
    manifest = json.loads((tmp_path / surface.MANIFEST).read_text())
    assert manifest["landmarks"] == {"ED": "landmarks_ED.json"}
    # The landmarks lie on the written surfaces: every insertion point is a node of the RV septum
    import meshio

    septum = meshio.read(tmp_path / "RV_SEPTUM_ED.stl").points
    d = np.linalg.norm(septum[None, :, :] - np.array(lm["insertion"])[:, None, :], axis=2).min(
        axis=1
    )
    assert d.max() < 1e-4


def test_surf_lv_writes_no_landmarks(tmp_path, atlas_path):
    import ukb.cli

    ukb.cli.main(
        [
            "surf",
            str(tmp_path),
            "--case",
            "ED",
            "--cache-dir",
            str(atlas_path.parent),
            "--geometry",
            "lv",
        ]
    )
    assert not (tmp_path / "landmarks_ED.json").exists()
