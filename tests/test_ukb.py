import json
import subprocess
from unittest.mock import patch

import pytest
import h5py
import numpy as np

import ukb.cli
import ukb.surface
import ukb.mesh
from ukb import pointcloud, template
from ukb import atlas

BIV_REGIONS = [region for regions in ukb.surface.BIV.surfaces.values() for region in regions]


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
        assert set(manifest["cases"][case_]) == set(ukb.surface.BIV.surfaces)

    for name in BIV_REGIONS:
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
    assert physical_names(tmp_path / "ED.msh") == {
        ("LV_ENDO", 2),
        ("RV_ENDO", 2),
        ("EPI", 2),
        ("MV", 2),
        ("AV", 2),
        ("TV", 2),
        ("PV", 2),
        ("Wall", 3),
    }


def physical_names(path):
    meshio = pytest.importorskip("meshio")
    mesh = meshio.read(path)
    return {(name, int(dim)) for name, (_, dim) in mesh.field_data.items()}


def test_mesh_both_cases(tmp_path, atlas_path):
    ukb.cli.main(["surf", str(tmp_path), "--case", "both", "--cache-dir", str(atlas_path.parent)])
    ukb.cli.main(["mesh", str(tmp_path), "--case", "ES"])
    assert (tmp_path / "ES.msh").exists()
    assert not (tmp_path / "ED.msh").exists()


def test_mesh_without_manifest(tmp_path):
    with pytest.raises(FileNotFoundError, match="surf"):
        ukb.cli.main(["mesh", str(tmp_path), "--case", "ED"])


def test_mesh_geo_fallback(tmp_path, atlas_path):
    ukb.cli.main(["surf", str(tmp_path), "--case", "ED", "--cache-dir", str(atlas_path.parent)])
    with (
        patch("ukb.mesh.find_gmsh", return_value=FAKE_GMSH),
        patch("subprocess.run", return_value=gmsh_result()) as mock_run,
    ):
        ukb.mesh.create_mesh_geo(tmp_path, 5.0, 5.0, "ED")
    mock_run.assert_called_once()
    assert mock_run.call_args.args[0][0] == FAKE_GMSH[0]
    geo = (tmp_path / "ED.geo").read_text()
    assert 'Merge "LV_ENDO_ED.stl";' in geo
    assert 'Physical Surface("RV_ENDO", 2) = {2, 3};' in geo
    assert 'Physical Volume("Wall"' in geo


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
    assert physical_names(tmp_path / "ED_clipped.msh") == {
        ("LV_ENDO", 2),
        ("RV_ENDO", 2),
        ("EPI", 2),
        ("BASE", 2),
        ("Wall", 3),
    }


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

    for name in BIV_REGIONS:
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
    assert ukb.surface.read_manifest(tmp_path, "ES")[0]["RV_ENDO"] == [
        tmp_path / "RV_SEPTUM_ES.stl",
        tmp_path / "RV_FREEWALL_ES.stl",
    ]


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


@pytest.mark.parametrize(
    "num_nodes, message",
    [(5806, "older versions"), (5352, "--all"), (100, "5810")],
)
def test_get_point_cloud_wrong_shape(num_nodes, message):
    with pytest.raises(ValueError, match=message):
        pointcloud.get_point_cloud(np.zeros((num_nodes, 3)))


def test_custom_points_all_atlas_message(tmp_path):
    points = atlas.Points(ED=np.zeros((5352, 3)), ES=np.zeros((5352, 3)))
    with pytest.raises(ValueError, match="--all") as e:
        ukb.surface.main(tmp_path, custom_points=points)
    assert "older versions" not in str(e.value)


def test_mesh_and_clip_case_both(tmp_path, atlas_path):
    ukb.cli.main(["surf", str(tmp_path), "--case", "both", "--cache-dir", str(atlas_path.parent)])
    ukb.cli.main(["mesh", str(tmp_path), "--case", "both"])
    assert (tmp_path / "ED.msh").exists()
    assert (tmp_path / "ES.msh").exists()
    with pytest.raises(ValueError, match="single case"):
        ukb.cli.main(["mesh", str(tmp_path), "--case", "both", "--clipped"])
    with pytest.raises(SystemExit):
        ukb.cli.main(["clip", str(tmp_path), "--case", "both"])


@pytest.mark.parametrize("command", ["surf", "points"])
def test_all_atlas_not_supported(tmp_path, command):
    with (
        patch("ukb.atlas.download_atlas") as mock_download,
        pytest.raises(NotImplementedError, match="not supported"),
    ):
        ukb.cli.main([command, str(tmp_path / "out"), "--all"])
    mock_download.assert_not_called()
    assert not (tmp_path / "out").exists()


