from pkg_ext.changelog.actions import (
    ChangelogAction,
    ChangelogActionType,
    dump_changelog_actions,
)
from pkg_ext.changelog.write_changelog_md import read_changelog_section


def test_dump_changelog_actions(text_normalizer_regression, tmp_path):
    actions = [ChangelogAction(name="test", type=ChangelogActionType.EXPOSE)]
    out_path = tmp_path / "test.yaml"
    dump_changelog_actions(out_path, actions)
    text_normalizer_regression(out_path)


_example_changelog = """\
# Changelog

## 0.1.1 2025-10-18 21:13:06.12345+00:00

### __Root__
- fix: adds chosen file (GIT_SHA)


## 0.1.0 2025-10-18 21:13:06.12345+00:00

### Git_Inferred
- New function inferred
"""

_011 = """\
## 0.1.1 2025-10-18 21:13:06.12345+00:00

### __Root__
- fix: adds chosen file (GIT_SHA)
"""
_010 = """\
## 0.1.0 2025-10-18 21:13:06.12345+00:00

### Git_Inferred
- New function inferred
"""


def test_read_changelog():
    assert read_changelog_section(_example_changelog, "0.1.0", "0.1.1") == _011
    assert read_changelog_section(_example_changelog, "", "0.1.0") == _010
    assert read_changelog_section(_example_changelog, "doesn't exist", "0.1.0") == _010
