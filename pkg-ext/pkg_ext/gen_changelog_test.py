from pkg_ext.gen_changelog import (
    ChangelogAction,
    ChangelogActionType,
    dump_changelog_actions,
)


def test_dump_changelog_actions(text_normalizer_regression, tmp_path):
    actions = [ChangelogAction(name="test", type=ChangelogActionType.EXPOSE)]
    out_path = tmp_path / "test.yaml"
    dump_changelog_actions(out_path, actions)
    text_normalizer_regression(out_path)
