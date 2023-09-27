import logging
from pathlib import Path
from typing import Any, cast

from compose_chart_export.chart_read import read_chart_name
from model_lib import dump, parse_payload
from zero_3rdparty.dict_nested import (
    iter_nested_key_values,
    read_nested_or_none,
    update,
)
from zero_3rdparty.file_utils import iter_paths_and_relative

logger = logging.getLogger(__name__)


def combine_values_yaml(old: Path, new: Path) -> str:
    parsed_old: dict = cast(dict, parse_payload(old))
    parsed_new: dict = cast(dict, parse_payload(new))
    chart_name = read_chart_name(new.parent)
    old_value: Any
    for nested_key, old_value in iter_nested_key_values(parsed_old):
        new_value = read_nested_or_none(parsed_new, nested_key)
        if isinstance(old_value, dict) or new_value == old_value:
            continue
        logger.warning(
            f"chart={chart_name} using old value for {nested_key}={old_value} instead of {new_value}"
        )
        update(parsed_new, nested_key, old_value)
    return dump(parsed_new, "yaml")


def combine(old_path: Path, new_path: Path) -> None:
    """
    Warnings:
        side effect of changing the new path

    Supports annotation in existing files:
    # FROZEN -> Will not make any updates to the file (needs to be 1st line)
    # Lines with `# noupdate` will be kept as is (only supported at the start and end)
    """
    old_rel_paths: dict[str, Path] = {
        rel_path: path
        for path, rel_path in iter_paths_and_relative(old_path, "*", only_files=True)
    }
    new_rel_paths: dict[str, Path] = {
        rel_path: path
        for path, rel_path in iter_paths_and_relative(new_path, "*", only_files=True)
    }
    for rel_path, path in new_rel_paths.items():
        if existing := old_rel_paths.get(rel_path):
            existing_lines = existing.read_text().splitlines()
            if rel_path == "values.yaml":
                new_content = combine_values_yaml(existing, path)
                path.write_text(new_content)
                continue
            if existing_lines and existing_lines[0] == "# FROZEN":
                logger.warning(f"keeping as is: {rel_path}")
                path.write_text(existing.read_text())
                continue
            all_lines = ensure_no_update_lines_kept(
                existing_lines, path.read_text().splitlines(), rel_path
            )
            path.write_text("\n".join(all_lines) + "\n")
    for rel_path, existing in new_rel_paths.items() - old_rel_paths.items():
        logger.info(f"adding old file not existing in new chart: {rel_path}")
        (new_path / rel_path).write_text(existing.read_text())


def ensure_no_update_lines_kept(
    old_lines: list[str], new_lines: list[str], rel_path: str
) -> list[str]:
    extra_old_lines_start: list[str] = []
    extra_old_lines_end: list[str] = []
    at_start = True
    for line in old_lines:
        if line.endswith("# noupdate"):
            if at_start:
                extra_old_lines_start.append(line)
            else:
                extra_old_lines_end.append(line)
        else:
            at_start = False
    if extra_old_lines_start:
        logger.warning(
            f"keeping {len(extra_old_lines_start)} # noupdate lines at start {rel_path}"
        )
    if extra_old_lines_end:
        logger.warning(
            f"keeping {len(extra_old_lines_end)} # noupdate lines at end {rel_path}"
        )
    return extra_old_lines_start + new_lines + extra_old_lines_end
