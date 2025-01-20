from __future__ import annotations

import re
import sys
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

REPO_PATH = Path(__file__).parents[1]
MODEL_LIB = "model-lib"
_pkg_names = {
    "m": MODEL_LIB,
    "z": "zero-3rdparty",
}

_pkg_tag_prefix = dict(zip(_pkg_names.values(), _pkg_names.keys()))


def pkg_tag(pkg_name: str, pkg_version: str) -> str:
    return _pkg_tag_prefix[pkg_name] + pkg_version


def find_pkg(pkg_name: str) -> str:
    for key, value in _pkg_names.items():
        if pkg_name == key or pkg_name.lower().replace("_", "-") == value:
            return value
    if pkg_name and (candidate := _pkg_names.get(pkg_name[0])):
        with suppress(ValueError):
            extract_version(candidate, pkg_name[1:])
        return candidate

    raise ValueError(f"Unknown package name: {pkg_name}")


_version_regex = re.compile(
    r"^(VERSION|version)\s+:?=\s+\"(?P<version>\d+\.\d+\.\d+\+?[\w\d]*)\"$", re.M
)


def find_pkg_version(pkg_name: str) -> str:
    _init_path = init_file(pkg_name)
    if not _init_path.exists():
        raise FileNotFoundError(
            f"Could not find package: {pkg_name} @ _init_path: {_init_path}"
        )
    return extract_version(pkg_name, _init_path.read_text())


def init_file(pkg_name: str) -> Path:
    return REPO_PATH / pkg_name / pkg_name.replace("-", "_") / "__init__.py"


def pyproject_file(pkg_name: str) -> Path:
    return REPO_PATH / pkg_name / "pyproject.toml"


def extract_version(pkg_name: str, text: str):
    if match := re.search(_version_regex, text):
        return match["version"]
    raise ValueError(f"Could not find version for package: {pkg_name} in __init__.py: ")


def sub_version(pkg_name: str, old_version: str, new_version: str) -> None:
    def replacer(match: re.Match) -> str:
        return match.group(0).replace(old_version, new_version)

    files = [init_file(pkg_name), pyproject_file(pkg_name)]
    if pkg_name == MODEL_LIB:
        files.append(REPO_PATH / "justfile")
    for path in files:
        if not path.exists():
            raise FileNotFoundError(f"Could not find file: {path} for {pkg_name}")
        new_text = re.sub(_version_regex, replacer, path.read_text(), 1)
        path.write_text(new_text)


@dataclass
class PkgVersion:
    major: int
    minor: int
    patch: int
    extra: str = ""

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

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}{self.extra}"


def main(pkg_name_input: str, command: str):
    pkg_name = find_pkg(pkg_name_input)
    pkg_version = find_pkg_version(pkg_name)
    if command == "read":
        print(pkg_version)
        return
    if command == "tag":
        tag = pkg_tag(pkg_name, pkg_version)
        print(tag)
        return
    if command == "decode-tag":
        print(pkg_name)
        return
    parsed_version = PkgVersion.parse(pkg_version)
    if command in {"bump", "bump-patch", "patch"}:
        new_version = parsed_version.bump_patch()
    elif command in {"bump-minor", "minor"}:
        new_version = parsed_version.bump_minor()
    elif command in {"bump-major", "major"}:
        new_version = parsed_version.bump_major()
    elif command in {"bump-alpha", "alpha"}:
        new_version = parsed_version.bump_alpha()
    elif command in {"bump-beta", "beta"}:
        new_version = parsed_version.bump_beta()
    elif command in {"bump-rc", "rc"}:
        new_version = parsed_version.bump_rc()
    else:
        raise ValueError(f"Unknown command: {command}")
    print(f"bumping from {pkg_version} to {str(new_version)}")
    sub_version(pkg_name, pkg_version, str(new_version))


if __name__ == "__main__":
    *_, pkg_name_input, command = sys.argv
    main(pkg_name_input, command)
