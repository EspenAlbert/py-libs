import logging
import pydoc
from itertools import zip_longest

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
    groups: list[str],
    *,
    force_regen: bool = False,  # useful instead of having to re-run multiple times
):
    execution_e2e_dir = paths.execution_e2e_dir
    execution_e2e_pkg_path = paths.execution_e2e_pkg_path
    copy(paths.e2e_dir, execution_e2e_dir)
    settings = PkgSettings(
        repo_root=execution_e2e_dir, pkg_directory=execution_e2e_pkg_path
    )
    # reset all the generated files
    for group in groups:
        paths.python_actual_group_path(group).unlink(missing_ok=True)
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
    if force_regen:
        copy(execution_e2e_pkg_path, paths.e2e_pkg_dir, clean_dest=True)
        copy(actual_changelog_path, paths.e2e_dir / ".changelog.yaml")
        copy(settings.public_groups_path, paths.e2e_dir / ".groups.yaml")
    regression_check(
        ".changelog.yaml", actual_changelog_path.read_text(), extension=".yaml"
    )
    regression_check.check_path(settings.public_groups_path)
    regression_check.check_path(settings.init_path)
    for group in groups:
        regression_check.check_path(paths.python_actual_group_path(group))


def _question_patcher(
    file_expose_answers: dict[str, str], groups: list[str]
) -> question_patcher:
    responses = [
        PromptMatch(
            substring=f"Select references of type function to expose from {file}",
            response=response,
        )
        for file, response in file_expose_answers.items()
    ]
    # group creation
    for group in groups:
        responses.extend(
            [
                PromptMatch(
                    substring="Choose public API group name",
                    response=KeyInput.CONTROLC,
                ),
                PromptMatch(substring="enter name of new public group", response=group),
            ]
        )
    # group selection
    responses.extend(
        PromptMatch(
            substring="Choose public API group name",
            response=f"{KeyInput.DOWN} ",
        )
        for group, _ in zip_longest(groups, file_expose_answers)
        if group is None
    )
    return question_patcher(dynamic_responses=responses)


def test_01_initial(e2e_dirs, file_regression_e2e, monkeypatch):
    groups = ["my_group", "my_dep"]
    with _question_patcher({"_internal.py": f" {KeyInput.DOWN} "}, groups):
        run_e2e(e2e_dirs, file_regression_e2e, monkeypatch, groups)


def test_02_dep_order(e2e_dirs, file_regression_e2e, monkeypatch):
    groups = ["g1"]
    with _question_patcher({"a.py": " ", "b.py": " ", "c.py": " "}, groups):
        run_e2e(
            e2e_dirs,
            file_regression_e2e,
            monkeypatch,
            groups=groups,
        )


def test_import(_e2e_dir, monkeypatch):
    monkeypatch.syspath_prepend(
        _e2e_dir.parent / test_01_initial.__name__.removeprefix("test_")
    )
    what = pydoc.locate("my_pkg._internal.expose", forceload=True)
    assert what() == "EXPOSED"  # type: ignore
