"""Tests for changelog actions module."""

from pathlib import Path

from pkg_ext.changelog.actions import (
    archive_old_actions,
    changelog_filename,
    changelog_filepath,
)


def test_archive_old_actions_no_cleanup_when_below_trigger(tmp_path: Path):
    """Test that no cleanup happens when file count is below trigger."""
    changelog_dir = tmp_path / "changelog"
    changelog_dir.mkdir()

    # Create 3 files (below trigger of 5)
    for i in range(1, 4):
        changelog_filepath(changelog_dir, i).write_text(f"content {i}")

    result = archive_old_actions(changelog_dir, cleanup_trigger=5, keep_count=2)

    assert result is False
    # All files should still be in original location
    assert len(list(changelog_dir.glob("*.yaml"))) == 3
    assert len(list(changelog_dir.rglob("*.yaml"))) == 3


def test_archive_old_actions_cleanup_when_above_trigger(tmp_path: Path):
    """Test that cleanup happens when file count reaches trigger."""
    changelog_dir = tmp_path / "changelog"
    changelog_dir.mkdir()

    # Create 6 files (above trigger of 5, should keep 2, archive 4)
    file_contents = {}
    for i in range(1, 7):
        filename = changelog_filename(i)
        content = f"action: test_{i}\nts: 2023-01-{i:02d}T10:00:00Z"
        (changelog_dir / filename).write_text(content)
        file_contents[filename] = content

    result = archive_old_actions(changelog_dir, cleanup_trigger=5, keep_count=2)

    assert result is True

    # Should have 2 files remaining in main directory
    remaining_files = list(changelog_dir.glob("*.yaml"))
    assert len(remaining_files) == 2
    assert "005.yaml" in [f.name for f in remaining_files]
    assert "006.yaml" in [f.name for f in remaining_files]

    # Should have 4 files archived in subdirectories
    archived_files = list(changelog_dir.rglob("*/*.yaml"))
    assert len(archived_files) == 4

    # Check that archived files are in correct structure
    # Files 001-004 should be archived in "000" subdirectory (pr_number // 1000 = 0)
    archive_dir = changelog_dir / "000"
    assert archive_dir.exists()
    archived_in_000 = list(archive_dir.glob("*.yaml"))
    assert len(archived_in_000) == 4

    expected_archived = ["001.yaml", "002.yaml", "003.yaml", "004.yaml"]
    actual_archived = [f.name for f in archived_in_000]
    assert sorted(actual_archived) == sorted(expected_archived)

    # Verify content is preserved
    for archived_file in archived_in_000:
        original_content = file_contents[archived_file.name]
        assert archived_file.read_text() == original_content


def test_archive_old_actions_different_archive_directories(tmp_path: Path):
    """Test that files are archived into correct directories based on PR number."""
    changelog_dir = tmp_path / "changelog"
    changelog_dir.mkdir()

    # Create files with different PR numbers that should go to different archive dirs
    test_cases = [
        (1, "000"),  # 1 // 1000 = 0
        (999, "000"),  # 999 // 1000 = 0
        (1000, "001"),  # 1000 // 1000 = 1
        (1001, "001"),  # 1001 // 1000 = 1
        (2500, "002"),  # 2500 // 1000 = 2
    ]

    for pr_number, expected_archive_dir in test_cases:
        (changelog_dir / changelog_filename(pr_number)).write_text(f"pr: {pr_number}")

    result = archive_old_actions(changelog_dir, cleanup_trigger=3, keep_count=1)

    assert result is True

    # Should have 1 file remaining (the last one alphabetically: 999.yaml)
    # Note: alphabetical sort gives: 001.yaml, 1000.yaml, 1001.yaml, 2500.yaml, 999.yaml
    remaining_files = list(changelog_dir.glob("*.yaml"))
    assert len(remaining_files) == 1
    assert remaining_files[0].name == "999.yaml"

    # Check archived files are in correct directories
    # Alphabetical sort: 001.yaml, 1000.yaml, 1001.yaml, 2500.yaml are archived (first 4)
    # 999.yaml remains (last alphabetically)
    archived_cases = [(1, "000"), (1000, "001"), (1001, "001"), (2500, "002")]
    for pr_number, expected_archive_dir in archived_cases:
        expected_path = (
            changelog_dir / expected_archive_dir / changelog_filename(pr_number)
        )
        assert expected_path.exists(), f"Expected {expected_path} to exist"
        assert expected_path.read_text() == f"pr: {pr_number}"


def test_archive_old_actions_exact_trigger_count(tmp_path: Path):
    """Test behavior when file count exactly equals trigger."""
    changelog_dir = tmp_path / "changelog"
    changelog_dir.mkdir()

    # Create exactly 5 files (equal to trigger)
    for i in range(1, 6):
        changelog_filepath(changelog_dir, i).write_text(f"content {i}")

    result = archive_old_actions(changelog_dir, cleanup_trigger=5, keep_count=2)

    assert result is True

    # Should keep 2 files, archive 3
    remaining_files = list(changelog_dir.glob("*.yaml"))
    assert len(remaining_files) == 2
    assert "004.yaml" in [f.name for f in remaining_files]
    assert "005.yaml" in [f.name for f in remaining_files]

    archived_files = list(changelog_dir.rglob("*/*.yaml"))
    assert len(archived_files) == 3


def test_archive_old_actions_keep_count_larger_than_file_count(tmp_path: Path):
    """Test when keep_count is larger than file count."""
    changelog_dir = tmp_path / "changelog"
    changelog_dir.mkdir()

    # Create 3 files but want to keep 5
    for i in range(1, 4):
        changelog_filepath(changelog_dir, i).write_text(f"content {i}")

    result = archive_old_actions(changelog_dir, cleanup_trigger=2, keep_count=5)

    assert result is True  # Cleanup was triggered

    # All files should remain (can't archive negative number of files)
    remaining_files = list(changelog_dir.glob("*.yaml"))
    assert len(remaining_files) == 3

    # No archived files
    archived_files = list(changelog_dir.rglob("*/*.yaml"))
    assert not archived_files


def test_archive_old_actions_empty_directory(tmp_path: Path):
    """Test behavior with empty changelog directory."""
    changelog_dir = tmp_path / "changelog"
    changelog_dir.mkdir()

    result = archive_old_actions(changelog_dir, cleanup_trigger=5, keep_count=2)

    assert result is False
    assert not list(changelog_dir.glob("*.yaml"))


def test_archive_old_actions_only_subdirectories_ignored(tmp_path: Path):
    """Test that existing subdirectories are ignored when counting files to archive."""
    changelog_dir = tmp_path / "changelog"
    changelog_dir.mkdir()

    # Create some top-level files
    for i in range(1, 6):
        changelog_filepath(changelog_dir, i).write_text(f"content {i}")

    # Create some files in subdirectories (should be ignored)
    subdir = changelog_dir / "000"
    subdir.mkdir()
    (subdir / "archived.yaml").write_text("archived content")

    result = archive_old_actions(changelog_dir, cleanup_trigger=4, keep_count=2)

    assert result is True

    # Should only count top-level files for archival
    remaining_files = list(changelog_dir.glob("*.yaml"))
    assert len(remaining_files) == 2

    # The pre-existing archived file should still be there
    assert (subdir / "archived.yaml").exists()
    assert (subdir / "archived.yaml").read_text() == "archived content"
