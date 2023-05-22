from pathlib import Path
from time import sleep, time

from zero_3rdparty.file_utils import (
    abspath_current_dir,
    abspath_dir,
    clean_dir,
    copy,
    ensure_parents_write_text,
    file_modified_time,
    iter_paths,
    iter_paths_and_relative,
    join_if_not_absolute,
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
