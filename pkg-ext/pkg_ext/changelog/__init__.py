# Changelog management domain
#
# Note: parser.py and write_changelog_md.py are intentionally NOT imported here
# to avoid circular imports. They depend on pkg_ext.context and pkg_ext.pkg_state
# which in turn import from this package. Import them directly when needed:
#   from pkg_ext.changelog.parser import parse_changelog
#   from pkg_ext.changelog.write_changelog_md import write_changelog_md

from .actions import (
    AdditionalChangeAction,
    BreakingChangeAction,
    BumpType,
    ChangelogAction,
    ChangelogActionBase,
    DeleteAction,
    DeprecatedAction,
    ExperimentalAction,
    FixAction,
    GAAction,
    GroupModuleAction,
    KeepPrivateAction,
    MakePublicAction,
    MaxBumpTypeAction,
    ReleaseAction,
    RenameAction,
    StabilityTarget,
    changelog_filepath,
    default_changelog_path,
    dump_changelog_actions,
    parse_changelog_actions,
    parse_changelog_file_path,
)

__all__ = [
    "AdditionalChangeAction",
    "BreakingChangeAction",
    "BumpType",
    "ChangelogAction",
    "ChangelogActionBase",
    "DeleteAction",
    "DeprecatedAction",
    "ExperimentalAction",
    "FixAction",
    "GAAction",
    "GroupModuleAction",
    "KeepPrivateAction",
    "MakePublicAction",
    "MaxBumpTypeAction",
    "ReleaseAction",
    "RenameAction",
    "StabilityTarget",
    "changelog_filepath",
    "default_changelog_path",
    "dump_changelog_actions",
    "parse_changelog_actions",
    "parse_changelog_file_path",
]
