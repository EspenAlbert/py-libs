from __future__ import annotations

import re
from contextlib import suppress
from dataclasses import dataclass
from typing import Callable

from model_lib.metadata.context_dict import identity
from model_lib.serialize.parse import parse_dict

from pkg_ext.changelog import (
    BumpType,
)
from pkg_ext.models import pkg_ctx


@dataclass
class PkgVersion:
    major: int
    minor: int
    patch: int
    extra: str = ""

    @classmethod
    def default(cls) -> PkgVersion:
        return cls.parse("0.0.0")

    @classmethod
    def parse(cls, raw: str) -> PkgVersion:
        assert raw.count(".") == 2, f"Invalid version string: {raw}"
        major, minor, patch = raw.split(".")
        extra = ""
        if non_digit := re.search(r"\D", patch):
            patch, extra = patch[: non_digit.start()], patch[non_digit.start() :]
        return cls(int(major), int(minor), int(patch), extra)

    def bump_major(self) -> PkgVersion:
        return PkgVersion(self.major + 1, 0, 0)

    def bump_minor(self) -> PkgVersion:
        return PkgVersion(self.major, self.minor + 1, 0)

    def bump_patch(self) -> PkgVersion:
        return PkgVersion(self.major, self.minor, self.patch + 1)

    def bump_rc(self) -> PkgVersion:
        if self.extra.startswith("rc"):
            rc = int(self.extra[2:])
            return PkgVersion(self.major, self.minor, self.patch, f"rc{rc + 1}")
        return PkgVersion(self.major, self.minor, self.patch, "rc1")

    def bump_alpha(self) -> PkgVersion:
        if self.extra.startswith("a"):
            alpha = int(self.extra[1:])
            return PkgVersion(self.major, self.minor, self.patch, f"a{alpha + 1}")
        return PkgVersion(self.major, self.minor, self.patch, "a1")

    def bump_beta(self) -> PkgVersion:
        if self.extra.startswith("b"):
            beta = int(self.extra[1:])
            return PkgVersion(self.major, self.minor, self.patch, f"b{beta + 1}")
        return PkgVersion(self.major, self.minor, self.patch, "b1")

    def bump(self, bump_type: BumpType) -> PkgVersion:
        return _bumps[bump_type](self)

    @property
    def is_default(self) -> bool:
        return self == self.parse("0.0.0")

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}{self.extra}"


_bumps: dict[BumpType, Callable[[PkgVersion], PkgVersion]] = {
    BumpType.MAJOR: PkgVersion.bump_major,
    BumpType.MINOR: PkgVersion.bump_minor,
    BumpType.PATCH: PkgVersion.bump_patch,
    BumpType.RC: PkgVersion.bump_rc,
    BumpType.ALPHA: PkgVersion.bump_alpha,
    BumpType.BETA: PkgVersion.bump_beta,
    BumpType.UNDEFINED: identity,
}
# use compile time error if a BumpType is added without a bump method
_missing_bumps = [bump for bump in list(BumpType) if bump not in _bumps]
assert not _missing_bumps, f"missing BumpType found for PkgVersion: {_missing_bumps}"


version_pattern_str = (
    r"^(VERSION|version)\s+:?=\s+\"(?P<version>\d+\.\d+\.\d+\+?[\w\d]*)\"$"
)
_version_regex = re.compile(version_pattern_str, re.M)


def _extract_version(text: str) -> str:
    if match := re.search(_version_regex, text):
        return match["version"]
    return ""


def bump_version(
    ctx: pkg_ctx,
    old_version: PkgVersion,
) -> PkgVersion:
    """Use the .changelog dir to find the bump type"""
    actions = ctx.pr_changelog_actions()
    bumps = [action.bump_type for action in actions]
    bump = BumpType.max_bump_type(bumps)
    return old_version.bump(bump)


def read_current_version(ctx: pkg_ctx):
    """To find the version:
    1. Look in pyproject.toml
    2. Look in __init__.py
    3. Return default 0.0.0"""
    version = PkgVersion.default()  # default if not found
    pyproject_toml = ctx.settings.pyproject_toml
    if pyproject_toml.exists():
        with suppress(Exception):
            pyproject = parse_dict(pyproject_toml)
            version_raw = pyproject["project"]["version"]
            version = PkgVersion.parse(version_raw)
    init_path = ctx.settings.init_path
    if version.is_default and init_path.exists():
        if raw_init_version := _extract_version(init_path.read_text()):
            with suppress(Exception):
                version = PkgVersion.parse(raw_init_version)
    return version


__all__ = [
    "bump_version",
    "read_current_version",
    "PkgVersion",
]
