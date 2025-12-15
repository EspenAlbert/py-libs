import pytest
from git import Repo


@pytest.fixture
def tmp_repo(tmp_path):
    """Create a temporary git repo."""

    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    repo = Repo.init(repo_path)
    (repo_path / ".gitkeep").write_text("")
    repo.index.add([".gitkeep"])
    repo.index.commit("Initial commit")
    return repo_path
