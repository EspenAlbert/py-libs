from pkg_ext.changelog.actions import (
    ChangelogAction,
    parse_changelog_actions,
)
from pkg_ext.interactive import on_new_ref
from pkg_ext.models import PkgCodeState, PublicGroups
from pkg_ext.pkg_state import PkgExtState
from pkg_ext.settings import PkgSettings


def parse_changelog(
    settings: PkgSettings, code_state: PkgCodeState | None = None
) -> tuple[PkgExtState, list[ChangelogAction]]:
    changelog_path = settings.changelog_dir
    changelog_path.mkdir(parents=True, exist_ok=True)
    actions = parse_changelog_actions(changelog_path)
    groups = settings.parse_computed_public_groups(PublicGroups)
    tool_state = PkgExtState(
        repo_root=settings.repo_root,
        changelog_dir=changelog_path,
        pkg_path=settings.pkg_directory,
        groups=groups,
    )
    for action in actions:
        tool_state.update_state(action)
    extra_actions = []
    # Skip group selection for flat packages - they don't use the public API workflow
    if code_state and not settings.is_flat:
        for name in tool_state.refs:
            if ref_symbol := tool_state.code_ref(code_state, name):
                if new_action := on_new_ref(groups)(ref_symbol):
                    extra_actions.append(new_action)
    return tool_state, extra_actions
