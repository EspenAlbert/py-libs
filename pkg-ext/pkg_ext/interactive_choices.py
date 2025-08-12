from ask_shell._internal.interactive import (
    ChoiceTyped,
    NewHandlerChoice,
    SelectOptions,
    confirm,
    select_list_choice,
)

from pkg_ext.errors import NoPublicGroupMatch
from pkg_ext.models import (
    PublicGroup,
    PublicGroups,
    RefSymbol,
    SymbolType,
    ref_id,
)


def as_choices(groups: PublicGroups) -> list[ChoiceTyped[PublicGroup]]:
    return [
        ChoiceTyped(
            name=group.name,
            value=group,
            description="Don't belong to a group, rather at top level"
            if group.is_root
            else "",
        )
        for group in groups.groups
    ]


def new_public_group_constructor(
    groups: PublicGroups, rel_path: str, symbol_name: str
) -> SelectOptions[PublicGroup]:
    def new_public_group(name: str) -> PublicGroup:
        group = groups.add_group(PublicGroup(name=name))
        ref = RefSymbol(name=symbol_name, type=SymbolType.UNKNOWN, rel_path=rel_path)
        groups.add_ref(ref, name)
        return group

    return SelectOptions(
        new_handler_choice=NewHandlerChoice(
            new_public_group, "enter name of new public group"
        )
    )


def select_group(groups: PublicGroups, rel_path: str, symbol_name: str) -> PublicGroup:
    try:
        group = groups.matching_group(symbol_name, rel_path)
        if confirm(
            f"group {group.name} is ok for {ref_id(rel_path, symbol_name)}?",
            default=True,
        ):
            return group
    except NoPublicGroupMatch:
        pass
    choices = as_choices(groups)
    return select_list_choice(
        "Choose public API group name",
        choices,
        options=new_public_group_constructor(groups, rel_path, symbol_name),
    )
