"""Utility functions for the flat package."""


def read_file(path: str) -> str:
    """Read file contents."""
    with open(path) as f:
        return f.read()


def write_file(path: str, content: str) -> None:
    """Write content to file."""
    with open(path, "w") as f:
        f.write(content)
