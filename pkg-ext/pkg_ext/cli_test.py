import logging
import pydoc
from pathlib import Path

from ask_shell._internal.interactive import KeyInput, PromptMatch, question_patcher
from click.testing import Result
from pytest import MonkeyPatch
from typer.testing import CliRunner
from zero_3rdparty.file_utils import clean_dir

from pkg_ext.cli import app
from pkg_ext.conftest import E2eRegressionCheck
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
    e2e_dir: Path,
    e2e_pkg_path: Path,
    regression_check: E2eRegressionCheck,
    monkeypatch: MonkeyPatch,
):
    pkg_path_relative = str(e2e_pkg_path.relative_to(e2e_dir))
    settings = PkgSettings(repo_root=e2e_dir, pkg_directory=e2e_pkg_path)
    monkeypatch.syspath_prepend(e2e_dir)
    logger.info(f"adding to path: {e2e_dir}")
    clean_dir(settings.changelog_path, recreate=False)
    settings.public_groups_path.unlink(missing_ok=True)
    settings.check_paths
    command = f"--repo-root {e2e_dir} {pkg_path_relative} --skip-open"
    logger.info(f"running command: {command}")
    result = run(command)
    assert result.exit_code == 0


def test_01_initial(e2e_dir, e2e_pkg_path, file_regression_e2e, monkeypatch):
    with question_patcher(
        dynamic_responses={
            PromptMatch(
                substring="Select references of type function to expose from _internal.py"
            ): " ",
            PromptMatch(
                substring="Choose public API group name"
            ): f"{KeyInput.CONTROLC}",
            PromptMatch(substring="enter name of new public group"): "my_group",
            PromptMatch(substring="Do you want to write __init__.py"): "y",
        }
    ):
        run_e2e(e2e_dir, e2e_pkg_path, file_regression_e2e, monkeypatch)


def test_import(e2e_dir, monkeypatch):
    monkeypatch.syspath_prepend(
        e2e_dir.parent / test_01_initial.__name__.removeprefix("test_")
    )
    what = pydoc.locate("my_pkg._internal.expose", forceload=True)
    assert what() == "EXPOSED"  # type: ignore
