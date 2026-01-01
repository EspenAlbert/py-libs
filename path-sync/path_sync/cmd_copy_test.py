from path_sync.cmd_copy import _cleanup_orphans, _sync_path
from path_sync.header import add_header, has_header
from path_sync.models import Destination, PathMapping

CONFIG_NAME = "test-config"


def _make_dest(**kwargs) -> Destination:
    defaults = {"name": "test", "dest_path_relative": "."}
    return Destination(**(defaults | kwargs))  # pyright: ignore[reportArgumentType]


def test_sync_single_file(tmp_path):
    src_root = tmp_path / "src"
    dest_root = tmp_path / "dest"
    src_root.mkdir()
    dest_root.mkdir()

    (src_root / "file.py").write_text("content")

    mapping = PathMapping(src_path="file.py", dest_path="out.py")
    changes, synced = _sync_path(
        mapping, src_root, dest_root, _make_dest(), CONFIG_NAME, False, False
    )

    assert changes == 1
    assert dest_root / "out.py" in synced
    result = (dest_root / "out.py").read_text()
    assert has_header(result)
    assert f"path-sync copy -n {CONFIG_NAME}" in result


def test_sync_skips_opted_out_file(tmp_path):
    src_root = tmp_path / "src"
    dest_root = tmp_path / "dest"
    src_root.mkdir()
    dest_root.mkdir()

    (src_root / "file.py").write_text("new content")
    (dest_root / "file.py").write_text("local content without header")

    mapping = PathMapping(src_path="file.py")
    changes, _ = _sync_path(
        mapping, src_root, dest_root, _make_dest(), CONFIG_NAME, False, False
    )

    assert changes == 0
    assert (dest_root / "file.py").read_text() == "local content without header"


def test_cleanup_orphans(tmp_path):
    dest_root = tmp_path / "dest"
    dest_root.mkdir()

    # File with matching config header - will be orphaned
    orphan = dest_root / "orphan.py"
    orphan.write_text(add_header("orphan content", ".py", CONFIG_NAME))

    # File with different config - should not be deleted
    other = dest_root / "other.py"
    other.write_text(add_header("other content", ".py", "other-config"))

    synced: set = set()  # No files synced
    deleted = _cleanup_orphans(dest_root, CONFIG_NAME, synced, dry_run=False)

    assert deleted == 1
    assert not orphan.exists()
    assert other.exists()


def test_sync_with_sections_replaces_managed(tmp_path):
    src_root = tmp_path / "src"
    dest_root = tmp_path / "dest"
    src_root.mkdir()
    dest_root.mkdir()

    src_content = """\
# === DO_NOT_EDIT: path-sync standard ===
new recipe
# === OK_EDIT ==="""
    (src_root / "file.sh").write_text(src_content)

    dest_content = add_header(
        """\
# === DO_NOT_EDIT: path-sync standard ===
old recipe
# === OK_EDIT ===
# my custom stuff""",
        ".sh",
        CONFIG_NAME,
    )
    (dest_root / "file.sh").write_text(dest_content)

    mapping = PathMapping(src_path="file.sh")
    changes, _ = _sync_path(
        mapping, src_root, dest_root, _make_dest(), CONFIG_NAME, False, False
    )

    assert changes == 1
    result = (dest_root / "file.sh").read_text()
    assert "new recipe" in result
    assert "old recipe" not in result
    assert "# my custom stuff" in result


def test_sync_with_sections_skip(tmp_path):
    src_root = tmp_path / "src"
    dest_root = tmp_path / "dest"
    src_root.mkdir()
    dest_root.mkdir()

    src_content = """\
# === DO_NOT_EDIT: path-sync standard ===
source
# === OK_EDIT ==="""
    (src_root / "file.sh").write_text(src_content)

    dest_content = add_header(
        """\
# === DO_NOT_EDIT: path-sync standard ===
keep this
# === OK_EDIT ===""",
        ".sh",
        CONFIG_NAME,
    )
    (dest_root / "file.sh").write_text(dest_content)

    dest = _make_dest(skip_sections={"file.sh": ["standard"]})
    mapping = PathMapping(src_path="file.sh")
    changes, _ = _sync_path(
        mapping, src_root, dest_root, dest, CONFIG_NAME, False, False
    )

    assert changes == 0
    assert "keep this" in (dest_root / "file.sh").read_text()
