import pytest

from path_sync.cmd_copy import (
    CopyOptions,
    _cleanup_orphans,
    _ensure_dest_repo,
    _sync_path,
)
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


def test_force_overwrite_adds_header_when_content_matches(tmp_path):
    src_root = tmp_path / "src"
    dest_root = tmp_path / "dest"
    src_root.mkdir()
    dest_root.mkdir()

    content = "same content"
    (src_root / "file.py").write_text(content)
    (dest_root / "file.py").write_text(content)  # No header, same content

    mapping = PathMapping(src_path="file.py")
    changes, _ = _sync_path(
        mapping, src_root, dest_root, _make_dest(), CONFIG_NAME, False, True
    )

    assert changes == 1
    result = (dest_root / "file.py").read_text()
    assert has_header(result)
    assert content in result


def test_cleanup_orphans(tmp_path):
    dest_root = tmp_path / "dest"
    dest_root.mkdir()

    # File with matching config header - will be orphaned
    orphan = dest_root / "orphan.py"
    orphan.write_text(add_header("orphan content", orphan, CONFIG_NAME))

    # File with different config - should not be deleted
    other = dest_root / "other.py"
    other.write_text(add_header("other content", other, "other-config"))

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
# === OK_EDIT: path-sync standard ==="""
    (src_root / "file.sh").write_text(src_content)

    dest_file = dest_root / "file.sh"
    dest_content = add_header(
        """\
# === DO_NOT_EDIT: path-sync standard ===
old recipe
# === OK_EDIT: path-sync standard ===
# my custom stuff""",
        dest_file,
        CONFIG_NAME,
    )
    dest_file.write_text(dest_content)

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
# === OK_EDIT: path-sync standard ==="""
    (src_root / "file.sh").write_text(src_content)

    dest_file = dest_root / "file.sh"
    dest_content = add_header(
        """\
# === DO_NOT_EDIT: path-sync standard ===
keep this
# === OK_EDIT: path-sync standard ===""",
        dest_file,
        CONFIG_NAME,
    )
    dest_file.write_text(dest_content)

    dest = _make_dest(skip_sections={"file.sh": ["standard"]})
    mapping = PathMapping(src_path="file.sh")
    changes, _ = _sync_path(
        mapping, src_root, dest_root, dest, CONFIG_NAME, False, False
    )

    assert changes == 0
    assert "keep this" in (dest_root / "file.sh").read_text()


def test_ensure_dest_repo_dry_run_errors_if_missing(tmp_path):
    dest = _make_dest()
    dest_root = tmp_path / "missing_repo"
    with pytest.raises(ValueError, match="Destination repo not found"):
        _ensure_dest_repo(dest, dest_root, dry_run=True)


def test_copy_options_defaults():
    opts = CopyOptions()
    assert not opts.dry_run
    assert not opts.force_overwrite
    assert not opts.no_checkout
    assert not opts.local
    assert not opts.no_prompt
    assert not opts.no_pr


def test_source_with_header_no_duplicate(tmp_path):
    """Source files with headers should not get double headers in destination."""
    src_root = tmp_path / "src"
    dest_root = tmp_path / "dest"
    src_root.mkdir()
    dest_root.mkdir()

    # Source file already has a header (e.g., template repo uses path-sync itself)
    src_file = src_root / "file.py"
    src_content_with_header = add_header("content", src_file, "original-config")
    src_file.write_text(src_content_with_header)

    mapping = PathMapping(src_path="file.py")
    changes, synced = _sync_path(
        mapping, src_root, dest_root, _make_dest(), CONFIG_NAME, False, False
    )

    assert changes == 1
    assert dest_root / "file.py" in synced
    result = (dest_root / "file.py").read_text()

    # Should have exactly one header line with CONFIG_NAME, not two headers
    header_count = result.count("path-sync copy -n")
    assert header_count == 1, (
        f"Expected 1 header, got {header_count}. Content:\n{result}"
    )
    assert f"path-sync copy -n {CONFIG_NAME}" in result
    assert "original-config" not in result