def test_surf_geometry_lv_closed(tmp_path, atlas_path):
    ukb.cli.main(["surf", str(tmp_path), "-g", "lv-closed", "--cache-dir", str(atlas_path.parent)])
    assert (tmp_path / "MV_CAP_ED.stl").exists()
    assert (tmp_path / "SEPTAL_BRIDGE_ED.stl").exists()
    assert not (tmp_path / "RV_FREEWALL_ED.stl").exists()
    assert json.loads((tmp_path / "parameters.json").read_text())["geometry"] == "lv-closed"
    manifest = json.loads((tmp_path / ukb.surface.MANIFEST).read_text())
    assert manifest["geometry"] == "lv-closed"
    assert set(manifest["volumes"]) == {"Wall", "LV_CAVITY"}


def tet_volumes(path):
    """Return physical volume name -> total tet volume."""
    meshio = pytest.importorskip("meshio")
    mesh = meshio.read(path)
    names = {tag: name for name, (tag, dim) in mesh.field_data.items() if dim == 3}
    tets = mesh.cells_dict["tetra"]
    tags = mesh.cell_data_dict["gmsh:physical"]["tetra"]
    p = mesh.points[tets]
    vol = np.abs(
        np.einsum("ij,ij->i", p[:, 1] - p[:, 0], np.cross(p[:, 2] - p[:, 0], p[:, 3] - p[:, 0]))
    )
    return {names[tag]: vol[tags == tag].sum() / 6 for tag in np.unique(tags)}


@pytest.mark.parametrize("geometry", ["biv", "biv-closed", "lv", "lv-closed"])
def test_mesh_geometry(tmp_path, atlas_path, geometry):
    ukb.cli.main(["surf", str(tmp_path), "-g", geometry, "--cache-dir", str(atlas_path.parent)])
    ukb.cli.main(["mesh", str(tmp_path), "--case", "ED"])
    recipe = ukb.surface.RECIPES[geometry]
    expected = {(s, 2) for s in recipe.surfaces} | {(v, 3) for v in recipe.volumes}
    assert physical_names(tmp_path / "ED.msh") == expected
    volumes = tet_volumes(tmp_path / "ED.msh")
    assert set(volumes) == set(recipe.volumes)
    assert all(v > 0 for v in volumes.values())


def test_closed_wall_matches_open(tmp_path, atlas_path):
    for geometry in ["biv", "biv-closed"]:
        folder = tmp_path / geometry
        ukb.cli.main(["surf", str(folder), "-g", geometry, "--cache-dir", str(atlas_path.parent)])
        ukb.cli.main(["mesh", str(folder), "--case", "ED"])
    open_wall = tet_volumes(tmp_path / "biv" / "ED.msh")["Wall"]
    closed_wall = tet_volumes(tmp_path / "biv-closed" / "ED.msh")["Wall"]
    assert closed_wall == pytest.approx(open_wall, rel=0.02)


def test_mesh_geo_fallback_volumes(tmp_path, atlas_path):
    ukb.cli.main(["surf", str(tmp_path), "-g", "biv-closed", "--cache-dir", str(atlas_path.parent)])
    with (
        patch("ukb.mesh.find_gmsh", return_value=FAKE_GMSH),
        patch("subprocess.run", return_value=gmsh_result()),
    ):
        ukb.mesh.create_mesh_geo(tmp_path, 5.0, 5.0, "ED")
    geo = (tmp_path / "ED.geo").read_text()
    assert geo.count("Surface Loop(") == 3
    assert geo.count("Volume(") >= 3
    assert 'Physical Volume("LV_CAVITY"' in geo
    assert 'Physical Surface("MV_CAP"' in geo


def test_clip_lv_raises(tmp_path, atlas_path):
    ukb.cli.main(["surf", str(tmp_path), "-g", "lv", "--cache-dir", str(atlas_path.parent)])
    with pytest.raises(ValueError, match="biv"):
        ukb.cli.main(["clip", str(tmp_path)])


def gmsh_result(returncode=0, stdout="Build options : 64Bit Hxt Netgen Mesh"):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")


FAKE_GMSH = ("/opt/gmsh/bin/gmsh", "Build options : 64Bit Hxt Netgen Mesh")


def test_find_gmsh():
    with (
        patch("shutil.which", return_value="/opt/gmsh/bin/gmsh"),
        patch("subprocess.run", return_value=gmsh_result(stdout="Build options : Hxt")),
    ):
        assert ukb.mesh.find_gmsh() == ("/opt/gmsh/bin/gmsh", "Build options : Hxt")


def test_find_gmsh_not_on_path():
    with patch("shutil.which", return_value=None):
        assert ukb.mesh.find_gmsh() is None


def test_find_gmsh_not_runnable():
    # e.g. on Windows, where the pip gmsh launcher script found on PATH cannot be run
    with (
        patch("shutil.which", return_value="C:/Python/Scripts/gmsh"),
        patch("subprocess.run", side_effect=OSError("[WinError 2]")),
    ):
        assert ukb.mesh.find_gmsh() is None


