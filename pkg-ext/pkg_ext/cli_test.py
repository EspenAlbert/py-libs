import logging
import pydoc

from ask_shell._internal.interactive import KeyInput, PromptMatch, question_patcher
from click.testing import Result
from pytest import MonkeyPatch
from typer.testing import CliRunner
from zero_3rdparty.file_utils import clean_dir, copy

from pkg_ext.cli import app
from pkg_ext.conftest import E2eDirs, E2eRegressionCheck
from pkg_ext.settings import PkgSettings

logger = logging.getLogger(__name__)
runner = CliRunner()


def run(command: str, exit_code: int = 0) -> Result:
    result = runner.invoke(app, command.split())
    logger.info(f"cli command output={result.output}")
    if exit_code == 0 and (e := result.exception):
        logger.exception(e)
        raise e
    assert result.exit_code == exit_code, "exit code is not as expected"
    return result


def test_normal_help_command_is_ok():
    run("--help", exit_code=0)


def run_e2e(
    paths: E2eDirs,
    regression_check: E2eRegressionCheck,
    monkeypatch: MonkeyPatch,
):
    execution_e2e_dir = paths.execution_e2e_dir
    execution_e2e_pkg_path = paths.execution_e2e_pkg_path
    copy(paths.e2e_dir, execution_e2e_dir)
    settings = PkgSettings(
        repo_root=execution_e2e_dir, pkg_directory=execution_e2e_pkg_path
    )
    monkeypatch.syspath_prepend(execution_e2e_dir)
    clean_dir(settings.changelog_path, recreate=False)
    settings.public_groups_path.unlink(missing_ok=True)
    settings.init_path.write_text("")
    command = f"--repo-root {execution_e2e_dir} {paths.pkg_path_relative} --skip-open"
    logger.info(f"running command: {command}")
    result = run(command)
    assert result.exit_code == 0
    actual_changelog_path = next(settings.changelog_path.glob("*.yaml"), None)
    assert actual_changelog_path, "no .changelog/*.yaml file created "
    regression_check(
        ".changelog.yaml", actual_changelog_path.read_text(), extension=".yaml"
    )
    regression_check.check_path(settings.public_groups_path)
    regression_check.check_path(settings.init_path)


def test_01_initial(e2e_dirs, file_regression_e2e, monkeypatch):
    # todo: continue with the e2e regression check
    with question_patcher(
        dynamic_responses={
            PromptMatch(
                substring="Select references of type function to expose from _internal.py"
            ): f" {KeyInput.DOWN} ",
            PromptMatch(
                substring="Choose public API group name",
                max_matches=2,
            ): f"{KeyInput.CONTROLC}",
            PromptMatch(substring="enter name of new public group"): "my_group",
            # TODO: Understand how to do this substring matching better
            PromptMatch(substring="enter name of new public"): "my_dep",
            PromptMatch(substring="Do you want to write __init__.py"): "y",
        }
    ):
        run_e2e(e2e_dirs, file_regression_e2e, monkeypatch)
        file_regression_e2e.check_path(e2e_dirs.python_actual_group_path("my_dep"))
        file_regression_e2e.check_path(e2e_dirs.python_actual_group_path("my_group"))


def test_import(_e2e_dir, monkeypatch):
    monkeypatch.syspath_prepend(
        _e2e_dir.parent / test_01_initial.__name__.removeprefix("test_")
    )
    what = pydoc.locate("my_pkg._internal.expose", forceload=True)
    assert what() == "EXPOSED"  # type: ignore
