import pytest

from ukb import atlas


@pytest.fixture(scope="session")
def atlas_path(tmp_path_factory):
    """Fixture to download the atlas once per session."""
    # Create a persistent directory for the session
    cache_dir = tmp_path_factory.mktemp("atlas_cache")
    # Download the healthy reference atlas (all=False)
    path = atlas.download_atlas(outdir=cache_dir, all=False)
    return path
