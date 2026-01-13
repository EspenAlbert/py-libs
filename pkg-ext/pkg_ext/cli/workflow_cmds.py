"""Git workflow commands: pre_change, pre_commit, post_merge."""

import logging
from pathlib import Path

import typer
from zero_3rdparty.file_utils import ensure_parents_write_text
from zero_3rdparty.sections import get_comment_config, parse_sections, replace_sections

from pkg_ext import api_dumper
from pkg_ext.changelog import parse_changelog_actions
from pkg_ext.cli.options import (
    option_git_changes_since,
    option_group,
    option_pr,
    option_push,
    option_skip_clean,
    option_skip_docs,
)
from pkg_ext.cli.workflows import (
    GenerateApiInput,
    clean_old_entries,
    create_api_dump,
    create_ctx,
    create_stability_ctx,
    generate_api_workflow,
    post_merge_commit_workflow,
    sync_files,
    update_changelog_entries,
)
from pkg_ext.config import PKG_EXT_TOOL_NAME, load_project_config
from pkg_ext.generation import docs, example_gen, test_gen
from pkg_ext.git_usage import GitSince, head_merge_pr
from pkg_ext.models import PublicGroups
from pkg_ext.settings import PkgSettings
from pkg_ext.version_bump import read_current_version

logger = logging.getLogger(__name__)


def generate_examples_for_groups(
    settings: PkgSettings,
    groups: list[api_dumper.GroupDump],
) -> int:
    py_config = get_comment_config("file.py")
    count = 0
    for group_dump in groups:
        if not group_dump.symbols:
            continue
        path = settings.examples_file_path(group_dump.name)
        new_content = example_gen.generate_group_examples_file(
            group_dump, settings.pkg_import_name
        )
        if path.exists():
            existing = path.read_text()
            src_sections = {
                s.id: s.content
                for s in parse_sections(new_content, PKG_EXT_TOOL_NAME, py_config)
            }
            merged = replace_sections(
                existing, src_sections, PKG_EXT_TOOL_NAME, py_config
            )
            path.write_text(merged)
        else:
            ensure_parents_write_text(path, new_content)
        logger.info(f"Generated examples: {path}")
        count += 1
    return count


def generate_tests_for_groups(
    settings: PkgSettings,
    groups: list[api_dumper.GroupDump],
) -> int:
    py_config = get_comment_config("file.py")
    count = 0
    for group_dump in groups:
        testable_symbols = [
            s
            for s in group_dump.symbols
            if isinstance(s, api_dumper.FunctionDump | api_dumper.ClassDump)
        ]
        if not testable_symbols:
            logger.debug(f"Skipping group with no testable symbols: {group_dump.name}")
            continue
        path = settings.test_file_path(group_dump.name)
        new_content = test_gen.generate_group_test_file(
            group_dump, settings.pkg_import_name
        )
        if path.exists():
            existing = path.read_text()
            src_sections = {
                s.id: s.content
                for s in parse_sections(new_content, test_gen.TOOL_NAME, py_config)
            }
            merged = replace_sections(
                existing, src_sections, test_gen.TOOL_NAME, py_config
            )
            path.write_text(merged)
        else:
            ensure_parents_write_text(path, new_content)
        logger.info(f"Generated tests: {path}")
        count += 1
    return count


