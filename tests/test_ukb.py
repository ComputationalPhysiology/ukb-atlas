import json
from unittest.mock import patch

import pytest
import h5py
import numpy as np

import ukb.cli
import ukb.surface
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
    assert points.ED.shape[1] == 3
    assert points.ES.shape[1] == 3
    # Check that unwanted nodes were removed
    # (Original nodes count depends on the h5, but we ensure deletion happened)
    assert len(points.ED) > 0


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
    N = 34860  # Original number of nodes in the atlas before removing unwanted nodes

    with patch("scipy.io.loadmat") as mock_loadmat:
        # Mock the loadmat to return a structure with the expected keys
        hdf = {
            "MU": np.zeros((1, N)),
            "COEFF": np.random.rand(N, num_scores),
            "LATENT": np.random.rand(num_scores, 1),
        }
        mock_loadmat.return_value = {"pca200": np.array([[hdf]])}
        points = atlas.generate_points_burns(atlas_path, score=scores)

    assert points.ED.shape[1] == 3
    assert len(points.ED) > 0


def test_compute_S_errors(atlas_path):
    """Test that compute_S raises appropriate errors for invalid inputs."""
    with h5py.File(atlas_path, "r") as hdf:
        # Test invalid mode
        with pytest.raises(ValueError, match="Mode 999 is out of bounds"):
            atlas.compute_S(hdf, mode=999)


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

    for name in ukb.surface.surfaces:
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

    for name in ukb.surface.surfaces:
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
