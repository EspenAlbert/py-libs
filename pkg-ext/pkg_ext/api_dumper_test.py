from dataclasses import dataclass

from pydantic import BaseModel

from pkg_ext import api_dumper


@dataclass
class DataclassNoDoc:
    foo: bool = False
    bar: str = ""


@dataclass
class DataclassWithDoc:
    """My dataclass docstring."""

    foo: bool = False


class PydanticNoDoc(BaseModel):
    foo: bool = False
    bar: str = ""


class PydanticWithDoc(BaseModel):
    """My pydantic docstring."""

    foo: bool = False


class RegularClassNoDoc:
    pass


class RegularClassWithDoc:
    """My regular class docstring."""

    pass


def test_is_auto_generated_dataclass_doc():
    assert api_dumper._is_auto_generated_dataclass_doc(DataclassNoDoc)
    assert not api_dumper._is_auto_generated_dataclass_doc(DataclassWithDoc)
    assert not api_dumper._is_auto_generated_dataclass_doc(PydanticNoDoc)
    assert not api_dumper._is_auto_generated_dataclass_doc(PydanticWithDoc)
    assert not api_dumper._is_auto_generated_dataclass_doc(RegularClassNoDoc)
    assert not api_dumper._is_auto_generated_dataclass_doc(RegularClassWithDoc)


def test_get_class_docstring():
    assert api_dumper._get_class_docstring(DataclassNoDoc) == ""
    assert (
        api_dumper._get_class_docstring(DataclassWithDoc) == "My dataclass docstring."
    )
    assert api_dumper._get_class_docstring(PydanticNoDoc) == ""
    assert api_dumper._get_class_docstring(PydanticWithDoc) == "My pydantic docstring."
    assert api_dumper._get_class_docstring(RegularClassNoDoc) == ""
    assert (
        api_dumper._get_class_docstring(RegularClassWithDoc)
        == "My regular class docstring."
    )
