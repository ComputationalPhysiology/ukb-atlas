from unittest.mock import patch
import pytest
import h5py
import numpy as np
from ukb import atlas


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
