import json
import pytest
import ukb.cli
import ukb.surface


def test_generate_surfaces_mean_healthy(tmp_path):
    ukb.cli.main([str(tmp_path), "--subdir", "."])
    assert (tmp_path / "UKBRVLV.h5").exists()
    assert (tmp_path / "parameters.json").exists()
    for name in ukb.surface.surfaces:
        for case in ["ED", "ES"]:
            path = tmp_path / f"{name}_{case}.stl"
            assert path.exists()


def test_generate_surfaces_non_mean_healthy(tmp_path):
    mode = 1
    std = 0.3
    ukb.cli.main([str(tmp_path), "--mode", str(mode), "--std", str(std), "--subdir", "."])
    assert (tmp_path / "UKBRVLV.h5").exists()
    assert (tmp_path / "parameters.json").exists()
    params = json.loads((tmp_path / "parameters.json").read_text())
    assert params["mode"] == mode
    assert params["std"] == std

    for name in ukb.surface.surfaces:
        for case in ["ED", "ES"]:
            path = tmp_path / f"{name}_{case}.stl"
            assert path.exists()


@pytest.mark.xfail(reason="I think we have the wrong template")
def test_generate_surfaces_mean_all(tmp_path):
    ukb.cli.main([str(tmp_path), "--all", "--subdir", "."])
    assert (tmp_path / "UKBRVLV_ALL.h5").exists()
    assert (tmp_path / "parameters.json").exists()
    for name in ukb.surface.surfaces:
        for case in ["ED", "ES"]:
            path = tmp_path / f"{name}_{case}.stl"
            assert path.exists()
