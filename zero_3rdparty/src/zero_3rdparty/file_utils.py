from __future__ import annotations

import logging
import os
import shutil
from logging import Logger
from pathlib import Path
from typing import Iterable

from zero_3rdparty.run_env import running_in_container_environment

PathLike = os.PathLike
logger = logging.getLogger(__name__)


def filepath_in_same_dir(file_path: str, *other_filename: str) -> str:
    """
    >>> filepath_in_same_dir(__file__, 'id_creator.py').endswith('id_creator.py')
    True
    """
    return os.path.join(os.path.dirname(file_path), *other_filename)


def abspath_current_dir(file: os.PathLike) -> str:
    return abspath_dir(file, dirs_up=0)


def abspath_dir(file: os.PathLike, dirs_up: int = 0) -> str:
    parents = list(Path(file).parents)
    return str(parents[dirs_up])


def rm_tree_logged(file_path: str, logger: Logger, ignore_errors: bool = True) -> None:
    logger.info(f"remove dir: {file_path}")
    if ignore_errors:

        def log_error(*args):
            logger.warning(f"error deleting: {file_path}, {args}")

        shutil.rmtree(file_path, ignore_errors=False, onerror=log_error)
    else:
        shutil.rmtree(file_path, ignore_errors=False)


def stem_name(
    path: os.PathLike, include_parent: bool = False, join_parent: str = "/"
) -> str:
    """
    >>> Path("docker-compose.dec.yaml").stem # notice how there is still .dec
    'docker-compose.dec'
    >>> stem_name('dump/docker-compose.dec.yaml')
    'docker-compose'
    >>> stem_name('dump/docker-compose.dec.yaml', include_parent=True)
    'dump/docker-compose'
    """
    path = Path(path)
    name = path.name.replace("".join(path.suffixes), "")
    if include_parent:
        name = f"{path.parent.name}{join_parent}{name}"
    return name


def clean_dir(
    path: Path, expected_parents: int = 2, recreate: bool = True, ignore_errors=True
) -> None:
    if not running_in_container_environment():
        assert (
            len(Path(path).parents) > expected_parents
        ), f"rm root by accident {path}?"
    rm_tree_logged(str(path), logger, ignore_errors=ignore_errors)
    if recreate:
        path.mkdir(parents=True, exist_ok=True)


def join_if_not_absolute(base_path: os.PathLike, relative: str) -> str:
    if relative.startswith(os.path.sep):
        return relative
    return os.path.join(base_path, relative)


def copy(
    src: os.PathLike, dest: os.PathLike, clean_dest: bool = False, ensure_parents=True
) -> None:
    logger.info(f"cp {src} {dest}")
    dest = Path(dest)
    if ensure_parents:
        dest.parent.mkdir(parents=True, exist_ok=True)
    if Path(src).is_dir():
        if clean_dest and dest.exists():
            clean_dir(dest, recreate=False)
        shutil.copytree(src, dest)
    else:
        if dest.exists():
            dest.unlink()
        shutil.copy(src, dest)


def ensure_parents_write_text(path: os.PathLike, text: str, log: bool = False) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    if log:
        logger.info(f"writing to {path}, text={text}")


def file_modified_time(path: os.PathLike) -> float:
    return os.path.getmtime(path)


IMG_EXTENSIONS = (".jpeg", ".gif", ".png")


def is_image_file(path: os.PathLike) -> bool:
    """
    >>> is_image_file("profile.png")
    True
    >>> is_image_file("profile.txt")
    False
    >>> is_image_file("profile")
    False
    """
    return Path(path).suffix.endswith(IMG_EXTENSIONS)


def iter_paths(base_dir: Path, *globs: str, rglob=True) -> Iterable[Path]:
    search_func = base_dir.rglob if rglob else base_dir.glob
    for glob in globs:
        yield from search_func(glob)


def iter_paths_and_relative(
    base_dir: Path, *globs: str, rglob=True, only_files: bool = False
) -> Iterable[tuple[Path, str]]:
    for path in iter_paths(base_dir, *globs, rglob=rglob):
        if only_files and not path.is_file():
            continue
        yield path, str(path.relative_to(base_dir))
