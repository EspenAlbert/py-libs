from pathlib import Path

from ask_shell._internal._run import run_and_wait

_GIT_AUTHOR = (
    '--author="github-actions[bot] <github-actions[bot]@users.noreply.github.com>"'
)


def git_commit(
    repo_dir: Path,
    message: str,
    tag: str = "",
    push: bool = False,
    verify: bool = False,
):
    run_and_wait("git add .", cwd=repo_dir)
    verify_arg = "" if verify else " --no-verify"
    run_and_wait(f'git commit {_GIT_AUTHOR} -m "{message}"{verify_arg}', cwd=repo_dir)
    if tag:
        run_and_wait(f'git tag -a "{tag}" -m "{tag}"', cwd=repo_dir)
    if push:
        follow_tags = " --follow-tags" if tag else ""
        run_and_wait(f"git push{follow_tags}")
