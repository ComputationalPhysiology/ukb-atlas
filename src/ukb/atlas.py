from typing import NamedTuple
from pathlib import Path
import logging
import h5py
import numpy as np

logger = logging.getLogger(__name__)


class Points(NamedTuple):
    ED: np.ndarray
    ES: np.ndarray


unwanted_nodes = (5630, 5655, 5696, 5729)


def download_atlas(outdir: Path, all: bool = True) -> Path:
    """Download the UK Biobank atlas from the Cardiac Atlas Project.

    Parameters
    ----------
    outdir : Path
        Directory to download the atlas to.
    all : bool, optional
        If true, download the PCA atlas derived from all 4,329 subjects
        from the UK Biobank Study. If false, downlaod PCA atlas derived
        from 630 healthy reference subjects from the UK Biobank Study
        (see [1]_) by default False

    Returns
    -------
    Path
        Path to the downloaded file.

    References
    ----------
    .. [1] Petersen, Steffen E., et al. "Reference ranges for cardiac
        structure and function using cardiovascular magnetic resonance
        (CMR) in Caucasians from the UK Biobank population cohort.
        " Journal of cardiovascular magnetic resonance 19.1 (2016): 18.

    """
    from urllib.request import urlretrieve
    import zipfile

    outdir = Path(outdir)
    outdir.mkdir(exist_ok=True)

    if all:
        url = "https://www.cardiacatlas.org/share/download.php?id=59&token=CUfi3eWV41LrIL6ZtlMf7bvHEkiiWpVu&download"
        path = outdir / "UKBRVLV_ALL.zip"
    else:
        url = "https://www.cardiacatlas.org/share/download.php?id=60&token=AR3JSoaxJ9Ev9n8QAkvV4BHJUniyttqm&download"

        path = outdir / "UKBRVLV.zip"

    if not path.with_suffix(".h5").exists():
        logger.info(f"Downloading {url} to {path}. This may take a while.")
        urlretrieve(url, path)
        with zipfile.ZipFile(path, "r") as zip_ref:
            zip_ref.extractall(outdir)
        path.unlink()

        logger.info("Done downloading.")

    return path.with_suffix(".h5")


def generate_points(filename: Path, mode: int = -1, std: float = 1.5) -> Points:
    """Generate points from the UK Biobank atlas.

    Parameters
    ----------
    filename : Path
        Path to the UK Biobank atlas file.
    mode : int, optional
        Mode to generate points from. If -1, generate points from the mean
        shape. If between 0 and the number of modes, generate points from
        the specified mode. By default -1
    std : float, optional
        Standard deviation to scale the mode by, by default 1.5

    Returns
    -------
    Points
        Named tuple containing the end-diastolic (ED) and end-systolic (ES)
        points.
    """
    logger.info(f"Generating points from {filename} using mode {mode} and std {std}")
    with h5py.File(filename, "r") as hdf:
        mu = np.transpose(hdf["MU"])
        if mode == -1:
            S = mu
        else:
            if mode < 0 or mode >= hdf["COEFF"].shape[0]:
                raise ValueError(
                    f"Mode {mode} is out of bounds. Needs to be between "
                    f"0 and {hdf['COEFF'].shape[0] - 1}"
                )
            eigenvalue = hdf["LATENT"][0, mode]
            eigenvector = hdf["COEFF"][mode, :]
            S = np.transpose(hdf["MU"]) + (std * np.sqrt(eigenvalue) * eigenvector)

        # First half is ED and second half is ES
        N = S.shape[1] // 2
        ed = np.reshape(S[0, :N], (-1, 3))
        es = np.reshape(S[0, N:], (-1, 3))

    return Points(
        ED=np.delete(ed, unwanted_nodes, axis=0),
        ES=np.delete(es, unwanted_nodes, axis=0),
    )
