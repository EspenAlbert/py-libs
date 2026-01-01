from path_sync.models import (
    Destination,
    PathMapping,
    PRDefaults,
    SrcConfig,
    find_repo_root,
    resolve_config_path,
)


def test_path_mapping_resolved():
    m1 = PathMapping(src_path="src/file.py")
    assert m1.resolved_dest_path() == "src/file.py"

    m2 = PathMapping(src_path="src/file.py", dest_path="dest/file.py")
    assert m2.resolved_dest_path() == "dest/file.py"


def test_resolve_config_path(tmp_path):
    src_path = resolve_config_path(tmp_path, "sdlc")
    assert src_path == tmp_path / ".github" / "sdlc.src.yaml"


def test_find_repo_root(tmp_repo):
    subdir = tmp_repo / "a" / "b"
    subdir.mkdir(parents=True)
    found = find_repo_root(subdir)
    assert found == tmp_repo


def test_src_config_find_destination():
    config = SrcConfig(
        name="test",
        destinations=[
            Destination(name="repo1", dest_path_relative="../repo1"),
            Destination(name="repo2", dest_path_relative="../repo2"),
        ],
    )
    dest = config.find_destination("repo1")
    assert dest.name == "repo1"


def test_destination_skip_sections():
    dest = Destination(
        name="test",
        dest_path_relative="../test",
        skip_sections={"justfile": ["pkg-ext"], "pyproject.toml": ["coverage"]},
    )
    assert dest.skip_sections["justfile"] == ["pkg-ext"]
    assert dest.skip_sections.get("unknown", []) == []


def test_pr_defaults_format_body():
    pr = PRDefaults()
    body = pr.format_body(
        src_repo_url="https://github.com/user/my-repo",
        src_sha="abc12345def67890",
        sync_log="INFO Wrote: file.py",
        dest_name="dest1",
    )
    assert "[my-repo](https://github.com/user/my-repo)" in body
    assert "`abc12345`" in body
    assert "INFO Wrote: file.py" in body


def test_pr_defaults_format_body_extracts_repo_name():
    pr = PRDefaults(body_template="{src_repo_name}")
    assert pr.format_body("https://github.com/u/repo", "sha", "", "") == "repo"
    assert pr.format_body("https://github.com/u/repo.git", "sha", "", "") == "repo"
