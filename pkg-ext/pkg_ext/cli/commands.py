"""CLI commands for pkg-ext."""

import logging
from pathlib import Path

import typer
from model_lib.serialize import dump
from typer import Typer
from zero_3rdparty.file_utils import ensure_parents_write_text
from zero_3rdparty.sections import get_comment_config, parse_sections, replace_sections

from pkg_ext import api_dumper
from pkg_ext.changelog import (
    DeprecatedAction,
    ExperimentalAction,
    GAAction,
    ReleaseAction,
    parse_changelog,
    parse_changelog_actions,
)
from pkg_ext.changelog.write_changelog_md import read_changelog_section
from pkg_ext.cli.options import (
    option_bump_version,
    option_create_tag,
    option_git_changes_since,
    option_pr,
    option_push,
)
from pkg_ext.cli.stability import (
    ParsedTarget,
    StabilityLevel,
    validate_group_is_ga,
    validate_target,
)
from pkg_ext.cli.workflows import (
    GenerateApiInput,
    clean_old_entries,
    create_ctx,
    generate_api_workflow,
    parse_pkg_code_state,
    post_merge_commit_workflow,
    sync_files,
    update_changelog_entries,
)
from pkg_ext.config import PKG_EXT_TOOL_NAME, load_project_config
from pkg_ext.context import pkg_ctx as PkgCtx
from pkg_ext.generation import docs, example_gen, test_gen
from pkg_ext.git_usage import GitChanges, GitSince, head_merge_pr
from pkg_ext.models import PublicGroups
from pkg_ext.settings import PkgSettings, pkg_settings
from pkg_ext.version_bump import read_current_version

logger = logging.getLogger(__name__)
app = Typer(name="pkg-ext", help="Generate public API for a package and more!")


def resolve_repo_root(cwd: Path) -> Path:
    for path in [cwd] + list(cwd.parents):
        if (path / ".git").exists():
            return path
    raise ValueError(f"Repository root not found starting from {cwd}")


def is_package_dir(path: Path) -> bool:
    return path.is_dir() and (path / "__init__.py").exists()


def resolve_pkg_path_str(cwd: Path, repo_root: Path) -> str:
    if is_package_dir(cwd):
        return str(cwd.relative_to(repo_root))

    for item in cwd.iterdir():
        if is_package_dir(item):
            return str(item.relative_to(repo_root))

    current = cwd
    for parent in cwd.parents:
        if parent == repo_root:
            break
        if is_package_dir(parent):
            return str(current.relative_to(repo_root))
    raise ValueError(f"No package directory found starting from {cwd}")


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    pkg_path_str: str | None = typer.Option(
        None,
        "-p",
        "--path",
        "--pkg-path",
        help="Path to the package directory (auto-detected if not provided), expecting {pkg_path}/**/__init__.py to exist",
    ),
    repo_root: Path | None = typer.Option(
        None,
        help="Repository root directory (auto-detected from .git if not provided)",
    ),
    is_bot: bool = typer.Option(
        False,
        "--is-bot",
        envvar="PKG_EXT_IS_BOT",
        help="For CI to avoid any prompt hanging or accidental defaults made or to check for no more manual changes",
    ),
    skip_open: bool | None = typer.Option(
        None,
        "--skip-open",
        envvar="PKG_EXT_SKIP_OPEN",
        help="Skip opening files in editor. Uses user config or env var if not set explicitly.",
    ),
    tag_prefix: str | None = typer.Option(
        None,
        "--tag-prefix",
        envvar="PKG_EXT_TAG_PREFIX",
        help="{tag_prefix}{version} used in the git tag. Uses project config or env var if not set.",
    ),
):  # sourcery skip: raise-from-previous-error
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()
    if repo_root is None:
        try:
            resolved_repo_root = resolve_repo_root(Path.cwd())
        except ValueError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1)
    else:
        resolved_repo_root = repo_root

    if pkg_path_str is not None:
        candidate = resolved_repo_root / pkg_path_str
        if not is_package_dir(candidate):
            pkg_path_str = resolve_pkg_path_str(candidate, resolved_repo_root)

    if pkg_path_str is None:
        pkg_path_str = resolve_pkg_path_str(Path.cwd(), resolved_repo_root)

    ctx.obj = pkg_settings(
        repo_root=resolved_repo_root,
        is_bot=is_bot,
        pkg_path=pkg_path_str,
        skip_open_in_editor=skip_open,
        tag_prefix=tag_prefix,
    )


