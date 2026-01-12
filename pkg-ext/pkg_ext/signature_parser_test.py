from dataclasses import dataclass

from pydantic import BaseModel, Field, computed_field

from pkg_ext.models.api_dump import ParamKind
from pkg_ext.signature_parser import (
    parse_class_fields,
    parse_direct_bases,
    parse_signature,
)


def sample_func(a: int, b: str = "hello", *args, kwonly: bool = False, **kwargs) -> str:
    return ""


class SampleModel(BaseModel):
    name: str
    count: int = Field(default=0, description="A count field")

    @computed_field
    @property
    def double_count(self) -> int:
        return self.count * 2


@dataclass
class SampleDataclass:
    name: str
    value: int = 10


class ChildClass(SampleModel):
    extra: str = ""


def test_parse_signature_covers_all_param_kinds():
    sig = parse_signature(sample_func)
    assert len(sig.parameters) == 5
    kinds = [p.kind for p in sig.parameters]
    assert ParamKind.POSITIONAL_OR_KEYWORD in kinds
    assert ParamKind.VAR_POSITIONAL in kinds
    assert ParamKind.KEYWORD_ONLY in kinds
    assert ParamKind.VAR_KEYWORD in kinds
    assert sig.return_annotation == "str"


def test_parse_pydantic_model_fields():
    fields = parse_class_fields(SampleModel)
    assert fields
    field_names = [f.name for f in fields]
    assert "name" in field_names
    assert "count" in field_names
    assert "double_count" in field_names
    computed = next(f for f in fields if f.name == "double_count")
    assert computed.is_computed


def test_parse_dataclass_fields():
    fields = parse_class_fields(SampleDataclass)
    assert fields
    assert len(fields) == 2
    value_field = next(f for f in fields if f.name == "value")
    assert value_field.default
    assert value_field.default.value_repr == "10"


def test_parse_direct_bases():
    bases = parse_direct_bases(ChildClass)
    assert "SampleModel" in bases
