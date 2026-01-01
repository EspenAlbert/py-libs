from git import Repo

from path_sync import validation
from path_sync.header import get_header_line

HEADER = get_header_line(".py", "test-config")


def _setup_baseline(repo_path, filename: str, content: str) -> None:
    """Commit content as baseline on main and create origin/main ref."""
    repo = Repo(repo_path)
    file_path = repo_path / filename
    file_path.write_text(content)
    repo.index.add([filename])
    repo.index.commit("baseline")
    repo.create_head("origin/main", repo.head.commit)


def test_modify_ok_edit_passes(tmp_repo):
    baseline = f"""{HEADER}
# === OK_EDIT ===
user content
# === DO_NOT_EDIT: path-sync standard ===
protected
# === OK_EDIT ===
"""
    _setup_baseline(tmp_repo, "test.py", baseline)

    current = f"""{HEADER}
# === OK_EDIT ===
modified user content
# === DO_NOT_EDIT: path-sync standard ===
protected
# === OK_EDIT ===
"""
    (tmp_repo / "test.py").write_text(current)

    result = validation.validate_no_unauthorized_changes(tmp_repo, "main")
    assert result == []


def test_modify_do_not_edit_fails(tmp_repo):
    baseline = f"""{HEADER}
# === DO_NOT_EDIT: path-sync standard ===
protected content
# === OK_EDIT ===
"""
    _setup_baseline(tmp_repo, "test.py", baseline)

    current = f"""{HEADER}
# === DO_NOT_EDIT: path-sync standard ===
MODIFIED protected content
# === OK_EDIT ===
"""
    (tmp_repo / "test.py").write_text(current)

    result = validation.validate_no_unauthorized_changes(tmp_repo, "main")
    assert result == ["test.py:standard"]


def test_skip_section_passes(tmp_repo):
    baseline = f"""{HEADER}
# === DO_NOT_EDIT: path-sync coverage ===
protected
# === OK_EDIT ===
"""
    _setup_baseline(tmp_repo, "test.py", baseline)

    current = f"""{HEADER}
# === DO_NOT_EDIT: path-sync coverage ===
MODIFIED
# === OK_EDIT ===
"""
    (tmp_repo / "test.py").write_text(current)

    result = validation.validate_no_unauthorized_changes(
        tmp_repo, "main", skip_sections={"test.py": {"coverage"}}
    )
    assert result == []


def test_section_removed_fails(tmp_repo):
    baseline = f"""{HEADER}
# === DO_NOT_EDIT: path-sync standard ===
protected
# === OK_EDIT ===
"""
    _setup_baseline(tmp_repo, "test.py", baseline)

    current = f"""{HEADER}
# no sections anymore
"""
    (tmp_repo / "test.py").write_text(current)

    result = validation.validate_no_unauthorized_changes(tmp_repo, "main")
    assert result == ["test.py:standard"]


def test_no_sections_full_file_comparison(tmp_repo):
    baseline = f"{HEADER}\noriginal content\n"
    _setup_baseline(tmp_repo, "test.py", baseline)

    (tmp_repo / "test.py").write_text(f"{HEADER}\nmodified content\n")

    result = validation.validate_no_unauthorized_changes(tmp_repo, "main")
    assert result == ["test.py"]


def test_parse_skip_sections():
    result = validation.parse_skip_sections("justfile:coverage,pyproject.toml:default")
    assert result == {"justfile": {"coverage"}, "pyproject.toml": {"default"}}

    result = validation.parse_skip_sections("path:a,path:b")
    assert result == {"path": {"a", "b"}}