def generate_docs_for_pkg(
    settings: PkgSettings,
    output_dir: Path | None = None,
    filter_group: str | None = None,
) -> int:
    from pkg_ext import api_dumper

    pkg_ctx = create_stability_ctx(settings)
    groups = settings.parse_computed_public_groups(PublicGroups)
    version = str(read_current_version(pkg_ctx))
    refs = {ref.local_id: ref for ref in pkg_ctx.code_state.import_id_refs.values()}
    api_dump = api_dumper.dump_public_api(
        pkg_ctx.tool_state, groups, refs, settings.pkg_import_name, version
    )
    config = load_project_config(settings.state_dir)
    changelog_actions = parse_changelog_actions(settings.changelog_dir)
    docs_dir = output_dir or settings.docs_dir

    example_symbols: dict[str, set[str]] = {}
    groups_to_process = (
        [api_dump.get_group(filter_group)] if filter_group else api_dump.groups
    )
    for group_dump in groups_to_process:
        loaded = docs.load_examples_for_group(settings.pkg_import_name, group_dump.name)
        example_symbols[group_dump.name] = set(loaded.keys())

    output = docs.generate_docs(
        api_dump=api_dump,
        config=config,
        example_symbols=example_symbols,
        changelog_actions=changelog_actions,
        docs_dir=docs_dir,
        pkg_src_dir=settings.repo_root,
        load_examples=True,
    )
    if filter_group:
        dir_name = docs.group_dir_name(api_dump.get_group(filter_group))
        output.path_contents = {
            k: v for k, v in output.path_contents.items() if k.startswith(dir_name)
        }
    docs.copy_readme_as_index(settings.state_dir, docs_dir, settings.pkg_import_name)
    count = docs.write_docs_files(output, docs_dir)
    nav = docs.generate_mkdocs_nav(api_dump, settings.pkg_import_name)
    docs.write_mkdocs_yml(
        settings.mkdocs_yml, settings.pkg_import_name, nav, config.mkdocs_skip_sections
    )
    return count


def post_merge(
    ctx: typer.Context,
    explicit_pr: int = option_pr,
    push: bool = option_push,
    skip_clean_old_entries: bool = option_skip_clean,
):
    settings: PkgSettings = ctx.obj
    settings.force_bot()
    pr = explicit_pr or head_merge_pr(Path(settings.repo_root))
    logger.info(f"pr found: {pr}")
    api_input = GenerateApiInput(
        settings=settings,
        git_changes_since=GitSince.NO_GIT_CHANGES,
        bump_version=True,
        create_tag=True,
        push=push,
        explicit_pr=pr,
    )
    pkg_ctx = create_ctx(api_input)
    sync_files(api_input, pkg_ctx)
    post_merge_commit_workflow(
        repo_path=settings.repo_root,
        changelog_dir_path=pkg_ctx.settings.changelog_dir,
        pr_number=pr,
        tag_prefix=settings.tag_prefix,
        old_version=pkg_ctx.run_state.old_version,
        new_version=pkg_ctx.run_state.new_version,
        push=push,
    )
    if not skip_clean_old_entries:
        clean_old_entries(settings)


def pre_change(
    ctx: typer.Context,
    group: str | None = option_group,
    git_changes_since: GitSince = option_git_changes_since,
):
    """Handle new symbols then generate examples and tests."""
    settings: PkgSettings = ctx.obj
    api_input = GenerateApiInput(
        settings=settings,
        git_changes_since=git_changes_since,
        bump_version=False,
        create_tag=False,
        push=False,
    )
    if not update_changelog_entries(api_input):
        return
    api_dump = create_api_dump(settings)
    groups = [api_dump.get_group(group)] if group else api_dump.groups
    examples_count = generate_examples_for_groups(settings, groups)
    tests_count = generate_tests_for_groups(settings, groups)
    total = examples_count + tests_count
    logger.info(
        f"Generated {total} files ({examples_count} examples, {tests_count} tests)"
    )


def pre_commit(
    ctx: typer.Context,
    git_changes_since: GitSince = option_git_changes_since,
    skip_docs: bool = option_skip_docs,
):
    """Update changelog and regenerate docs (bot mode, writes to -dev files)."""
    settings: PkgSettings = ctx.obj
    settings.force_bot()
    settings.dev_mode = True

    api_input = GenerateApiInput(
        settings=settings,
        git_changes_since=git_changes_since,
        bump_version=False,
        create_tag=False,
        push=False,
    )
    if not generate_api_workflow(api_input):
        raise typer.Exit(1)

    if skip_docs:
        logger.info("Skipped docs regeneration")
        return

    count = generate_docs_for_pkg(settings)
    logger.info(f"Regenerated {count} doc files")
