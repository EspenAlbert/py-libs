import pkg_version
import pytest


@pytest.mark.parametrize("version", ["1.0.0", "1.0.0+rc1", "1.0.0+a1", "1.0.0+b1"])
def test_pkg_version(version):
    assert pkg_version.extract_version(version, f'VERSION = "{version}"') == version
    assert pkg_version.PkgVersion.parse(version)


def test_bumping():
    version = pkg_version.PkgVersion.parse("1.0.0")
    assert str(version.bump_major()) == "2.0.0"
    assert str(version.bump_minor()) == "1.1.0"
    assert str(version.bump_patch()) == "1.0.1"
    assert str(version.bump_alpha()) == "1.0.0a1"
    assert str(version.bump_beta()) == "1.0.0b1"
    assert str(version.bump_rc()) == "1.0.0rc1"
    version = pkg_version.PkgVersion.parse("1.0.0rc1")
    assert str(version.bump_rc()) == "1.0.0rc2"
    version = pkg_version.PkgVersion.parse("1.0.0a1")
    assert str(version.bump_alpha()) == "1.0.0a2"
    version = pkg_version.PkgVersion.parse("1.0.0b1")
    assert str(version.bump_beta()) == "1.0.0b2"


def test_pkg_tag():
    assert pkg_version.pkg_tag("model-lib", "1.0.0") == "m1.0.0"
    assert pkg_version.pkg_tag("zero-3rdparty", "1.0.0") == "z1.0.0"
