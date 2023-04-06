import logging
import os
import shutil
from io import StringIO
from logging import Logger
from pathlib import Path
from typing import Callable, Iterable, List, Union

from zero_lib.run_env import running_in_container_environment

logger = logging.getLogger(__name__)
PathLike = Union[str, Path]


def replace_between_lines(
    file_path: PathLike = "Dockerfile",
    line_start: str = "# LOCAL_COPY\n",
    line_end: str = "#END LOCAL_COPY\n",
    content_to_insert: str = "\n".join(("COPY src/rabbitmq ./", "COPY src/ci_lib ./"))
    + "\n",
) -> None:
    read = "read"
    write_override = "write_override"
    mode = read
    file_out = StringIO()
    with open(file_path) as file_in:
        for line in file_in:
            if line == line_start:
                mode = write_override
                file_out.write(line)
                file_out.write(content_to_insert)
                continue
            elif line == line_end:
                file_out.write(line)
                mode = read
                continue
            if mode == read:
                file_out.write(line)
            elif mode == write_override:
                continue
    with open(file_path, "w") as out:
        out.write(file_out.getvalue())


def read_files_in_dir(
    path: PathLike,
    filter_function: Callable[[str], bool] = lambda s: not s.startswith("."),
) -> List[str]:
    return [dir for dir in os.listdir(path) if filter_function(dir)]


def filepath_in_same_dir(file_path: str, *other_filename: str) -> str:
    """
    >>> filepath_in_same_dir(__file__, 'id_creator.py').endswith('utils/id_creator.py')
    True
    """
    return os.path.join(os.path.dirname(file_path), *other_filename)


def read_lines_in(file_path: PathLike) -> str:
    with open(file_path, mode="rt") as f:
        return "".join(f.readlines())


def python_filter(s: str) -> bool:
    return not s.startswith((".", "_")) and s.endswith(".py")


def python_files_in_dir(file_path: PathLike, strip_py: bool = True) -> List[str]:
    files = read_files_in_dir(file_path, filter_function=python_filter)
    if strip_py:
        files = [f.replace(".py", "") for f in files]
    return files


def abspath_current_dir(file: str) -> str:
    return abspath_dir(file, dirs_up=0)


def abspath_dir(file: str, dirs_up: int = 0) -> str:
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
    path: PathLike, include_parent: bool = False, join_parent: str = "/"
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


def join_if_not_absolute(base_path: PathLike, relative: str) -> str:
    if relative.startswith("/"):
        return relative
    return os.path.join(base_path, relative)


def relative_to_safe(base_path: Path, relative: Path) -> Path:
    try:
        return relative.relative_to(base_path)
    except ValueError:
        return relative


def copy(
    src: PathLike, dest: PathLike, clean_dest: bool = False, ensure_parents=True
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


def ensure_parents_write_text(path: Path, text: str, log: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    if log:
        print(f"writing to {path}", f"text={text}", sep="\n")


def file_modified_time(path: PathLike) -> float:
    return os.path.getmtime(path)


IMG_EXTENSIONS = (".jpeg", ".gif", ".png")


def is_image_file(path: PathLike) -> bool:
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


def touch(path: str, times: int | tuple[int, int] | None = None):
    """Equivalent of unix `touch path`.

    Reference: import from pantsbuild.pants util package
    :API: public

    :path: The file to touch.
    :times Either a tuple of (atime, mtime) or else a single time to use for both.  If not
           specified both atime and mtime are updated to the current time.
    """
    if isinstance(times, tuple) and len(times) > 2:
        raise ValueError(
            "`times` must either be a tuple of (atime, mtime) or else a single time to use for both."
        )
    if isinstance(times, int):
        times = (times, times)
    Path(path).parent.mkdir(exist_ok=True, parents=True)
    with open(path, "a"):
        os.utime(path, times)
