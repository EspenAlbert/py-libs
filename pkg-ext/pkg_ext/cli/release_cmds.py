"""Release commands: release_notes, dump_groups."""

import logging
from pathlib import Path

import typer
from zero_3rdparty.file_utils import ensure_parents_write_text

from pkg_ext.changelog import MakePublicAction, ReleaseAction, parse_changelog_actions
from pkg_ext.changelog.write_changelog_md import read_changelog_section
from pkg_ext.cli.workflows import parse_pkg_code_state
from pkg_ext.config import load_project_config
from pkg_ext.models import PublicGroups
from pkg_ext.settings import PkgSettings

logger = logging.getLogger(__name__)


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


def dump_groups(ctx: typer.Context):
    """Regenerate .groups.yaml with merged config data and reconcile with changelog."""
    settings: PkgSettings = ctx.obj
    groups = settings.parse_computed_public_groups(PublicGroups)
    config = load_project_config(settings.repo_root)
    groups.merge_config(config)

    # Reconcile changelog MakePublicAction entries with code to find missing refs
    changelog_actions = parse_changelog_actions(settings.changelog_dir)
    code_state = parse_pkg_code_state(settings)
    named_refs = code_state.named_refs

    for action in changelog_actions:
        if not isinstance(action, MakePublicAction):
            continue
        # Check if this ref is already in owned_refs for this group
        group = groups.get_or_create_group(action.group)
        # Find ref in code by name
        if ref_state := named_refs.get(action.name):
            symbol = ref_state.symbol
            # Add to owned_refs if not already there
            if symbol.local_id not in group.owned_refs:
                group.owned_refs.add(symbol.local_id)
                group.owned_modules.add(symbol.module_path)
                logger.info(
                    f"Added missing ref {symbol.local_id} to group {action.group}"
                )

    groups.write()
    logger.info(f"Wrote groups to {groups.storage_path}")
