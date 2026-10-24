import json
from unittest.mock import patch

import pytest
import h5py
import numpy as np

import ukb.cli
import ukb.surface
from ukb import pointcloud, template
from ukb import atlas


@pytest.fixture(scope="session")
def atlas_path(tmp_path_factory):
    """Fixture to download the atlas once per session."""
    # Create a persistent directory for the session
    cache_dir = tmp_path_factory.mktemp("atlas_cache")
    # Download the healthy reference atlas (all=False)
    path = atlas.download_atlas(outdir=cache_dir, all=False)
    return path


def test_generate_points_mean(atlas_path):
    """Test that generating points with mode=-1 returns the expected mean shape."""
    points = atlas.generate_points(atlas_path, mode=-1)

    assert isinstance(points, atlas.Points)
    # All template nodes are kept, including the valve centres
    assert points.ED.shape == (5810, 3)
    assert points.ES.shape == (5810, 3)


def test_generate_points_with_mode(atlas_path):
    """Test that perturbing a specific mode changes the points from the mean."""
    mean_points = atlas.generate_points(atlas_path, mode=-1)
    mode_points = atlas.generate_points(atlas_path, mode=0, std=2.0)

    assert not np.allclose(mean_points.ED, mode_points.ED)
    assert mode_points.ED.shape == mean_points.ED.shape


def test_generate_points_with_scores(atlas_path):
    """Test generation using explicit PCA scores."""
    num_scores = 25
    np.random.seed(0)  # For reproducibility
    scores = np.random.normal(0, 1, num_scores)
    N = 34860  # 5810 nodes x 3 coordinates x 2 cases

    with patch("scipy.io.loadmat") as mock_loadmat:
        # Mock the loadmat to return a structure with the expected keys
        hdf = {
            "MU": np.zeros((1, N)),
            "COEFF": np.random.rand(N, num_scores),
            "LATENT": np.random.rand(num_scores, 1),
        }
        mock_loadmat.return_value = {"pca200": np.array([[hdf]])}
        points = atlas.generate_points_burns(atlas_path, score=scores)

    assert points.ED.shape == (5810, 3)
    assert points.ES.shape == (5810, 3)


def test_compute_S_errors(atlas_path):
    """Test that compute_S raises appropriate errors for invalid inputs."""
    with h5py.File(atlas_path, "r") as hdf:
        # Test invalid mode
        with pytest.raises(ValueError, match="Mode 999 is out of bounds"):
            atlas.compute_S(hdf, mode=999)


@pytest.mark.parametrize("all", [False, True])
def test_download_atlas_verifies_checksum(tmp_path, all):
    """Test that a download with the expected checksum is moved into place."""
    import hashlib

    content = b"atlas"
    name, _ = atlas.ATLAS_FILES[all]
    sha256 = hashlib.sha256(content).hexdigest()
    with (
        patch("requests.get") as mock_get,
        patch.dict(atlas.ATLAS_FILES, {all: (name, sha256)}),
    ):
        mock_get.return_value.__enter__.return_value.iter_content.return_value = [content]
        path = atlas.download_atlas(tmp_path, all=all)

    assert path == tmp_path / name
    assert path.read_bytes() == content
    assert list(tmp_path.iterdir()) == [path]


def test_download_atlas_checksum_mismatch(tmp_path):
    """Test that a corrupted download raises and leaves nothing in the cache."""
    with patch("requests.get") as mock_get:
        mock_get.return_value.__enter__.return_value.iter_content.return_value = [b"corrupted"]
        with pytest.raises(RuntimeError, match="Checksum mismatch"):
            atlas.download_atlas(tmp_path, all=False)

    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("case", ["ED", "ES", "both"])
def test_generate_surfaces_mean_healthy(case, tmp_path, atlas_path):
    ukb.cli.main(["surf", str(tmp_path), "--case", case, "--cache-dir", str(atlas_path.parent)])
    assert (tmp_path / "parameters.json").exists()

    if case == "both":
        cases = ["ED", "ES"]
        non_cases = []
    else:
        cases = [case]
        non_cases = ["ED", "ES"]
        non_cases.remove(case)

    manifest = json.loads((tmp_path / ukb.surface.MANIFEST).read_text())
    assert manifest["geometry"] == "biv"
    assert set(manifest["cases"]) == set(cases)
    for case_ in cases:
        assert set(manifest["cases"][case_]) == set(ukb.surface.BIV)

    for name in ukb.surface.BIV:
        for case_ in cases:
            path = tmp_path / f"{name}_{case_}.stl"
            assert path.exists()
        for case_ in non_cases:
            path = tmp_path / f"{name}_{case_}.stl"
            assert not path.exists()


def test_generate_mesh(tmp_path, atlas_path):
    ukb.cli.main(["surf", str(tmp_path), "--case", "ED", "--cache-dir", str(atlas_path.parent)])
    assert not (tmp_path / "ED.msh").exists()
    ukb.cli.main(["mesh", str(tmp_path), "--case", "ED"])
    assert (tmp_path / "ED.msh").exists()


