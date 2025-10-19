from __future__ import annotations

from ask_shell._internal.interactive import ChoiceTyped
from model_lib.model_base import Entity
from pydantic import Field
from zero_3rdparty.enum_utils import StrEnum

from .py_symbols import RefSymbol


class RefStateType(StrEnum):
    UNSET = "unset"
    EXPOSED = "exposed"
    HIDDEN = "hidden"
    DEPRECATED = "deprecated"
    DELETED = "deleted"


class RefState(Entity):
    name: str
    type: RefStateType = RefStateType.UNSET

    def as_choice(self) -> ChoiceTyped:
        return ChoiceTyped(
            name=self.name, value=self.name, description=f"State: {self.type.value}"
        )

    @property
    def exist_in_code(self) -> bool:
        return self.type in {RefStateType.EXPOSED, RefStateType.DEPRECATED}


class RefStateWithSymbol(RefState):
    symbol: RefSymbol = Field(
        description="Reference symbol, should be set for this state"
    )

    def as_choice(self) -> ChoiceTyped:
        return ChoiceTyped(
            name=self.symbol.local_id,
            value=self.name,
            description=self.symbol.docstring,
        )

    def __eq__(self, value: object) -> bool:
        if not isinstance(value, RefStateWithSymbol):
            return False
        return str(self.symbol) == str(value.symbol)

    def __hash__(self) -> int:
        return hash(str(self.symbol))
