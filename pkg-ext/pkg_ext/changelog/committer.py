import difflib
from collections import Counter
from contextlib import suppress

from ask_shell._internal.rich_live import print_to_live
from rich.markdown import Markdown

from pkg_ext.changelog.actions import (
    ChangelogAction,
    ChangelogActionType,
    CommitFixChangelog,
)
from pkg_ext.errors import NoPublicGroupMatch
from pkg_ext.git_usage.state import GitCommit
from pkg_ext.interactive import (
    CommitFixAction,
    select_commit_fix,
    select_commit_rephrased,
    select_group_name,
)
from pkg_ext.models import PublicGroups, as_module_path, pkg_ctx


def py_diff(old: str, new: str) -> str:
    old_lines = old.splitlines()
    new_lines = new.splitlines()
    ndiff = list(difflib.ndiff(old_lines, new_lines))
    unified_diff = list(difflib.unified_diff(old_lines, new_lines))
    len_diffs = [
        (len(ndiff), ndiff),
        (len(unified_diff), unified_diff),
    ]
    _, diff = min(len_diffs)
    return "\n".join(diff)


def rich_diff(old: str, new: str) -> Markdown:
    diff = py_diff(old, new)
    return Markdown(
        f"""
```diff
{diff}
```"""
    )


def infer_group(groups: PublicGroups, changes: dict[str, str]) -> str:
    group_counts = Counter()
    for rel_path, diff in changes.items():
        with suppress(NoPublicGroupMatch):
            group = groups.matching_group_by_module_path(as_module_path(rel_path))
            group_counts[group.name] += len(diff.splitlines())
    if not group_counts:
        return ""
    return group_counts.most_common(1)[0][0]


def prompt_for_fix(
    sha: str, commit_message: str, prompt_text: str
) -> CommitFixChangelog:
    fix = CommitFixChangelog(
        short_sha=sha,
        message=commit_message,
        changelog_message=commit_message,
    )
    match select_commit_fix(prompt_text):
        case CommitFixAction.REPHRASE:
            fix.changelog_message = select_commit_rephrased(commit_message)
            fix.rephrased = True
        case CommitFixAction.EXCLUDE:
            fix.ignored = True
    return fix


def fix_changelog_action(
    commit: GitCommit, ctx: pkg_ctx
) -> ChangelogAction[CommitFixChangelog] | None:
    tool_state = ctx.tool_state
    git_changes = ctx.git_changes
    assert git_changes
    pkg_changes = sorted(
        changed_path
        for changed_path in commit.file_changes
        if tool_state.is_pkg_relative(changed_path)
    )
    if not pkg_changes:
        return None
    prompt_context = []
    diff_suffixes = ctx.settings.commit_fix_diff_suffixes
    diffs: dict[str, str] = {}
    for rel_path in pkg_changes:
        if not git_changes.has_change(rel_path) or not rel_path.endswith(diff_suffixes):
            continue
        path = tool_state.full_path(rel_path)
        if not path.exists():
            continue
        new_content = path.read_text()
        old_content = git_changes.old_version(rel_path)
        diffs[rel_path] = diff = py_diff(old_content, new_content)
        prompt_context.extend(
            [
                f"### {rel_path} ###",
                diff,
            ]
        )
    prompt_md = Markdown("\n".join(prompt_context))
    print_to_live(prompt_md)
    commit_message = commit.message
    commit_sha = commit.sha
    prompt_text = f"commit({commit_sha}): {commit_message}"
    groups = tool_state.groups
    group = infer_group(groups, diffs)
    public_group = select_group_name(
        f"select group for {prompt_text}", groups, default=group
    )
    group = public_group.name
    details = prompt_for_fix(commit_sha, commit_message, prompt_text)
    return ChangelogAction(
        name=group,
        type=ChangelogActionType.FIX,
        author=commit.author,
        details=details,
    )


def add_git_changes(ctx: pkg_ctx) -> None:
    git_changes = ctx.git_changes
    commit_fix_prefixes = ctx.settings.commit_fix_prefixes
    tool_state = ctx.tool_state
    for commit in git_changes.commits:
        if tool_state.sha_processed(commit.sha):
            continue
        message = commit.message
        if not message.startswith(commit_fix_prefixes):
            continue
        if commit_fix := fix_changelog_action(commit, ctx):
            ctx.add_changelog_action(commit_fix)


if __name__ == "__main__":
    from rich.console import Console

    original = "\n".join(f"original-{i}" for i in range(10))
    one = f"{original}\n\nline1\nline2\nline3\nline4"
    two = f"{original}\n\nline1\nline2 changed\nline3"

    Console().print(rich_diff(one, two))
