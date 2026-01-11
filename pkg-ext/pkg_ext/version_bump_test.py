import pytest
from zero_3rdparty.file_utils import ensure_parents_write_text

from pkg_ext.changelog import BumpType
from pkg_ext.changelog.actions import (
    BreakingChangeAction,
    FixAction,
    KeepPrivateAction,
    MakePublicAction,
)
from pkg_ext.changelog.parser import parse_changelog
from pkg_ext.conftest import TEST_PKG_NAME
from pkg_ext.context import pkg_ctx
from pkg_ext.git_usage.state import GitChanges
from pkg_ext.models import PkgCodeState
from pkg_ext.settings import PkgSettings
from pkg_ext.version_bump import PkgVersion, bump_version, read_current_version


@pytest.fixture()
def pkg_ctx_instance(settings) -> pkg_ctx:
    tool, _ = parse_changelog(settings)
    return pkg_ctx(
        settings,
        tool,
        PkgCodeState.model_construct(
            pkg_import_name=TEST_PKG_NAME, import_id_refs={}, files=[]
        ),
        GitChanges.empty(),
    )


def test_read_version_default(pkg_ctx_instance):
    assert read_current_version(pkg_ctx_instance) == PkgVersion.default()


def test_read_version_default_from_toml(settings, pkg_ctx_instance):
    pyproject_toml = settings.pyproject_toml
    ensure_parents_write_text(pyproject_toml, '[project]\nversion = "1.2.3"')
    assert str(read_current_version(pkg_ctx_instance)) == "1.2.3"


_actions = [
    (BreakingChangeAction(name="func_name", group="test_group", details=""), "1.0.0"),
    (MakePublicAction(name="func_name", group="test_group"), "0.1.0"),
    (FixAction(name="func_name", short_sha="abc", message="fix"), "0.0.2"),
    (KeepPrivateAction(name="func_name"), "0.0.1"),
]


@pytest.mark.parametrize(
    "action,new_version",
    _actions,
    ids=[type(action).__name__ for action, _ in _actions],
)
def test_bump_major(pkg_ctx_instance, action, new_version):
    actions = [action]
    pkg_ctx_instance._actions = actions
    with pkg_ctx_instance:
        assert (
            str(bump_version(pkg_ctx_instance, PkgVersion.parse("0.0.1")))
            == new_version
        )


_prerelease_bump_type_cases = [
    ("1.0.0b7", BumpType.BETA),
    ("1.0.0a3", BumpType.ALPHA),
    ("1.0.0rc2", BumpType.RC),
    ("1.0.0", None),
    ("2.3.4", None),
]


@pytest.mark.parametrize(
    "version,expected_bump_type",
    _prerelease_bump_type_cases,
    ids=[v for v, _ in _prerelease_bump_type_cases],
)
def test_prerelease_bump_type(version, expected_bump_type):
    assert PkgVersion.parse(version).prerelease_bump_type == expected_bump_type


@pytest.fixture()
def pkg_ctx_keep_prerelease(static_env_vars, tmp_path) -> pkg_ctx:
    pkg_directory = tmp_path / TEST_PKG_NAME
    init_path = pkg_directory / "__init__.py"
    ensure_parents_write_text(init_path, "")
    settings = PkgSettings(
        repo_root=tmp_path, pkg_directory=pkg_directory, keep_prerelease=True
    )
    tool, _ = parse_changelog(settings)
    return pkg_ctx(
        settings,
        tool,
        PkgCodeState.model_construct(
            pkg_import_name=TEST_PKG_NAME, import_id_refs={}, files=[]
        ),
        GitChanges.empty(),
    )


_keep_prerelease_cases = [
    (MakePublicAction(name="func_name", group="test_group"), "1.0.0b7", "1.0.0b8"),
    (
        BreakingChangeAction(name="func_name", group="test_group", details=""),
        "1.0.0b7",
        "1.0.0b8",
    ),
    (FixAction(name="func_name", short_sha="abc", message="fix"), "2.0.0a5", "2.0.0a6"),
    (MakePublicAction(name="func_name", group="test_group"), "1.0.0rc1", "1.0.0rc2"),
    (MakePublicAction(name="func_name", group="test_group"), "1.0.0", "1.1.0"),
]


@pytest.mark.parametrize(
    "action,old_version,new_version",
    _keep_prerelease_cases,
    ids=[f"{old}->{new}" for _, old, new in _keep_prerelease_cases],
)
def test_bump_version_keep_prerelease(
    pkg_ctx_keep_prerelease, action, old_version, new_version
):
    pkg_ctx_keep_prerelease._actions = [action]
    with pkg_ctx_keep_prerelease:
        result = bump_version(pkg_ctx_keep_prerelease, PkgVersion.parse(old_version))
        assert str(result) == new_version
