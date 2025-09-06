import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from functools import total_ordering
from pathlib import Path
from typing import ClassVar, Iterable, Self

from ask_shell._internal._run import run_and_wait
from git import Commit, Git, GitCommandError, InvalidGitRepositoryError, Repo
from model_lib import utc_datetime
from pydantic import BaseModel, model_validator

from pkg_ext.errors import RemoteURLNotFound
from pkg_ext.git_url import read_remote_url

logger = logging.getLogger(__name__)


class GitSince(StrEnum):
    NO_GIT_CHANGES = "no_git_changes"
    LAST_GIT_TAG = "last_git_tag"
    LAST_REMOTE_SHA = "last_remote_sha"
    LAST_REMOTE_BRANCH = "last_remote_branch"


def _file_content(git: Git, commit: str, file: str) -> str:
    try:
        return git.show(f"{commit}:{file}")
    except GitCommandError as e:
        msg = e.stderr
        if "does not exist" in msg or "exists on disk, but not in" in msg:
            return ""
        if "'fatal: bad object" in msg:
            # most likely a submodule
            return ""
        raise e


@dataclass
class GitState:
    def previous_version(self, rel_path_repo: str) -> str:
        raise NotImplementedError


class GitChangesInput(BaseModel):
    repo_path: Path
    since: GitSince


@total_ordering
class GitCommit(BaseModel):
    SHA_MAX_LEN: ClassVar[int] = 6
    file_changes: set[str]
    author: str
    message: str
    ts: utc_datetime
    sha: str

    @model_validator(mode="after")
    def shorten_sha(self) -> Self:
        self.sha = self.sha[: self.SHA_MAX_LEN]
        return self

    def __lt__(self, other) -> bool:
        if not isinstance(other, GitCommit):
            raise TypeError
        return self.ts < other.ts


# Merge pull request #26 from EspenAlbert/pkg-ext-standalone
_merge_message_regex = re.compile(r"Merge pull request #(\d+)")


def pr_number_from_url(url: str) -> int:
    """
    >>> pr_number_from_url('https://github.com/EspenAlbert/py-libs/pull/28')
    28
    """
    last_path = url.rstrip("/").split("/")[-1]
    if last_path.isdigit():
        return int(last_path)
    raise ValueError(f"pr url invalid format, expected ending with number, got {url}")


@dataclass
class GitChanges:
    commits: list[GitCommit]
    files_changed: set[str]
    git: Git | None
    start_sha: str
    end_sha: str
    current_pr: int
    remote_url: str

    @classmethod
    def empty(cls) -> Self:
        return cls(
            commits=[],
            files_changed=set(),
            git=None,
            start_sha="",
            end_sha="",
            current_pr=1,
            remote_url="",
        )

    @property
    def pr_url(self) -> str:
        if not self.remote_url:
            return ""
        return f"{self.remote_url}/pull{self.current_pr}"

    def has_change(self, rel_path_repo: str) -> bool:
        return rel_path_repo in self.files_changed

    def old_version(self, rel_path_repo: str) -> str:
        assert self.has_change(rel_path_repo), f"file hasn't changed: {rel_path_repo}"
        assert self.git, "git repo must be set for reading the old version"
        return _file_content(self.git, self.start_sha, rel_path_repo)


def last_merge_pr(
    commits: Iterable[GitCommit], after_ts: utc_datetime | None = None
) -> int | None:
    after_ts = after_ts or datetime.fromtimestamp(0, tz=timezone.utc)
    for commit in sorted(commits, reverse=True):
        if commit.ts < after_ts:
            return None
        if merge_match := _merge_message_regex.match(commit.message):
            return int(merge_match[1])
    return None


def _last_merge_pr_repo(repo: Repo, head_sha: str) -> int | None:
    for commit in repo.iter_commits(rev=head_sha):
        message = str(commit.message.strip())
        if merge_match := _merge_message_regex.match(message):
            return int(merge_match[1])


class _NoGitChangesError(Exception):
    pass


def solve_since_sha(repo: Repo, repo_path: Path, since: GitSince) -> Commit:
    if since == GitSince.LAST_GIT_TAG:
        output = run_and_wait(
            "git describe --tags --abbrev=0", cwd=repo_path
        ).stdout_one_line
        return repo.commit(output)
    elif since == GitSince.NO_GIT_CHANGES:
        raise _NoGitChangesError
    else:
        raise NotImplementedError


def find_pr_url(repo_path: Path) -> str:
    result = run_and_wait(
        "gh pr view --json url", cwd=repo_path, allow_non_zero_exit=True
    )
    if not result.clean_complete:
        return ""
    result_json = result.parse_output(dict)
    return result_json.get("url", "")


def _parse_changes(
    repo: Repo, start_sha: str, head_sha: str
) -> tuple[list[GitCommit], set[str]]:
    commits: list[GitCommit] = []
    files_changed: set[str] = set()
    for commit in repo.iter_commits(rev=head_sha):
        if commit.hexsha.startswith(start_sha):
            break
        commit_files = {str(file) for file in commit.stats.files}
        files_changed |= commit_files
        commits.append(
            GitCommit(
                author=commit.author.name or "",
                message=str(commit.message.strip()),
                ts=commit.committed_datetime,  # type: ignore
                sha=commit.hexsha,
                file_changes=commit_files,
            )
        )
    assert commits, f"No commit messages found between {start_sha} and {head_sha}"
    return commits, files_changed


def find_git_changes(event: GitChangesInput) -> GitChanges:
    repo_path = event.repo_path
    try:
        repo = Repo(repo_path)
        head_sha = repo.head.commit.hexsha
    except InvalidGitRepositoryError as e:
        logger.warning(f"not a git repo @ {repo_path}: {e!r}")
        return GitChanges.empty()
    try:
        start_commit = solve_since_sha(repo, event.repo_path, event.since)
        start_sha = start_commit.hexsha
        commits, files_changed = _parse_changes(repo, start_sha, head_sha)
    except _NoGitChangesError:
        commits = []
        files_changed: set[str] = set()
        start_sha = ""
    try:
        remote_url = read_remote_url(event.repo_path)
    except RemoteURLNotFound as e:
        logger.warning(repr(e))
        remote_url = ""
    if pr_url := find_pr_url(event.repo_path):
        pr_number = pr_number_from_url(pr_url)
    else:
        prev_pr_number = _last_merge_pr_repo(repo, head_sha) or 0
        pr_number = prev_pr_number + 1
    return GitChanges(
        commits=sorted(commits),
        files_changed=files_changed,
        git=repo.git,
        start_sha=start_sha,
        end_sha=head_sha,
        remote_url=remote_url,
        current_pr=pr_number,
    )
