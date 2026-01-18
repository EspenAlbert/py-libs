"""Git workflow commands: pre_change, pre_commit, post_merge."""

import logging
from pathlib import Path
from typing import cast

import typer
from git import InvalidGitRepositoryError, Repo
from zero_3rdparty.file_utils import ensure_parents_write_text
from zero_3rdparty.sections import get_comment_config, parse_sections, replace_sections

from pkg_ext import api_dumper, py_format
from pkg_ext.changelog import parse_changelog_actions
from pkg_ext.cli.options import (
    option_full,
    option_git_changes_since,
    option_group,
    option_pr,
    option_push,
    option_skip_clean,
    option_skip_dirty_check,
    option_skip_docs,
    option_skip_fix_commits,
)
from pkg_ext.cli.workflows import (
    GenerateApiInput,
    clean_old_entries,
    create_api_dump,
    create_ctx,
    create_release_action,
    create_stability_ctx,
    generate_api_workflow,
    post_merge_commit_workflow,
    run_api_diff,
    sync_files,
    update_changelog_entries,
    write_api_dump,
)
from pkg_ext.config import PKG_EXT_TOOL_NAME, ProjectConfig, load_project_config
from pkg_ext.generation import docs, docs_mkdocs, example_gen, test_gen
from pkg_ext.git_usage import GitSince, find_pr_info_or_none, head_merge_pr
from pkg_ext.models import PublicGroups
from pkg_ext.settings import PkgSettings
from pkg_ext.version_bump import read_current_version

logger = logging.getLogger(__name__)


def get_generated_file_paths(settings: PkgSettings) -> list[Path]:
    """Return paths of all generated files (relative to repo root)."""
    repo_root = settings.repo_root
    paths = [
        settings.public_groups_path.relative_to(repo_root),
        settings.changelog_md.relative_to(repo_root),
        settings.init_path.relative_to(repo_root),
    ]
    if settings.warnings_file_path.exists():
        paths.append(settings.warnings_file_path.relative_to(repo_root))
    groups = settings.parse_computed_public_groups(PublicGroups)
    for group in groups.groups_no_root:
        group_path = settings.group_module_path(group.name)
        paths.append(group_path.relative_to(repo_root))
    docs_dir = settings.docs_dir
    if docs_dir.exists():
        for md_file in docs_dir.rglob("*.md"):
            paths.append(md_file.relative_to(repo_root))
    return paths


def check_generated_files_dirty(settings: PkgSettings) -> list[str]:
    """Check if generated files are modified (unstaged) or untracked."""
    try:
        repo = Repo(settings.repo_root)
    except InvalidGitRepositoryError:
        logger.debug("Not a git repo, skipping dirty check")
        return []
    generated_paths = {str(p) for p in get_generated_file_paths(settings)}
    modified = [
        f"{item.a_path} (modified)"
        for item in repo.index.diff(None)
        if item.a_path in generated_paths
    ]
    untracked = [
        f"{path} (untracked)"
        for path in repo.untracked_files
        if path in generated_paths
    ]
    return modified + untracked


