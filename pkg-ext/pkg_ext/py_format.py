"""Python file formatting utilities.

Provides functions to format Python files using a configurable format command
(default: ruff format). Use these utilities whenever writing Python files.
"""

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def format_python_files(
    paths: list[Path],
    format_command: tuple[str, ...] | None = None,
) -> bool:
    """Format Python files using the specified format command.

    Args:
        paths: List of paths to Python files to format.
        format_command: Command to use for formatting (e.g., ("ruff", "format")).
                       If None or empty, formatting is skipped.

    Returns:
        True if formatting was executed, False if skipped.
    """
    if not paths or not format_command:
        return False

    result = subprocess.run(
        [*format_command, *[str(p) for p in paths]],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        logger.debug(
            "Format command exited with code %d: %s",
            result.returncode,
            result.stderr.decode() if result.stderr else "",
        )
    return True
