from pathlib import Path
from time import sleep, time

import pytest

from zero_3rdparty.file_utils import (
    MarkerNotFoundError,
    abspath_current_dir,
    abspath_dir,
    clean_dir,
    copy,
    ensure_parents_write_text,
    file_modified_time,
    iter_paths,
    iter_paths_and_relative,
    join_if_not_absolute,
    update_between_markers,
)


def test_file_modified_time(tmp_path):
    now = time()
    sleep(0.01)
    path = tmp_path / "file.txt"
    path.write_text("1234")
    modified_time = file_modified_time(path)
    assert now < modified_time


def test_iter_paths(tmp_path):
    filenames = ["1.yaml", "2.yml", "3.ini", "4.txt", "5.ini"]
    for name in filenames:
        (tmp_path / name).write_text(f"test-{name}")
    found = list(iter_paths(tmp_path, "*.yaml", "*.yml", "*.ini"))
    assert len(found) == 4


def test_iter_paths_with_exclude(tmp_path):
    rel_paths = [
        "1.yaml",
        ".terraform/2.yaml",
        "modules/.terraform/3.yaml",
        "terraform/4.yaml",
    ]
    for path in rel_paths:
        ensure_parents_write_text(tmp_path / path, f"path: {path}")
    assert sorted(
        path.name
        for path in iter_paths(tmp_path, "*.yaml", exclude_folder_names=[".terraform"])
    ) == ["1.yaml", "4.yaml"]


def test_iter_paths_and_relative(tmp_path, subtests):
    filenames = [
        "1.yaml",
        "2.yml",
        "deeply/nested/4.txt",
        "deeply/nested/5.ini",
        "nested/3.ini",
    ]
    with subtests.test("ensure parents"):
        for rel_path in filenames:
            abs_path = join_if_not_absolute(tmp_path, rel_path)
            ensure_parents_write_text(abs_path, "")
    with subtests.test("iter_paths_and_relative"):
        rel_paths: dict[str, Path] = {
            relative: full_path
            for full_path, relative in iter_paths_and_relative(
                tmp_path, "*.yaml", "*.yml", "*.txt", "*.ini"
            )
        }
        assert sorted(rel_paths.keys()) == filenames
    with subtests.test("abspath_dir"):
        assert abspath_current_dir(rel_paths["1.yaml"]) == str(tmp_path)
        assert abspath_dir(rel_paths["nested/3.ini"], dirs_up=1) == str(tmp_path)
        assert abspath_dir(rel_paths["deeply/nested/5.ini"], dirs_up=2) == str(tmp_path)
    with subtests.test("copy_file"):
        copy(rel_paths["1.yaml"], tmp_path / "new_dir/xx.yaml")
        assert len(list(iter_paths(tmp_path, "xx.yaml"))) == 1
    with subtests.test("copy_folder and clean it"):
        copy(
            rel_paths["nested/3.ini"].parent,
            tmp_path / "deeply/nested",
            clean_dest=True,
        )
        assert len(list(iter_paths(tmp_path, "3.ini"))) == 2
        assert len(list(iter_paths(tmp_path, "4.txt"))) == 0
    with subtests.test("clean_dir"):
        clean_dir(tmp_path)
        assert len(list(iter_paths(tmp_path, "*.ini"))) == 0


def test_update_between_markers_update_non_existing_file(tmp_path):
    start_marker = "# start"
    end_marker = "# end"
    path: Path = tmp_path / "file.txt"

    def read_lines() -> list[str]:
        return path.read_text().splitlines()

    update_between_markers(path, "1st content", start_marker, end_marker)
    assert read_lines() == [start_marker, "1st content", end_marker]


def test_update_between_markers_not_touching_existing_content_before(tmp_path):
    start_marker = "# start"
    end_marker = "# end"
    path: Path = tmp_path / "file.txt"

    def read_lines() -> list[str]:
        return path.read_text().splitlines()

    path.write_text(f"original\n{start_marker}\nold\n{end_marker}\n")
    update_between_markers(path, "2nd content", start_marker, end_marker)
    assert read_lines() == [
        "original",
        start_marker,
        "2nd content",
        end_marker,
    ]


def test_update_between_markers_not_touching_existing_content_after(tmp_path):
    start_marker = "# start"
    end_marker = "# end"
    path: Path = tmp_path / "file.txt"

    def read_lines() -> list[str]:
        return path.read_text().splitlines()

    path.write_text(f"some-start\n{start_marker}\nold\n{end_marker}\nsome-end")
    update_between_markers(path, "3rd content", start_marker, end_marker)
    assert read_lines() == [
        "some-start",
        start_marker,
        "3rd content",
        end_marker,
        "some-end",
    ]


def test_update_between_markers_markers_missing_raises_error(tmp_path):
    start_marker = "# start"
    end_marker = "# end"
    path: Path = tmp_path / "file.txt"
    path.write_text("some-start-no-marker")
    with pytest.raises(MarkerNotFoundError, match=start_marker):
        update_between_markers(path, "error", start_marker, end_marker)
    path.write_text(f"some-start-no-marker\n{start_marker}\ncontent")
    with pytest.raises(MarkerNotFoundError, match=end_marker):
        update_between_markers(path, "error", start_marker, end_marker)
    path.write_text(f"some-start-no-marker\n{end_marker}\ncontent\n{start_marker}")
    with pytest.raises(ValueError, match=f"end marker {end_marker} before start"):
        update_between_markers(path, "error", start_marker, end_marker)


def test_update_between_markers_append_if_not_found(tmp_path):
    start_marker = "# start"
    end_marker = "# end"
    path: Path = tmp_path / "file.txt"

    def read_lines() -> list[str]:
        return path.read_text().splitlines()

    path.write_text("original text")
    update_between_markers(
        path, "4th content", start_marker, end_marker, append_if_not_found=True
    )
    assert read_lines() == [
        "original text",
        start_marker,
        "4th content",
        end_marker,
    ]


def test_update_between_markers_leave_file_unchanged(tmp_path):
    start_marker = "# start"
    end_marker = "# end"
    path: Path = tmp_path / "file.txt"

    def read_lines() -> list[str]:
        return path.read_text().splitlines()

    file_lines = [
        "original text",
        "",
        "",
        start_marker,
        "4th content",
        "",  # empty line should be preserved
        end_marker,
    ]

    path.write_text("\n".join(file_lines))

    update_between_markers(path, "4th content\n", start_marker, end_marker)
    assert read_lines() == file_lines
