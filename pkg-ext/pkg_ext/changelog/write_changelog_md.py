import logging
import re
from collections import defaultdict
from pathlib import Path

from zero_3rdparty.datetime_utils import date_filename
from zero_3rdparty.file_utils import ensure_parents_write_text

from pkg_ext.changelog.actions import (
    BumpType,
    ChangelogAction,
    ChangelogActionType,
    CommitFixChangelog,
)
from pkg_ext.errors import NoPublicGroupMatch
from pkg_ext.models import PublicGroup, pkg_ctx

logger = logging.getLogger(__name__)
_header_regex = re.compile(r"^(?P<hashes>#{2,5})\s", re.M)


def _header_level(changelog_content: str, version: str) -> int | None:
    version_header_regex = re.compile(_header_regex.pattern + version, re.M)
    if header_match := version_header_regex.search(changelog_content):
        return len(header_match["hashes"])
    return None


def read_changelog_section(
    changelog_content: str, old_version: str, new_version: str
) -> str:
    old_version_header_regex = re.compile(_header_regex.pattern + old_version, re.M)
    new_version_header_regex = re.compile(_header_regex.pattern + new_version, re.M)
    if header_match := new_version_header_regex.search(changelog_content):
        section_end = -1
        if old_version and (
            old_match := old_version_header_regex.search(changelog_content)
        ):
            section_end = old_match.start()
        return changelog_content[header_match.start() : section_end].strip() + "\n"
    raise ValueError(f"unable to find {new_version} in changelog")


def _add_changelog_section(old_content: str, new_section: str, version: str) -> str:
    _header_start_regex = re.compile(_header_regex.pattern + version, re.M)
    if existing := _header_start_regex.search(old_content):
        dash_count = len(existing["hashes"])
        start_index = existing.start()
        for end_match in _header_regex.finditer(old_content, existing.end()):
            dash_count_end = len(end_match["hashes"])
            if dash_count != dash_count_end:
                continue
            end_index = end_match.end()
            break
        else:
            # no end match, this is the last header section
            return old_content[:start_index] + new_section
        return old_content[:start_index] + new_section + old_content[end_index:]
    if insert_point := next(
        (header_match.start() for header_match in _header_regex.finditer(old_content)),
        None,
    ):
        return (
            old_content[:insert_point]
            + new_section
            + "\n\n"
            + old_content[insert_point:]
        )
    else:
        return old_content + new_section  # no existing headers, appending to the end


def _commit_url(remote_url: str, sha: str) -> str:
    if remote_url:
        url = f"{remote_url}/commit/{sha}"
        return f"[{sha}]({url})"
    return f"({sha})"


def as_changelog_line(action: ChangelogAction, remote_url: str, ctx: pkg_ctx) -> str:
    match action:
        case ChangelogAction(
            type=ChangelogActionType.FIX,
            details=CommitFixChangelog(
                ignored=False,
                message=message,
                changelog_message=changelog_message,
                short_sha=sha,
            ),
        ):
            return f"{changelog_message or message} {_commit_url(remote_url, sha)}"
        case ChangelogAction(type=ChangelogActionType.EXPOSE, name=name):
            ref_symbol = ctx.code_state.ref_symbol(name)
            return f"New {ref_symbol.type} {name}"
    return ""


def _get_section_header_level(path: Path, version: str):
    section_header_level = 2
    if path.exists():
        if current_header_level := _header_level(path.read_text(), version):
            section_header_level = current_header_level
    return section_header_level


def _group_changelog_entries(
    ctx: pkg_ctx, actions: list[ChangelogAction], remote_url: str
) -> tuple[dict[str, list[str]], list[str]]:
    group_sections: dict[str, list[str]] = defaultdict(list)
    other_sections: list[str] = []
    for action in BumpType.sort_by_bump(actions):
        line = as_changelog_line(action, remote_url, ctx)
        try:
            group: PublicGroup = ctx.action_group(action)
            group_sections[group.name].append(line)
        except NoPublicGroupMatch:
            other_sections.append(line)
    return group_sections, other_sections


def _create_changelog_content(
    ctx: pkg_ctx, actions: list[ChangelogAction], old_version: str, new_version: str
) -> list[str]:
    git_changes = ctx.git_changes
    remote_url = git_changes.remote_url
    group_sections, other_sections = _group_changelog_entries(ctx, actions, remote_url)
    changelog_md: list[str] = []
    root_prefix = "#" * _get_section_header_level(
        ctx.settings.changelog_md, old_version
    )

    def add_section(header: str, lines: list[str], *, header_level=1) -> None:
        header_prefix = root_prefix + header_level * "#"
        changelog_md.append(f"{header_prefix} {header}")
        lines.append("")  # Include an extra line after a group
        changelog_md.extend(lines)

    if pr_url := git_changes.pr_url:
        pr_part = f" [#{git_changes.current_pr}]({pr_url})"
    else:
        pr_part = ""
    add_section(
        header=f"{new_version} {date_filename()}{pr_part}", lines=[], header_level=0
    )
    for group, lines in sorted(group_sections.items()):
        add_section(group.title(), [f"- {line}" for line in lines])
    if other_sections:
        add_section("Other Changes", [f"- {line}" for line in other_sections])
    return changelog_md


def write_changelog_md(ctx: pkg_ctx) -> Path:
    settings = ctx.settings
    path = settings.changelog_md
    unreleased = [
        action
        for action in ctx.pr_changelog_actions()
        if as_changelog_line(action, ctx.git_changes.remote_url, ctx)
    ]
    if not unreleased:
        return path
    old_version = ctx.run_state.old_version
    new_version = ctx.run_state.new_version
    if old_version == new_version:
        return path
    changelog_md = _create_changelog_content(
        ctx, unreleased, str(old_version), str(new_version)
    )
    path = ctx.settings.changelog_md
    if not path.exists():
        ensure_parents_write_text(path, "# Changelog\n\n")
    new_content = _add_changelog_section(
        path.read_text(), "\n".join(changelog_md), str(new_version)
    )
    path.write_text(new_content)
    return path
