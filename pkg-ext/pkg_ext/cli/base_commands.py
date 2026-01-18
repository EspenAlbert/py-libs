"""CLI app setup and main callback with command registration."""

from pathlib import Path

import typer
from typer import Typer

from pkg_ext.settings import pkg_settings

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
        help="Path to the package directory (auto-detected if not provided)",
    ),
    repo_root: Path | None = typer.Option(
        None,
        help="Repository root directory (auto-detected from .git if not provided)",
    ),
    is_bot: bool = typer.Option(
        False,
        "--is-bot",
        envvar="PKG_EXT_IS_BOT",
        help="For CI to avoid any prompt hanging or accidental defaults",
    ),
    skip_open: bool | None = typer.Option(
        None,
        "--skip-open",
        envvar="PKG_EXT_SKIP_OPEN",
        help="Skip opening files in editor",
    ),
    tag_prefix: str | None = typer.Option(
        None,
        "--tag-prefix",
        envvar="PKG_EXT_TAG_PREFIX",
        help="{tag_prefix}{version} used in the git tag",
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


# Register commands from other modules (imports must be after app creation to avoid circular imports)
from pkg_ext.cli.gen_cmds import (  # noqa: E402
    diff_api,
    dump_api,
    gen_docs,
    gen_examples,
    gen_tests,
)
from pkg_ext.cli.release_cmds import dump_groups, release_notes  # noqa: E402
from pkg_ext.cli.stability_cmds import dep, exp, ga  # noqa: E402
from pkg_ext.cli.workflow_cmds import (  # noqa: E402
    chore,
    post_merge,
    pre_change,
    pre_commit,
    promote,
)

app.command()(post_merge)
app.command()(pre_change)
app.command()(pre_commit)
app.command()(chore)
app.command()(promote)
app.command()(exp)
app.command()(ga)
app.command()(dep)
app.command()(gen_examples)
app.command()(gen_tests)
app.command(name="docs")(gen_docs)
app.command()(dump_api)
app.command()(diff_api)
app.command()(release_notes)
app.command()(dump_groups)
