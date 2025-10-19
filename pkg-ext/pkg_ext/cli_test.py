import logging
from itertools import zip_longest
from pathlib import Path

from ask_shell._internal._run import run_and_wait
from ask_shell._internal.interactive import KeyInput, PromptMatch, question_patcher
from click.testing import Result
from pytest import MonkeyPatch
from typer.testing import CliRunner
from zero_3rdparty.file_utils import clean_dir, copy
from zero_3rdparty.str_utils import ensure_suffix

from pkg_ext.changelog.actions import (
    changelog_filename,
    default_changelog_path,
)
from pkg_ext.cli import app
from pkg_ext.conftest import CHANGELOG_YAML_FILENAME, E2eDirs, E2eRegressionCheck
from pkg_ext.git_usage.actions import git_commit
from pkg_ext.git_usage.state import GitSince
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


def prepare_test(
    paths: E2eDirs,
    monkeypatch: MonkeyPatch,
    groups: list[str],
    step_number: int,
    copy_ignore_globs: list[str] | None,
) -> PkgSettings:
    execution_e2e_dir = paths.execution_e2e_dir
    execution_e2e_pkg_path = paths.execution_e2e_pkg_path
    if step_number == 1:
        copy(paths.e2e_dir, execution_e2e_dir)
        if copy_ignore_globs:
            for glob in copy_ignore_globs:
                for path in list(execution_e2e_dir.rglob(glob)):
                    if path.is_file():
                        path.unlink()
    settings = PkgSettings(
        repo_root=execution_e2e_dir, pkg_directory=execution_e2e_pkg_path
    )
    if step_number > 1:
        # rename the old changelog path
        default_path = default_changelog_path(settings.changelog_dir)
        if default_path.exists():
            new_name = changelog_filename(step_number - 1)
            default_path.rename(default_path.with_name(new_name))
    else:
        # reset all the generated files
        for group in groups:
            paths.python_actual_group_path(group).unlink(missing_ok=True)
        monkeypatch.syspath_prepend(execution_e2e_dir)
        clean_dir(settings.changelog_dir, recreate=False)
        settings.public_groups_path.unlink(missing_ok=True)
        settings.init_path.write_text("")
        settings.changelog_md.unlink(missing_ok=True)
    return settings


def _run_command(
    settings: PkgSettings,
    *,
    git_since: GitSince = GitSince.NO_GIT_CHANGES,
    extra_cli_args: str = "",
    extra_global_cli_args: str = "",
):
    execution_e2e_dir = settings.repo_root
    pkg_path_relative = str(settings.pkg_directory.relative_to(execution_e2e_dir))
    if extra_global_cli_args:
        extra_global_cli_args = ensure_suffix(extra_global_cli_args, " ")
    command = f"{extra_global_cli_args}--skip-open --repo-root {execution_e2e_dir} --pkg-path {pkg_path_relative} generate-api --git-since {git_since} --bump"
    if extra_cli_args:
        command = f"{command} {extra_cli_args}"
    logger.info(f"running command: {command}")
    result = run(command)
    assert result.exit_code == 0


def run_e2e(
    paths: E2eDirs,
    regression_check: E2eRegressionCheck,
    monkeypatch: MonkeyPatch,
    groups: list[str],
    *,
    force_regen: bool = False,
    git_since: GitSince = GitSince.NO_GIT_CHANGES,
    step_number: int = 1,
    skip_regressions: bool = False,
    copy_ignore_globs: list[str] | None = None,
    extra_cli_args: str = "",
    extra_global_cli_args: str = "",
) -> PkgSettings:
    settings = prepare_test(paths, monkeypatch, groups, step_number, copy_ignore_globs)
    _run_command(
        settings,
        git_since=git_since,
        extra_cli_args=extra_cli_args,
        extra_global_cli_args=extra_global_cli_args,
    )
    actual_changelog_path = default_changelog_path(settings.changelog_dir)
    if not actual_changelog_path.exists():
        actual_changelog_path = max(
            path for path in actual_changelog_path.parent.glob("*.yaml")
        )
    changelog_md = settings.changelog_md
    if force_regen:
        copy(settings.pkg_directory, paths.e2e_pkg_dir, clean_dest=True)
        copy(actual_changelog_path, paths.e2e_dir / CHANGELOG_YAML_FILENAME)
        copy(settings.public_groups_path, paths.e2e_dir / ".groups.yaml")
        if changelog_md.exists():
            copy(changelog_md, paths.e2e_dir / settings.changelog_md.name)
        regression_check.modify_files(paths.e2e_dir)
    regression_check.modify_files(paths.execution_e2e_dir)
    if skip_regressions:
        return settings
    regression_check(
        CHANGELOG_YAML_FILENAME, actual_changelog_path.read_text(), extension=".yaml"
    )
    regression_check.check_path(settings.public_groups_path)
    regression_check.check_path(settings.init_path)
    assert changelog_md.exists(), "no changelog generated!"
    if changelog_md.exists():
        regression_check.check_path(changelog_md)
    for group in groups:
        regression_check.check_path(paths.python_actual_group_path(group))
    return settings


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
        settings = run_e2e(e2e_dirs, file_regression_e2e, monkeypatch, groups)
        # is bot after a run should have no effect
        _run_command(settings, extra_global_cli_args="--is-bot")


def test_02_dep_order(e2e_dirs, file_regression_e2e, monkeypatch):
    groups = ["g1"]
    with _question_patcher({"a.py": " ", "b.py": " ", "c.py": " "}, groups):
        run_e2e(
            e2e_dirs,
            file_regression_e2e,
            monkeypatch,
            groups=groups,
        )


def test_03_nested(e2e_dirs, file_regression_e2e, monkeypatch):
    groups = ["n1"]
    with _question_patcher({"_internal/a.py": f" {KeyInput.DOWN} "}, groups):
        run_e2e(
            e2e_dirs,
            file_regression_e2e,
            monkeypatch,
            groups,
        )


def git_init(repo_dir: Path):
    run_and_wait("git init", cwd=repo_dir)


_chosen_content = """\
def chosen():
    return "chosen"
"""


def test_04_git_fix(e2e_dirs, file_regression_e2e, monkeypatch):
    """
    Step 1:
    - Copy everything except chosen.py
    - Changelog should be updated.
    Step 2:
    - Commit the chosen.py
    -
    """
    pkg_path = e2e_dirs.execution_e2e_pkg_path
    chosen_filepath = pkg_path / "chosen.py"
    groups = ["git_inferred"]
    with _question_patcher({"inferred.py": " "}, groups):
        run_e2e(
            e2e_dirs,
            file_regression_e2e,
            monkeypatch,
            groups,
            skip_regressions=True,
            copy_ignore_globs=[chosen_filepath.name],
        )
    repo_path = e2e_dirs.execution_e2e_dir
    git_init(repo_path)
    git_commit(repo_path, "initial commit", tag="0.0.1")
    chosen_filepath.write_text(_chosen_content)
    chosen_file_commit_message = "fix: adds chosen file"
    git_commit(repo_path, chosen_file_commit_message)
    with _question_patcher({chosen_filepath.name: ""}, groups=groups) as patcher:
        patcher.dynamic_responses.extend(
            [
                PromptMatch(response=" ", substring="select group for commit"),
                PromptMatch(response=" ", substring=chosen_file_commit_message),
            ]
        )
        run_e2e(
            e2e_dirs,
            file_regression_e2e,
            monkeypatch,
            groups,
            git_since=GitSince.LAST_GIT_TAG,
            step_number=2,
            extra_cli_args="--tag --pr 2",
            extra_global_cli_args="--tag-prefix v",
        )
