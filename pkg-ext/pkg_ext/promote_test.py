import pytest
from typer.testing import CliRunner

from pkg_ext.changelog import KeepPrivateAction
from pkg_ext.cli import app
from pkg_ext.models import RefSymbol, SymbolType
from pkg_ext.reference_handling import promote

runner = CliRunner()


@pytest.fixture
def sample_private_action():
    return KeepPrivateAction(name="dump_as_str", full_path="serialize.dump.dump_as_str")


@pytest.fixture
def sample_ref_symbol():
    return RefSymbol(
        name="dump_as_str",
        module_path="serialize.dump",
        rel_path="serialize/dump.py",
        type=SymbolType.FUNCTION,
        docstring="Dumps model as string",
        src_usages=[],
        test_usages=[],
    )


def test_promote_command_registered():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "promote" in result.output


def test_filter_functions(sample_private_action, sample_ref_symbol):
    entries = [(sample_private_action, sample_ref_symbol)]

    assert promote.filter_by_module(entries, "serialize.dump") == entries
    assert promote.filter_by_module(entries, "serialize") == entries
    assert not promote.filter_by_module(entries, "other.module")

    assert promote.filter_by_pattern(entries, "dump_*") == entries
    assert promote.filter_by_pattern(entries, "*_str") == entries
    assert not promote.filter_by_pattern(entries, "parse_*")


def test_match_symbol_in_code(sample_private_action, sample_ref_symbol):
    class MockCodeState:
        import_id_refs = {"serialize.dump.dump_as_str": sample_ref_symbol}

    assert (
        promote.match_symbol_in_code(sample_private_action, MockCodeState())
        == sample_ref_symbol
    )

    class EmptyCodeState:
        import_id_refs = {}

    assert promote.match_symbol_in_code(sample_private_action, EmptyCodeState()) is None


def test_filter_with_none_private_action(sample_ref_symbol):
    entries = [(None, sample_ref_symbol)]

    assert promote.filter_by_module(entries, "serialize.dump") == entries
    assert promote.filter_by_pattern(entries, "dump_*") == entries
