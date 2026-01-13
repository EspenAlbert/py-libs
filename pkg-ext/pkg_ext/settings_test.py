from pkg_ext.settings import PkgSettings, detect_is_flat


def test_dev_suffix(settings: PkgSettings):
    assert settings.public_groups_path.name == ".groups.yaml"
    settings.dev_mode = True
    assert settings.public_groups_path.name == ".groups-dev.yaml"


def test_detect_is_flat(tmp_path):
    pkg_path = tmp_path / "my_pkg"
    pkg_path.mkdir(exist_ok=True)
    (pkg_path / "__init__.py").touch()

    assert detect_is_flat(pkg_path)

    (pkg_path / "_internal").mkdir(exist_ok=True)
    assert not detect_is_flat(pkg_path)
