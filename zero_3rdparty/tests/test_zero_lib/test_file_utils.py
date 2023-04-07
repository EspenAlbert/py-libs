from time import time, sleep

from zero_3rdparty.file_utils import file_modified_time, iter_paths


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
