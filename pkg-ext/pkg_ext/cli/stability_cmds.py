"""Stability commands: exp, ga, dep."""

import logging

import typer

from pkg_ext.changelog import DeprecatedAction, ExperimentalAction, GAAction
from pkg_ext.cli.options import option_replacement, option_target
from pkg_ext.cli.stability import (
    ParsedTarget,
    StabilityLevel,
    validate_group_is_ga,
    validate_target,
)
from pkg_ext.cli.workflows import create_stability_ctx
from pkg_ext.models import PublicGroups
from pkg_ext.settings import PkgSettings

logger = logging.getLogger(__name__)


def exp(
    ctx: typer.Context,
    target: str = option_target,
):
    """Mark target as experimental."""
    settings: PkgSettings = ctx.obj
    parsed = ParsedTarget.parse(target)
    pkg_ctx = create_stability_ctx(settings)
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


def ga(
    ctx: typer.Context,
    target: str = option_target,
):
    """Graduate target to GA (general availability)."""
    settings: PkgSettings = ctx.obj
    parsed = ParsedTarget.parse(target)
    pkg_ctx = create_stability_ctx(settings)
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


def dep(
    ctx: typer.Context,
    target: str = option_target,
    replacement: str | None = option_replacement,
):
    """Mark target as deprecated."""
    settings: PkgSettings = ctx.obj
    parsed = ParsedTarget.parse(target)
    pkg_ctx = create_stability_ctx(settings)
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
