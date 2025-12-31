from path_sync.cmd_copy import _sync_always_path
from path_sync.header import has_header
from path_sync.models import PathMapping

CONFIG_NAME = "test-config"


def test_sync_single_file(tmp_path):
    src_root = tmp_path / "src"
    dest_root = tmp_path / "dest"
    src_root.mkdir()
    dest_root.mkdir()

    (src_root / "file.py").write_text("content")

    mapping = PathMapping(src_path="file.py", dest_path="out.py")
    changes = _sync_always_path(
        mapping, src_root, dest_root, CONFIG_NAME, dry_run=False
    )

    assert changes == 1
    result = (dest_root / "out.py").read_text()
    assert has_header(result)
    assert "content" in result
    assert f"path-sync copy -n {CONFIG_NAME}" in result


def test_sync_directory(tmp_path):
    src_root = tmp_path / "src"
    dest_root = tmp_path / "dest"
    (src_root / "docs").mkdir(parents=True)
    dest_root.mkdir()

    (src_root / "docs" / "a.md").write_text("doc a")
    (src_root / "docs" / "sub" / "b.md").parent.mkdir()
    (src_root / "docs" / "sub" / "b.md").write_text("doc b")

    mapping = PathMapping(src_path="docs", dest_path="output")
    changes = _sync_always_path(
        mapping, src_root, dest_root, CONFIG_NAME, dry_run=False
    )

    assert changes == 2
    assert (dest_root / "output" / "a.md").exists()
    assert (dest_root / "output" / "sub" / "b.md").exists()


def test_sync_skips_opted_out_file(tmp_path):
    src_root = tmp_path / "src"
    dest_root = tmp_path / "dest"
    src_root.mkdir()
    dest_root.mkdir()

    (src_root / "file.py").write_text("new content")
    (dest_root / "file.py").write_text("local content without header")

    mapping = PathMapping(src_path="file.py")
    changes = _sync_always_path(
        mapping, src_root, dest_root, CONFIG_NAME, dry_run=False
    )

    assert changes == 0
    assert (dest_root / "file.py").read_text() == "local content without header"
