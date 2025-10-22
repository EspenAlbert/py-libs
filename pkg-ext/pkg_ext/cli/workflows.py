"""Business logic workflows for pkg-ext operations."""

from __future__ import annotations

import logging
from contextlib import ExitStack
from pathlib import Path
from typing import Self

from ask_shell._internal._run import run_and_wait
from ask_shell._internal.interactive import raise_on_question
from model_lib.model_base import Entity
from pydantic import model_validator
from zero_3rdparty.file_utils import iter_paths_and_relative

from pkg_ext.changelog import (
    ChangelogAction,
    ChangelogActionType,
    add_git_changes,
    changelog_filepath,
    dump_changelog_actions,
    parse_changelog,
    parse_changelog_file_path,
    write_changelog_md,
)
from pkg_ext.changelog.actions import ReleaseChangelog, archive_old_actions
from pkg_ext.errors import NoHumanRequiredError
from pkg_ext.file_parser import parse_code_symbols, parse_symbols
from pkg_ext.generation import update_pyproject_toml, write_groups, write_init
from pkg_ext.git_usage import (
    GitChangesInput,
    GitSince,
    find_git_changes,
    find_pr_info_raw,
    git_commit,
)
from pkg_ext.interactive import on_new_ref
from pkg_ext.models import PkgCodeState, pkg_ctx
from pkg_ext.reference_handling import handle_added_refs, handle_removed_refs
from pkg_ext.settings import PkgSettings
from pkg_ext.version_bump import bump_version, read_current_version

logger = logging.getLogger(__name__)


class GenerateApiInput(Entity):
    settings: PkgSettings
    git_changes_since: GitSince

    bump_version: bool
    create_tag: bool  # can we say always to create the tag when we bump_version?
    push: bool
    explicit_pr: int = 0

    @model_validator(mode="after")
    def checks(self) -> Self:
        if self.create_tag:
            assert self.bump_version, "cannot tag without bumping version"
        if self.push:
            assert self.create_tag, "cannot push without tagging/committing"
            assert not find_pr_info_raw(self.settings.repo_root), (
                "Never push changes from a branch with an active PR, release jobs only runs from the default branch and wouldn't be triggered leading to tags without releases"
            )
        return self

    @property
    def is_bot(self) -> bool:
        return self.settings.is_bot


def parse_pkg_code_state(settings: PkgSettings) -> PkgCodeState:
    """PkgDiskState is based only on the current python files in the package"""
    pkg_py_files = list(
        iter_paths_and_relative(settings.pkg_directory, "*.py", only_files=True)
    )
    pkg_import_name = settings.pkg_import_name

    def is_generated(py_text: str) -> bool:
        return py_text.startswith(settings.file_header)

    files = sorted(
        parsed
        for path, rel_path in pkg_py_files
        if (
            parsed := parse_symbols(
                path, rel_path, pkg_import_name, is_generated=is_generated
            )
        )
    )

    import_id_symbols = parse_code_symbols(files, pkg_import_name)
    return PkgCodeState(
        pkg_import_name=pkg_import_name,
        import_id_refs=import_id_symbols,
        files=files,
    )


def create_ctx(api_input: GenerateApiInput) -> pkg_ctx:
    settings = api_input.settings
    exit_stack = ExitStack()
    if api_input.is_bot:
        exit_stack.enter_context(raise_on_question(raise_error=NoHumanRequiredError))
    with exit_stack:
        code_state = parse_pkg_code_state(settings)
        tool_state, extra_actions = parse_changelog(settings, code_state)
        git_changes_input = GitChangesInput(
            repo_path=settings.repo_root,
            since=api_input.git_changes_since,
        )
        git_changes = find_git_changes(git_changes_input)
        return pkg_ctx(
            settings=settings,
            tool_state=tool_state,
            code_state=code_state,
            ref_add_callback=[on_new_ref(tool_state.groups)],
            git_changes=git_changes,
            _actions=extra_actions,
            explicit_pr=api_input.explicit_pr,
        )


def update_changelog_entries(api_input: GenerateApiInput) -> pkg_ctx | None:
    """Should also read the changelog entries from the default file if it is existing."""
    exit_stack = ExitStack()
    if api_input.is_bot:
        exit_stack.enter_context(raise_on_question(raise_error=NoHumanRequiredError))
    with exit_stack:
        ctx = create_ctx(api_input)
        try:
            with ctx:
                handle_removed_refs(ctx)
                handle_added_refs(ctx)
                add_git_changes(ctx)
        except KeyboardInterrupt:
            logger.warning(
                f"Interrupted while handling added references, only {ctx.settings.changelog_dir} updated"
            )
            return
    return ctx


def sync_files(api_input: GenerateApiInput, ctx: pkg_ctx):
    version_old = read_current_version(ctx)
    version_new = bump_version(ctx, version_old)
    ctx.add_versions(str(version_old), str(version_new))
    version_str = str(version_new) if api_input.bump_version else str(version_old)
    write_groups(ctx)
    write_init(ctx, version_str)
    update_pyproject_toml(ctx, version_str)
    write_changelog_md(ctx)
    settings = api_input.settings
    if hooks := settings.after_file_write_hooks:
        for hook in hooks:
            logger.info(f"running hook: {hook}")
            run_and_wait(hook, cwd=settings.repo_root)


def post_merge_commit_workflow(
    repo_path: Path,
    changelog_dir_path: Path,
    pr_number: int,
    tag_prefix: str,
    old_version: str,
    new_version: str,
    push: bool,
):
    assert pr_number > 0, f"invalid PR number: {pr_number} must be > 0"
    changelog_pr_path = changelog_filepath(changelog_dir_path, pr_number)
    old_actions = parse_changelog_file_path(changelog_pr_path)
    assert old_actions, f"no changes to commit for {pr_number}"
    if release_action := next(
        (
            action
            for action in old_actions
            if action.type == ChangelogActionType.RELEASE
        ),
        None,
    ):
        raise ValueError(f"pr has already been released: {release_action!r}")
    release_action = ChangelogAction(
        name=new_version,
        type=ChangelogActionType.RELEASE,
        details=ReleaseChangelog(old_version=old_version),
    )
    changelog_pr_path = dump_changelog_actions(
        changelog_pr_path,
        old_actions + [release_action],
    )
    git_tag = f"{tag_prefix}{new_version}"
    git_commit(
        repo_path,
        f"chore: pre-release commit for {git_tag}",
        tag=git_tag,
        push=push,
    )


def generate_api_workflow(api_input: GenerateApiInput) -> pkg_ctx | None:
    """Main API generation workflow"""
    if ctx := update_changelog_entries(api_input):
        sync_files(api_input, ctx)
        return ctx
    return None


def clean_old_entries(settings: PkgSettings):
    archive_old_actions(
        settings.changelog_dir,
        settings.changelog_cleanup_count,
        settings.changelog_keep_count,
    )
