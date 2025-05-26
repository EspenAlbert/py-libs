from __future__ import annotations

from enum import StrEnum
from typing import ClassVar


class ContentType(StrEnum):
    DEFAULT = "DEFAULT"
    STDOUT = "STDOUT"
    STDERR = "STDERR"
    WARNING = "WARNING"
    ERROR = "ERROR"

    __colors__: ClassVar[dict[str, str]] = {
        DEFAULT: "",
        STDOUT: "green",
        STDERR: "red",
        ERROR: "bright_red",
        WARNING: "orange_red1",
    }

    @classmethod
    def colors(cls) -> dict[str, str]:
        return {**cls.__colors__}


# directly from rich.color
EXTRA_COLORS: set[str] = {
    "yellow",
    "blue",
    "magenta",
    "cyan",
    "bright_black",
    "bright_green",
    "bright_blue",
    "bright_magenta",
    "bright_cyan",
    "navy_blue",
    "dark_blue",
    "blue3",
    "blue1",
    "dark_green",
    "deep_sky_blue4",
    "dodger_blue3",
    "dodger_blue2",
    "green4",
    "spring_green4",
    "turquoise4",
    "deep_sky_blue3",
    "red3",
    "deep_pink3",
    "magenta3",
    "dark_orange3",
    "indian_red",
    "hot_pink3",
    "hot_pink2",
    "orchid",
    "orange3",
}
