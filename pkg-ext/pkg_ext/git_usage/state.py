from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from functools import total_ordering
from pathlib import Path
from typing import Any, ClassVar, Iterable, Self

from ask_shell._internal._run import run_and_wait
from git import Commit, Git, GitCommandError, InvalidGitRepositoryError, Repo
from model_lib import utc_datetime
from model_lib.model_base import Entity
from pydantic import BaseModel, Field, model_validator

from pkg_ext.errors import RemoteURLNotFound
from pkg_ext.git_usage.url import read_remote_url

logger = logging.getLogger(__name__)


class GitSince(StrEnum):
    NO_GIT_CHANGES = "no_git_changes"
    LAST_GIT_TAG = "last_git_tag"
    PR_BASE_BRANCH = "pr_base_branch"
    DEFAULT = "default"  # use first pr_base_branch and if not last_git_tag


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


class PRInfo(Entity):
    base_ref_name: str = Field(alias="baseRefName")
    base_ref_oid: str = Field(alias="baseRefOid")
    url: str

    @property
    def pr_number(self) -> int:
        return pr_number_from_url(self.url)


@dataclass
class GitChanges:
    DEFAULT_PR_NUMBER: ClassVar[int] = 0
    commits: list[GitCommit]
    files_changed: set[str]
    git: Git | None
    start_sha: str
    end_sha: str
    pr_info: PRInfo | None = None
    last_merge_pr: int = DEFAULT_PR_NUMBER
    remote_url: str = ""

    @classmethod
    def empty(cls) -> Self:
        return cls(
            commits=[],
            files_changed=set(),
            git=None,
            start_sha="",
            end_sha="",
            last_merge_pr=cls.DEFAULT_PR_NUMBER,
            remote_url="",
        )

    @property
    def pr_url(self) -> str:
        if info := self.pr_info:
            return info.url
        return ""

    @property
    def current_pr(self) -> int:
        return self.pr_info.pr_number if self.pr_info else self.DEFAULT_PR_NUMBER

    @property
    def has_pr(self) -> bool:
        return self.pr_info is not None

    def has_change(self, rel_path_repo: str) -> bool:
        return rel_path_repo in self.files_changed

    def old_version(self, rel_path_repo: str) -> str:
        assert self.has_change(rel_path_repo), f"file hasn't changed: {rel_path_repo}"
        assert self.git, "git repo must be set for reading the old version"
        return _file_content(self.git, self.start_sha, rel_path_repo)


def head_merge_pr(repo_path: Path) -> int:
    repo = Repo(repo_path)
    message = str(repo.head.commit.message.strip())
    if merge_match := _merge_message_regex.match(message):
        return int(merge_match[1])
    raise ValueError(f"head is not a merge PR commit: {message}")


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


def _merge_base(repo: Repo, base_branch: str):
    base_commit = repo.commit(base_branch)
    head_commit = repo.head.commit
    stop_commits = repo.merge_base(base_commit, head_commit)
    assert stop_commits, f"Cannot find merge base for {base_branch} and {head_commit}"
    assert len(stop_commits) == 1, f"Multiple merge bases found: {stop_commits}"
    return stop_commits[0]


def solve_since_sha(repo: Repo, repo_path: Path, since: GitSince, ref: str) -> Commit:
    if since == GitSince.LAST_GIT_TAG or since == GitSince.DEFAULT and not ref:
        output = run_and_wait(
            "git describe --tags --abbrev=0", cwd=repo_path
        ).stdout_one_line
        return repo.commit(output)
    elif since in {GitSince.PR_BASE_BRANCH, GitSince.DEFAULT}:
        return _merge_base(repo, ref)
    elif since == GitSince.NO_GIT_CHANGES:
        raise _NoGitChangesError
    else:
        raise NotImplementedError


def find_pr_info_raw(repo_path: Path) -> dict[str, Any]:
    result = run_and_wait(
        "gh pr view --json baseRefName,url,baseRefOid",
        cwd=repo_path,
        allow_non_zero_exit=True,
    )
    if not result.clean_complete:
        return {}
    return result.parse_output(dict)


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


def find_pr_info_or_none(repo_path: Path) -> PRInfo | None:
    if raw := find_pr_info_raw(repo_path):
        return PRInfo(**raw)


def find_git_changes(event: GitChangesInput) -> GitChanges:
    repo_path = event.repo_path
    pr_info = find_pr_info_or_none(repo_path)
    try:
        repo = Repo(repo_path)
        head_sha = repo.head.commit.hexsha
    except InvalidGitRepositoryError as e:
        logger.warning(f"not a git repo @ {repo_path}: {e!r}")
        return GitChanges.empty()
    try:
        start_commit = solve_since_sha(
            repo, event.repo_path, event.since, pr_info.base_ref_oid if pr_info else ""
        )
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
    return GitChanges(
        commits=sorted(commits),
        files_changed=files_changed,
        git=repo.git,
        start_sha=start_sha,
        end_sha=head_sha,
        remote_url=remote_url,
        pr_info=pr_info,
        last_merge_pr=_last_merge_pr_repo(repo, head_sha)
        or GitChanges.DEFAULT_PR_NUMBER,
    )