def generate_examples_for_groups(
    settings: PkgSettings,
    groups: list[api_dumper.GroupDump],
    config: ProjectConfig | None = None,
) -> int:
    py_config = get_comment_config("file.py")
    config = config or load_project_config(settings.repo_root)
    generated_paths: list[Path] = []
    for group_dump in groups:
        if not (filtered := config.filter_group_for_examples(group_dump)):
            logger.debug(f"Skipping examples for {group_dump.name}: no symbols enabled")
            continue
        path = settings.examples_file_path(filtered.name)
        new_content = example_gen.generate_group_examples_file(
            filtered, settings.pkg_import_name
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
        generated_paths.append(path)
    py_format.format_python_files(generated_paths, settings.format_command)
    return len(generated_paths)


def generate_tests_for_groups(
    settings: PkgSettings,
    groups: list[api_dumper.GroupDump],
    config: ProjectConfig | None = None,
) -> int:
    py_config = get_comment_config("file.py")
    config = config or load_project_config(settings.repo_root)
    generated_paths: list[Path] = []
    for group_dump in groups:
        if not (filtered := config.filter_group_for_examples(group_dump)):
            logger.debug(
                f"Skipping tests for {group_dump.name}: no symbols with examples"
            )
            continue
        # Further filter to only testable types (functions/classes)
        testable = [
            s
            for s in filtered.symbols
            if isinstance(s, api_dumper.FunctionDump | api_dumper.ClassDump)
        ]
        if not testable:
            continue
        filtered = api_dumper.GroupDump(
            name=filtered.name,
            stability=filtered.stability,
            symbols=cast(list[api_dumper.SymbolDump], testable),
        )
        path = settings.test_file_path(filtered.name)
        new_content = test_gen.generate_group_test_file(
            filtered, settings.pkg_import_name
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
        generated_paths.append(path)
    py_format.format_python_files(generated_paths, settings.format_command)
    return len(generated_paths)


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
    docs_mkdocs.copy_readme_as_index(
        settings.state_dir, docs_dir, settings.pkg_import_name
    )
    count = docs_mkdocs.write_docs_files(output, docs_dir)
    nav = docs_mkdocs.generate_mkdocs_nav(api_dump, settings.pkg_import_name)
    docs_mkdocs.write_mkdocs_yml(
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
    write_api_dump(settings, dev_mode=False)
    # Create ReleaseAction first so docs generation has correct since_version
    create_release_action(
        changelog_dir_path=pkg_ctx.settings.changelog_dir,
        pr_number=pr,
        old_version=pkg_ctx.run_state.old_version,
        new_version=pkg_ctx.run_state.new_version,
    )
    count = generate_docs_for_pkg(settings)
    logger.info(f"Regenerated {count} doc files with release version")
    # Now commit with docs that have correct since_version
    post_merge_commit_workflow(
        repo_path=settings.repo_root,
        tag_prefix=settings.tag_prefix,
        new_version=pkg_ctx.run_state.new_version,
        push=push,
    )
    if not skip_clean_old_entries:
        clean_old_entries(settings)


def pre_change(
    ctx: typer.Context,
    group: str | None = option_group,
    git_changes_since: GitSince = option_git_changes_since,
    skip_fix_commits: bool = option_skip_fix_commits,
    full: bool = option_full,
    skip_docs: bool = option_skip_docs,
):
    """Handle new symbols then generate examples and tests."""
    settings: PkgSettings = ctx.obj
    api_input = GenerateApiInput(
        settings=settings,
        git_changes_since=git_changes_since,
        bump_version=False,
        create_tag=False,
        push=False,
        skip_fix_commits=skip_fix_commits,
    )
    pkg_ctx = update_changelog_entries(api_input)
    if not pkg_ctx:
        return
    api_dump = create_api_dump(settings)
    groups = [api_dump.get_group(group)] if group else api_dump.groups
    examples_count = generate_examples_for_groups(settings, groups)
    tests_count = generate_tests_for_groups(settings, groups)
    total = examples_count + tests_count
    logger.info(
        f"Generated {total} files ({examples_count} examples, {tests_count} tests)"
    )

    if not full:
        return
    settings.dev_mode = True
    sync_files(api_input, pkg_ctx)
    if skip_docs:
        logger.info("Skipped docs regeneration")
    else:
        count = generate_docs_for_pkg(settings)
        logger.info(f"Regenerated {count} doc files")
    write_api_dump(settings, dev_mode=True)
    pr_info = find_pr_info_or_none(settings.repo_root)
    run_api_diff(settings, pr_info.pr_number if pr_info else 0)


def pre_commit(
    ctx: typer.Context,
    git_changes_since: GitSince = option_git_changes_since,
    skip_docs: bool = option_skip_docs,
    skip_dirty_check: bool = option_skip_dirty_check,
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
    else:
        count = generate_docs_for_pkg(settings)
        logger.info(f"Regenerated {count} doc files")

    write_api_dump(settings, dev_mode=True)
    pr_info = find_pr_info_or_none(settings.repo_root)
    run_api_diff(settings, pr_info.pr_number if pr_info else 0)

    if skip_dirty_check:
        return
    if dirty_files := check_generated_files_dirty(settings):
        logger.error("Generated files have unstaged changes:")
        for f in dirty_files:
            logger.error(f"  {f}")
        logger.error("Run `git add` on these files before committing.")
        raise typer.Exit(1)
