import difflib

from rich.markdown import Markdown

from pkg_ext.gen_changelog import ChangelogAction, ChangelogActionType, CommitFix
from pkg_ext.git_state import GitCommit
from pkg_ext.models import pkg_ctx


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


def infer_group(changes: list[str]) -> str:
    raise NotImplementedError


def prompt_for_fix(
    sha: str, commit_message: str, prompt_context: list[str]
) -> CommitFix:
    # todo: prompt for decision to include/exclude/include_rephrase
    return CommitFix(
        short_sha=sha,
        message=commit_message,
        changelog_message=commit_message,
    )


def fix_changelog_action(commit: GitCommit, ctx: pkg_ctx) -> ChangelogAction[CommitFix]:
    tool_state = ctx.tool_state
    git_changes = ctx.git_changes
    assert git_changes
    pkg_changes = sorted(
        changed_path
        for changed_path in commit.file_changes
        if tool_state.is_pkg_relative(changed_path)
    )
    group = infer_group(pkg_changes)
    prompt_context = []
    for rel_path in pkg_changes:
        if not git_changes.has_change(rel_path):
            continue
        path = tool_state.full_path(rel_path)
        if not path.exists():
            continue
        new_content = path.read_text()
        old_content = git_changes.old_version(rel_path)
        prompt_context.extend(
            [
                f"### {rel_path} ###",
                py_diff(old_content, new_content),
            ]
        )
    commit_message = commit.message
    details = prompt_for_fix(commit.sha, commit_message, prompt_context)
    return ChangelogAction(
        name=group,
        action=ChangelogActionType.FIX,
        author=commit.author,
        details=details,
    )


def add_git_changes(ctx: pkg_ctx) -> None:
    git_changes = ctx.git_changes
    if git_changes is None:
        return
    commit_fix_prefixes = ctx.settings.commit_fix_prefixes
    tool_state = ctx.tool_state
    for commit in git_changes.commits:
        if tool_state.sha_processed(commit.sha):
            continue
        message = commit.message
        if not message.startswith(commit_fix_prefixes):
            continue
        commit_fix = fix_changelog_action(commit, ctx)
        ctx.add_changelog_action(commit_fix)


if __name__ == "__main__":
    from rich.console import Console

    original = "\n".join(f"original-{i}" for i in range(10))
    one = f"{original}\n\nline1\nline2\nline3\nline4"
    two = f"{original}\n\nline1\nline2 changed\nline3"

    Console().print(rich_diff(one, two))
