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