def test_mesh_geo_fallback_no_gmsh(tmp_path, atlas_path):
    ukb.cli.main(["surf", str(tmp_path), "--cache-dir", str(atlas_path.parent)])
    with (
        patch("ukb.mesh.find_gmsh", return_value=None),
        pytest.raises(RuntimeError, match="gmsh"),
    ):
        ukb.mesh.create_mesh_geo(tmp_path, 5.0, 5.0, "ED")


def test_mesh_geo_fallback_retries(tmp_path, atlas_path):
    ukb.cli.main(["surf", str(tmp_path), "--cache-dir", str(atlas_path.parent)])
    with (
        patch("ukb.mesh.find_gmsh", return_value=FAKE_GMSH),
        patch("subprocess.run", side_effect=[gmsh_result(returncode=1), gmsh_result()]) as run,
    ):
        ukb.mesh.create_mesh_geo(tmp_path, 5.0, 5.0, "ED")
    assert run.call_count == 2


def flaky_generate(failures):
    """Return a replacement for gmsh.model.mesh.generate failing the first calls."""
    gmsh = pytest.importorskip("gmsh")
    generate = gmsh.model.mesh.generate
    calls = []

    def generate_(dim=3):
        calls.append(dim)
        if len(calls) <= failures:
            raise Exception("PLC Error:  A segment and a facet intersect at point")
        generate(dim)

    return generate_, calls


def test_mesh_retries_failed_generation(tmp_path, atlas_path):
    gmsh = pytest.importorskip("gmsh")
    ukb.cli.main(["surf", str(tmp_path), "--cache-dir", str(atlas_path.parent)])
    generate, calls = flaky_generate(failures=1)
    with patch.object(gmsh.model.mesh, "generate", generate):
        ukb.cli.main(["mesh", str(tmp_path)])
    assert len(calls) == 2
    assert (tmp_path / "ED.msh").exists()


def test_mesh_gives_up_after_retries(tmp_path, atlas_path):
    gmsh = pytest.importorskip("gmsh")
    ukb.cli.main(["surf", str(tmp_path), "--cache-dir", str(atlas_path.parent)])
    generate, calls = flaky_generate(failures=10)
    with (
        patch.object(gmsh.model.mesh, "generate", generate),
        pytest.raises(Exception, match="PLC"),
    ):
        ukb.cli.main(["mesh", str(tmp_path)])
    assert len(calls) == 3


@pytest.mark.parametrize("netgen", [True, False])
def test_geo_script_netgen(tmp_path, netgen):
    geo = ukb.mesh.geo_script({"S": [tmp_path / "S.stl"]}, {"Wall": ["S"]}, 5.0, 5.0, netgen=netgen)
    assert f"Mesh.OptimizeNetgen = {int(netgen)};" in geo


def test_mesh_geo_fallback_without_netgen(tmp_path, atlas_path):
    ukb.cli.main(["surf", str(tmp_path), "--cache-dir", str(atlas_path.parent)])
    with (
        patch("ukb.mesh.find_gmsh", return_value=("gmsh", "Build options : Hxt")),
        patch("subprocess.run", return_value=gmsh_result()),
    ):
        ukb.mesh.create_mesh_geo(tmp_path, 5.0, 5.0, "ED")
    assert "Mesh.OptimizeNetgen = 0;" in (tmp_path / "ED.geo").read_text()


def test_mesh_geo_fallback_gmsh_fails(tmp_path, atlas_path):
    ukb.cli.main(["surf", str(tmp_path), "--cache-dir", str(atlas_path.parent)])
    with (
        patch("ukb.mesh.find_gmsh", return_value=FAKE_GMSH),
        patch("subprocess.run", return_value=gmsh_result(returncode=1)) as run,
        pytest.raises(RuntimeError, match="gmsh"),
    ):
        ukb.mesh.create_mesh_geo(tmp_path, 5.0, 5.0, "ED")
    assert run.call_count == 3


@pytest.mark.skipif(ukb.mesh.find_gmsh() is None, reason="needs a working gmsh binary")
@pytest.mark.parametrize("geometry", ["lv", "biv-closed"])
def test_mesh_geo_fallback_real_gmsh(tmp_path, atlas_path, geometry):
    ukb.cli.main(["surf", str(tmp_path), "-g", geometry, "--cache-dir", str(atlas_path.parent)])
    ukb.mesh.create_mesh_geo(tmp_path, 5.0, 5.0, "ED")
    recipe = ukb.surface.RECIPES[geometry]
    assert physical_names(tmp_path / "ED.msh") == {(s, 2) for s in recipe.surfaces} | {
        (v, 3) for v in recipe.volumes
    }
