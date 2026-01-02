"""Helper functions for the flat package."""


def format_name(first: str, last: str) -> str:
    """Format full name from parts."""
    return f"{first} {last}"


def parse_version(version: str) -> tuple[int, int, int]:
    """Parse semantic version string."""
    parts = version.split(".")
    return int(parts[0]), int(parts[1]), int(parts[2])