@app.command()
def post_merge(
    ctx: typer.Context,
    explicit_pr: int = option_pr,
    push: bool = option_push,
    skip_clean_old_entries: bool = typer.Option(
        False,
        "--skip-clean",
    ),
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


@app.command()
def generate_api(
    ctx: typer.Context,
    git_changes_since: GitSince = option_git_changes_since,
    bump_version: bool = option_bump_version,
    create_tag: bool = option_create_tag,
    push: bool = option_push,
    explicit_pr: int = option_pr,
    dump_groups: bool = typer.Option(
        False, "--dump-groups", help="Regenerate .groups.yaml with merged config data"
    ),
):
    settings: PkgSettings = ctx.obj
    if dump_groups:
        groups = settings.parse_computed_public_groups(PublicGroups)
        config = load_project_config(settings.repo_root)
        groups.merge_config(config)
        groups.write()
        logger.info(f"Wrote groups to {groups.storage_path}")
        return
    api_input = GenerateApiInput(
        settings=settings,
        git_changes_since=git_changes_since,
        bump_version=bump_version,
        create_tag=create_tag,
        push=push,
        explicit_pr=explicit_pr,
    )
    if pkg_ctx := generate_api_workflow(api_input):
        if api_input.create_tag:
            post_merge_commit_workflow(
                repo_path=settings.repo_root,
                changelog_dir_path=pkg_ctx.settings.changelog_dir,
                pr_number=explicit_pr or pkg_ctx.git_changes.current_pr,
                tag_prefix=settings.tag_prefix,
                old_version=pkg_ctx.run_state.old_version,
                new_version=pkg_ctx.run_state.new_version,
                push=push,
            )


def find_release_action(changelog_dir: Path, version: str) -> ReleaseAction:
    for changelog_action in parse_changelog_actions(changelog_dir):
        if (
            isinstance(changelog_action, ReleaseAction)
            and changelog_action.name == version
        ):
            pr = changelog_action.pr
            assert pr, f"found changelog action: {changelog_action} but pr missing"
            return changelog_action
    raise ValueError(f"couldn't find a release for {version}")


@app.command()
def release_notes(
    ctx: typer.Context,
    tag_name: str = typer.Option(..., "--tag", help="tag to find release notes for"),
):
    settings: PkgSettings = ctx.obj
    version = tag_name.removeprefix(settings.tag_prefix)
    action = find_release_action(settings.changelog_dir, version)
    content = read_changelog_section(
        settings.changelog_md.read_text(),
        old_version=action.old_version,
        new_version=action.name,
    )
    output_file = settings.repo_root / f"dist/{tag_name}.changelog.md"
    ensure_parents_write_text(output_file, content)


def _create_stability_ctx(settings: PkgSettings) -> PkgCtx:
    code_state = parse_pkg_code_state(settings)
    tool_state, extra_actions = parse_changelog(settings, code_state)
    return PkgCtx(
        settings=settings,
        tool_state=tool_state,
        code_state=code_state,
        git_changes=GitChanges.empty(),
        _actions=extra_actions,
    )


@app.command()
def exp(
    ctx: typer.Context,
    target: str = typer.Option(
        ..., "--target", "-t", help="Target: group | group.symbol | group.symbol.arg"
    ),
):
    """Mark target as experimental."""
    settings: PkgSettings = ctx.obj
    parsed = ParsedTarget.parse(target)
    pkg_ctx = _create_stability_ctx(settings)
    groups = settings.parse_computed_public_groups(PublicGroups)
    validate_target(parsed, pkg_ctx.code_state, groups)
    if parsed.level == StabilityLevel.arg:
        validate_group_is_ga(parsed, pkg_ctx.tool_state)
    match parsed.level:
        case StabilityLevel.group:
            action = ExperimentalAction(
                name=parsed.group, target=parsed.as_stability_target()
            )
        case StabilityLevel.symbol:
            action = ExperimentalAction(
                name=parsed.symbol_name,
                target=parsed.as_stability_target(),
                group=parsed.group,
            )
        case StabilityLevel.arg:
            action = ExperimentalAction(
                name=parsed.arg_name,
                target=parsed.as_stability_target(),
                parent=parsed.parent,
            )
    with pkg_ctx:
        pkg_ctx.add_changelog_action(action)
    logger.info(f"Created experimental action in {pkg_ctx.changelog_path}")


@app.command()
def ga(
    ctx: typer.Context,
    target: str = typer.Option(
        ..., "--target", "-t", help="Target: group | group.symbol | group.symbol.arg"
    ),
):
    """Graduate target to GA (general availability)."""
    settings: PkgSettings = ctx.obj
    parsed = ParsedTarget.parse(target)
    pkg_ctx = _create_stability_ctx(settings)
    groups = settings.parse_computed_public_groups(PublicGroups)
    validate_target(parsed, pkg_ctx.code_state, groups)
    match parsed.level:
        case StabilityLevel.group:
            action = GAAction(name=parsed.group, target=parsed.as_stability_target())
        case StabilityLevel.symbol:
            action = GAAction(
                name=parsed.symbol_name,
                target=parsed.as_stability_target(),
                group=parsed.group,
            )
        case StabilityLevel.arg:
            action = GAAction(
                name=parsed.arg_name,
                target=parsed.as_stability_target(),
                parent=parsed.parent,
            )
    with pkg_ctx:
        pkg_ctx.add_changelog_action(action)
    logger.info(f"Created GA action in {pkg_ctx.changelog_path}")


@app.command()
def dep(
    ctx: typer.Context,
    target: str = typer.Option(
        ..., "--target", "-t", help="Target: group | group.symbol | group.symbol.arg"
    ),
    replacement: str | None = typer.Option(
        None, "--replacement", "-r", help="Replacement suggestion"
    ),
):
    """Mark target as deprecated."""
    settings: PkgSettings = ctx.obj
    parsed = ParsedTarget.parse(target)
    pkg_ctx = _create_stability_ctx(settings)
    groups = settings.parse_computed_public_groups(PublicGroups)
    validate_target(parsed, pkg_ctx.code_state, groups)
    if parsed.level == StabilityLevel.arg:
        validate_group_is_ga(parsed, pkg_ctx.tool_state)
    match parsed.level:
        case StabilityLevel.group:
            action = DeprecatedAction(
                name=parsed.group,
                target=parsed.as_stability_target(),
                replacement=replacement,
            )
        case StabilityLevel.symbol:
            action = DeprecatedAction(
                name=parsed.symbol_name,
                target=parsed.as_stability_target(),
                group=parsed.group,
                replacement=replacement,
            )
        case StabilityLevel.arg:
            action = DeprecatedAction(
                name=parsed.arg_name,
                target=parsed.as_stability_target(),
                parent=parsed.parent,
                replacement=replacement,
            )
    with pkg_ctx:
        pkg_ctx.add_changelog_action(action)
    logger.info(f"Created deprecated action in {pkg_ctx.changelog_path}")


def _create_api_dump(settings: PkgSettings) -> api_dumper.PublicApiDump:
    pkg_ctx = _create_stability_ctx(settings)
    groups = settings.parse_computed_public_groups(PublicGroups)
    version = str(read_current_version(pkg_ctx))
    refs = {ref.local_id: ref for ref in pkg_ctx.code_state.all_refs}
    return api_dumper.dump_public_api(
        pkg_ctx.tool_state, groups, refs, settings.pkg_import_name, version
    )


def _generate_examples_for_groups(
    settings: PkgSettings,
    groups: list[api_dumper.GroupDump],
) -> int:
    py_config = get_comment_config(".py")
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


def _generate_tests_for_groups(
    settings: PkgSettings,
    groups: list[api_dumper.GroupDump],
) -> int:
    py_config = get_comment_config(".py")
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


@app.command()
def dump_api(
    ctx: typer.Context,
    output: Path | None = typer.Option(None, "-o", "--output", help="Output file path"),
    dev: bool = typer.Option(
        False, "--dev", help="Write to -dev file (gitignored for local comparison)"
    ),
):
    """Dump public API to YAML for diffing and breaking change detection."""
    settings: PkgSettings = ctx.obj
    api_dump = _create_api_dump(settings)
    if output is None:
        stem = f"{settings.pkg_import_name}.api"
        if dev:
            stem = f"{stem}-dev"
        output = settings.state_dir / f"{stem}.yaml"
    yaml_text = dump(api_dump.model_dump(exclude_none=True), "yaml")
    ensure_parents_write_text(output, yaml_text)
    logger.info(f"API dump written to {output}")


@app.command()
def pre_change(
    ctx: typer.Context,
    group: str | None = typer.Option(
        None, "-g", "--group", help="Generate for specific group only"
    ),
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
    api_dump = _create_api_dump(settings)
    groups = [api_dump.get_group(group)] if group else api_dump.groups
    examples_count = _generate_examples_for_groups(settings, groups)
    tests_count = _generate_tests_for_groups(settings, groups)
    total = examples_count + tests_count
    logger.info(
        f"Generated {total} files ({examples_count} examples, {tests_count} tests)"
    )


def _generate_docs_for_pkg(
    settings: PkgSettings,
    output_dir: Path | None = None,
    filter_group: str | None = None,
) -> int:
    """Generate docs for package. Returns file count."""
    pkg_ctx = _create_stability_ctx(settings)
    groups = settings.parse_computed_public_groups(PublicGroups)
    version = str(read_current_version(pkg_ctx))
    refs = {ref.local_id: ref for ref in pkg_ctx.code_state.all_refs}
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


@app.command()
def pre_commit(
    ctx: typer.Context,
    git_changes_since: GitSince = option_git_changes_since,
    skip_docs: bool = typer.Option(False, "--skip-docs", help="Skip doc regeneration"),
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

    count = _generate_docs_for_pkg(settings)
    logger.info(f"Regenerated {count} doc files")


@app.command()
def gen_examples(
    ctx: typer.Context,
    group: str | None = typer.Option(
        None, "-g", "--group", help="Generate for specific group only"
    ),
):
    """Generate example files for public API functions."""
    settings: PkgSettings = ctx.obj
    api_dump = _create_api_dump(settings)
    groups = [api_dump.get_group(group)] if group else api_dump.groups
    _generate_examples_for_groups(settings, groups)


@app.command()
def gen_tests(
    ctx: typer.Context,
    group: str | None = typer.Option(
        None, "-g", "--group", help="Generate for specific group only"
    ),
):
    """Generate parameterized test files from examples."""
    settings: PkgSettings = ctx.obj
    api_dump = _create_api_dump(settings)
    groups = [api_dump.get_group(group)] if group else api_dump.groups
    _generate_tests_for_groups(settings, groups)


@app.command(name="docs")
def gen_docs(
    ctx: typer.Context,
    output_dir: Path | None = typer.Option(
        None, "-o", "--output-dir", help="Output directory (default: docs/)"
    ),
    group: str | None = typer.Option(
        None, "-g", "--group", help="Generate for specific group only"
    ),
):
    """Generate documentation from public API."""
    settings: PkgSettings = ctx.obj
    count = _generate_docs_for_pkg(settings, output_dir=output_dir, filter_group=group)
    docs_dir = output_dir or settings.docs_dir
    logger.info(f"Generated {count} doc files in {docs_dir}")
