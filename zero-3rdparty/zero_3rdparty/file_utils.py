from __future__ import annotations

import logging
import os
import re
import shutil
from logging import Logger
from pathlib import Path
from typing import Iterable, NamedTuple, TypeAlias

from zero_3rdparty.run_env import running_in_container_environment

PathLike: TypeAlias = os.PathLike
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
        assert len(Path(path).parents) > expected_parents, (
            f"rm root by accident {path}?"
        )
    if path.exists():
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


def ensure_parents_write_text(path: Path | str, text: str, log: bool = False) -> None:
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


def iter_paths(
    base_dir: Path,
    *globs: str,
    rglob=True,
    exclude_folder_names: list[str] | None = None,
) -> Iterable[Path]:
    search_func = base_dir.rglob if rglob else base_dir.glob
    for glob in globs:
        if exclude_folder_names:
            for path in search_func(glob):
                rel_path = str(path.relative_to(base_dir))
                if any(
                    f"/{folder_name}/" in rel_path
                    or rel_path.startswith(f"{folder_name}/")
                    for folder_name in exclude_folder_names
                ):
                    continue
                yield path
        else:
            yield from search_func(glob)


def iter_paths_and_relative(
    base_dir: Path, *globs: str, rglob=True, only_files: bool = False
) -> Iterable[tuple[Path, str]]:
    for path in iter_paths(base_dir, *globs, rglob=rglob):
        if only_files and not path.is_file():
            continue
        yield path, str(path.relative_to(base_dir))


class UpdateMarkerResult(NamedTuple):
    before: str
    after: str


def update_between_markers(
    path: PathLike,
    content: str,
    start_marker: str,
    end_marker: str,
    *,
    error_if_not_found: bool = False,
    append_if_not_found: bool = False,
    marker_content_separator: str = "\n",
) -> UpdateMarkerResult:
    path = Path(path)
    new_content = f"{start_marker}{marker_content_separator}{content}{marker_content_separator}{end_marker}"
    if not path.exists():
        if error_if_not_found:
            raise ValueError(f"File {path} does not exist, cannot update markers")
        ensure_parents_write_text(path, new_content)
        return UpdateMarkerResult("", new_content)

    old_text = path.read_text()
    try:
        old_content = read_between_markers(old_text, start_marker, end_marker)
    except MarkerNotFoundError as e:
        if append_if_not_found:
            new_content = (
                f"{marker_content_separator}{new_content}{marker_content_separator}"
            )
            path.write_text(old_text + new_content)
            return UpdateMarkerResult("", new_content)
        raise e
    assert isinstance(old_content, str)
    if f"{marker_content_separator}{old_content}{marker_content_separator}" == content:
        return UpdateMarkerResult(old_content, old_content)
    updated = markers_pattern(start_marker, end_marker).sub(
        new_content,
        old_text,
    )
    path.write_text(updated)
    return UpdateMarkerResult(old_content, content)


def markers_pattern(start_marker: str, end_marker: str) -> re.Pattern:
    return re.compile(
        rf"(?P<start_marker>{re.escape(start_marker)})(?P<between_markers>.*?)(?P<end_marker>{re.escape(end_marker)})",
        re.DOTALL,
    )


class MarkerNotFoundError(ValueError):
    def __init__(self, marker_name: str) -> None:
        self.marker_name = marker_name


class MultipleMarkersError(ValueError):
    def __init__(self, marker_name: str, matches: list[re.Match]) -> None:
        self.marker_name = marker_name
        self.matches = matches


def read_between_markers(
    text: str, start_marker: str, end_marker: str, *, allow_multiple: bool = False
) -> str | list[str]:
    matches = list(markers_pattern(start_marker, end_marker).finditer(text))
    if len(matches) == 0:
        start, end = text.find(start_marker), text.find(end_marker)
        if start == -1:
            raise MarkerNotFoundError(start_marker)
        if end == -1:
            raise MarkerNotFoundError(end_marker)
        if end < start:
            raise ValueError(
                f"end marker {end_marker} before start marker {start_marker}"
            )
        raise ValueError("No markers found in text")
    if len(matches) == 1:
        return matches[0].group("between_markers")
    if allow_multiple:
        return [match.group("between_markers") for match in matches]
    raise MultipleMarkersError(start_marker, matches)
