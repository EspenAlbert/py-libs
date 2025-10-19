import pytest
from zero_3rdparty.file_utils import ensure_parents_write_text

from pkg_ext.changelog.actions import ChangelogAction, ChangelogActionType
from pkg_ext.changelog.parser import parse_changelog
from pkg_ext.conftest import TEST_PKG_NAME
from pkg_ext.git_usage.state import GitChanges
from pkg_ext.models import PkgCodeState, pkg_ctx
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
    (
        ChangelogAction(name="func_name", type=ChangelogActionType.BREAKING_CHANGE),
        "1.0.0",
    ),
    (ChangelogAction(name="func_name", type=ChangelogActionType.EXPOSE), "0.1.0"),
    (ChangelogAction(name="func_name", type=ChangelogActionType.FIX), "0.0.2"),
    (ChangelogAction(name="func_name", type=ChangelogActionType.HIDE), "0.0.1"),
]


@pytest.mark.parametrize(
    "action,new_version", _actions, ids=[action.type for action, _ in _actions]
)
def test_bump_major(pkg_ctx_instance, action, new_version):
    actions = [action]
    pkg_ctx_instance._actions = actions
    with (
        pkg_ctx_instance
    ):  # use context manager to read the actions from instance rather than disk
        assert (
            str(bump_version(pkg_ctx_instance, PkgVersion.parse("0.0.1")))
            == new_version
        )
