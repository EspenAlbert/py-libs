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
    """
    Yields tuples of paths and their relative paths under a base directory, matching specified glob patterns.
    
    Parameters:
        base_dir (Path): The root directory to search within.
        *globs (str): Glob patterns to match files or directories.
        rglob (bool): If True, uses recursive globbing.
        only_files (bool): If True, yields only files (not directories).
    
    Returns:
        Iterable[tuple[Path, str]]: Tuples containing the absolute path and its relative path from base_dir.
    """
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
    """
    Update the text between specified start and end markers in a file, replacing or appending content as needed.
    
    If the file does not exist, it is created with the markers and content unless `error_if_not_found` is True. If the markers are not found in an existing file, the content is appended if `append_if_not_found` is True; otherwise, an error is raised. Returns a named tuple containing the previous and new content between the markers.
    
    Parameters:
        path: Path to the file to update.
        content: The text to insert between the markers.
        start_marker: The marker indicating the start of the section to update.
        end_marker: The marker indicating the end of the section to update.
        error_if_not_found: If True, raises an error if the file does not exist.
        append_if_not_found: If True, appends the markers and content if they are not found in the file.
        marker_content_separator: String to separate markers from the content.
    
    Returns:
        UpdateMarkerResult: A named tuple with the content before and after the update.
    """
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
    if f"{marker_content_separator}{old_content}{marker_content_separator}" == content:
        return UpdateMarkerResult(old_content, old_content)
    updated = markers_pattern(start_marker, end_marker).sub(
        new_content,
        old_text,
    )
    path.write_text(updated)
    return UpdateMarkerResult(old_content, content)


def markers_pattern(start_marker: str, end_marker: str) -> re.Pattern:
    """
    Compile a regular expression pattern to match text between specified start and end markers.
    
    The returned pattern captures the start marker, the content between markers, and the end marker as named groups.
    """
    return re.compile(
        rf"(?P<start_marker>{re.escape(start_marker)})(?P<between_markers>.*?)(?P<end_marker>{re.escape(end_marker)})",
        re.DOTALL,
    )


class MarkerNotFoundError(ValueError):
    def __init__(self, marker_name: str) -> None:
        """
        Initialize the exception with the name of the marker associated with the error.
        
        Parameters:
            marker_name (str): The name or identifier of the marker involved in the error.
        """
        self.marker_name = marker_name


class MultipleMarkersError(ValueError):
    def __init__(self, marker_name: str, matches: list[re.Match]) -> None:
        """
        Initialize a MultipleMarkersError with the marker name and list of regex matches.
        
        Parameters:
            marker_name (str): The name or identifier of the marker associated with the error.
            matches (list[re.Match]): List of regex match objects representing all found marker occurrences.
        """
        self.marker_name = marker_name
        self.matches = matches


def read_between_markers_multiple(
    text: str, start_marker: str, end_marker: str
) -> list[str]:
    """
    Extracts all text segments found between multiple occurrences of the specified start and end markers.
    
    If only one marker pair is present, returns a single-item list containing the content between them. If multiple marker pairs are found, returns a list of all matched segments in order of appearance.
    
    Parameters:
        text (str): The input text to search for marker-delimited segments.
        start_marker (str): The marker indicating the start of a segment.
        end_marker (str): The marker indicating the end of a segment.
    
    Returns:
        list[str]: A list of all text segments found between each pair of markers.
    """
    try:
        single_response = read_between_markers(text, start_marker, end_marker)
        return [single_response]
    except MultipleMarkersError as e:
        return [match.group("between_markers") for match in e.matches]


def read_between_markers(
    text: str,
    start_marker: str,
    end_marker: str,
) -> str:
    """
    Extracts the text between the first occurrence of the specified start and end markers in the input string.
    
    Raises:
        MarkerNotFoundError: If either marker is missing from the text.
        MultipleMarkersError: If multiple marker pairs are found.
        ValueError: If the end marker appears before the start marker or if no valid marker pair is found.
    
    Returns:
        The text found between the first matching pair of markers.
    """
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
    raise MultipleMarkersError(start_marker, matches)