def test_clipped_surfaces_are_triangulated(tmp_path, atlas_path):
    """Clipped surfaces must contain only triangles.

    VTK >= 9.7 emits quads along the cut plane, and gmsh's PLY reader only
    ever reads three vertex indices per face -- it desyncs on binary files
    with mixed face sizes and silently drops the fourth vertex in ASCII.
    """
    meshio = pytest.importorskip("meshio")
    ukb.cli.main(["surf", str(tmp_path), "--case", "ED", "--cache-dir", str(atlas_path.parent)])
    ukb.cli.main(["clip", str(tmp_path), "--case", "ED", "--smooth"])

    for name in ["lv_clipped.ply", "rv_clipped.ply", "epi_clipped.ply"]:
        mesh = meshio.read(tmp_path / name)
        cell_types = {cell.type for cell in mesh.cells}
        assert cell_types == {"triangle"}, f"{name} contains non-triangles: {cell_types}"


def test_clip_mesh(tmp_path, atlas_path):
    ukb.cli.main(["surf", str(tmp_path), "--case", "ED", "--cache-dir", str(atlas_path.parent)])
    assert not (tmp_path / "lv_clipped.ply").exists()
    ukb.cli.main(["clip", str(tmp_path), "--case", "ED", "--smooth"])
    assert (tmp_path / "lv_clipped.ply").exists()
    assert (tmp_path / "rv_clipped.ply").exists()
    assert (tmp_path / "epi_clipped.ply").exists()
    assert not (tmp_path / "ED_clipped.msh").exists()
    ukb.cli.main(["mesh", str(tmp_path), "--case", "ED", "--clipped"])
    assert (tmp_path / "ED_clipped.msh").exists()


def test_generate_surfaces_non_mean_healthy(tmp_path, atlas_path):
    mode = 1
    std = 0.3
    ukb.cli.main(
        [
            "surf",
            str(tmp_path),
            "--mode",
            str(mode),
            "--std",
            str(std),
            "--case",
            "both",
            "--cache-dir",
            str(atlas_path.parent),
        ]
    )

    assert (tmp_path / "parameters.json").exists()
    params = json.loads((tmp_path / "parameters.json").read_text())
    assert params["mode"] == mode
    assert params["std"] == std

    for name in ukb.surface.BIV:
        for case in ["ED", "ES"]:
            path = tmp_path / f"{name}_{case}.stl"
            assert path.exists()


@pytest.mark.parametrize("case", ["ED", "ES", "both"])
@pytest.mark.parametrize("suffix", [".tsv", ".csv"])
def test_pointcloud(tmp_path, atlas_path, suffix, case):
    ukb.cli.main(
        [
            "points",
            str(tmp_path),
            "--mode",
            "-1",
            "--std",
            "0.0",
            "--case",
            case,
            "--cache-dir",
            str(atlas_path.parent),
            "--suffix",
            suffix,
        ]
    )

    cases = ["ED", "ES"] if case == "both" else [case]
    for c in cases:
        path = tmp_path / f"{c}_pointcloud{suffix}"
        assert path.exists()
        delimiter = "\t" if suffix == ".tsv" else ","
        header, *rows = [line.split(delimiter) for line in path.read_text().splitlines()]
        assert header == ["x", "y", "z", "label", "region"]
        assert len(rows) == 5810
        assert {row[4] for row in rows} <= set(pointcloud.LABELS)


def test_surf_ed_then_es_keeps_both_cases(tmp_path, atlas_path):
    for case in ["ED", "ES"]:
        ukb.cli.main(["surf", str(tmp_path), "--case", case, "--cache-dir", str(atlas_path.parent)])
    manifest = json.loads((tmp_path / ukb.surface.MANIFEST).read_text())
    assert set(manifest["cases"]) == {"ED", "ES"}
    assert ukb.surface.read_manifest(tmp_path, "ES")["LV_ENDO"] == tmp_path / "LV_ENDO_ES.stl"


def test_read_manifest_missing(tmp_path):
    with pytest.raises(FileNotFoundError, match="surf"):
        ukb.surface.read_manifest(tmp_path, "ED")


def test_custom_points_wrong_shape(tmp_path):
    points = atlas.Points(ED=np.zeros((5806, 3)), ES=np.zeros((5806, 3)))
    with pytest.raises(ValueError, match="5810"):
        ukb.surface.main(tmp_path, custom_points=points)


def test_get_point_cloud_labels():
    t = template.load_template()
    points = np.random.default_rng(0).random((5810, 3))
    pts, labels, names = pointcloud.get_point_cloud(points)
    assert np.array_equal(pts, points)
    assert set(names.values()) == set(pointcloud.LABELS)
    assert {names[label] for label in labels} == set(pointcloud.LABELS)
    for valve in template.VALVES:
        assert all(names[label] == valve for label in labels[t.rings[valve]])
        assert names[labels[t.centres[valve]]] == f"{valve}_CAP"
    assert all(names[label] == "RV_SEPTUM" for label in labels[t.insertion])
    assert all(names[label] == "LV_EPI" for label in labels[t.epi_seam])
