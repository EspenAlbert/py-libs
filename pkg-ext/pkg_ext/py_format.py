"""Python file formatting utilities.

Provides functions to format Python files using ruff check --fix and ruff format.
"""

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_LINE_LENGTH = 80


def _run_ruff_stdin(args: list[str], code: str) -> str | None:
    try:
        result = subprocess.run(
            ["ruff", *args, "-"],
            input=code,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.rstrip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def format_python_string(code: str, line_length: int = DEFAULT_LINE_LENGTH) -> str:
    """Format and lint-fix Python code string using ruff."""
    # First run check --fix to add missing imports etc
    fixed = _run_ruff_stdin(
        ["check", "--fix", "--stdin-filename", "_.py", "--isolated"], code
    )
    code = fixed if fixed is not None else code
    # Then format
    formatted = _run_ruff_stdin(["format", "--line-length", str(line_length)], code)
    return formatted if formatted is not None else code


def _run_command_on_files(cmd: tuple[str, ...], paths: list[Path]) -> bool:
    result = subprocess.run(
        [*cmd, *[str(p) for p in paths]], check=False, capture_output=True
    )
    if result.returncode != 0:
        logger.debug(
            "Command %s exited with code %d: %s",
            cmd,
            result.returncode,
            result.stderr.decode() if result.stderr else "",
        )
    return result.returncode == 0


def format_python_files(
    paths: list[Path],
    format_command: tuple[str, ...] | None = None,
) -> bool:
    """Run ruff check --fix then the format command on Python files."""
    if not paths:
        return False

    # Always run check --fix first
    _run_command_on_files(("ruff", "check", "--fix"), paths)

    # Then run the format command if provided
    if format_command:
        _run_command_on_files(format_command, paths)

    return True
