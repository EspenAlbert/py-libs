import re
from pathlib import Path

from git import InvalidGitRepositoryError, Repo

from pkg_ext.errors import RemoteURLNotFound


def remove_credentials(repo_url: str) -> str:
    """
    >>> remove_credentials('https://oauth2:BySECRET_TOKEN@gitlab.com/org/backend')
    'https://gitlab.com/org/backend'
    >>> remove_credentials('https://oauth2:By-SECRET_TOKEN@gitlab.com/org/backend')
    'https://gitlab.com/org/backend'
    """
    return re.sub(r"https://(oauth2:)?[^@]+@", "https://", repo_url)


def normalize_repo_url(repo_url: str) -> str:
    """
    >>> normalize_repo_url('git@gitlab.com:org/_shared/docker')
    'https://gitlab.com/org/_shared/docker'
    >>> normalize_repo_url('https://oauth2:BySECRET_TOKEN@gitlab.com/org/backend')
    'https://gitlab.com/org/backend'
    """
    repo_url = repo_url.removesuffix(".git")
    extra_prefix = "git@gitlab.com:"
    if repo_url.startswith(extra_prefix):
        repo_url = f"https://gitlab.com/{repo_url[len(extra_prefix) :]}"
    return remove_credentials(repo_url)


def read_remote_url(path: Path) -> str:
    try:
        repo = Repo(path)
    except InvalidGitRepositoryError as e:
        raise RemoteURLNotFound(reason=repr(e), path=path) from e
    remotes = repo.remotes
    if not remotes:
        raise RemoteURLNotFound("no remotes", path)
    for remote in remotes:
        if urls := list(remote.urls):
            return normalize_repo_url(urls[0])
    raise RemoteURLNotFound("no urls", path)
