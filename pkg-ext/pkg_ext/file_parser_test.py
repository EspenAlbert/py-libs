from pathlib import Path

from ask_shell import settings
from ask_shell._internal import _run_env, interactive, models

from pkg_ext.file_parser import parse_code_symbols, parse_symbols
from pkg_ext.models import PkgSrcFile

ASK_SHELL_PKG_IMPORT_NAME = "ask_shell"


def _parse_src_module(module) -> PkgSrcFile:
    module_path = Path(module.__file__)
    pkg_path = next(
        parent
        for parent in module_path.parents
        if parent.name == ASK_SHELL_PKG_IMPORT_NAME
    )
    rel_path = module_path.relative_to(pkg_path)
    result = parse_symbols(module_path, str(rel_path), ASK_SHELL_PKG_IMPORT_NAME)
    assert isinstance(result, PkgSrcFile)
    return result


def test_parse_symbols():
    symbols = _parse_src_module(settings)
    settings_path = Path(settings.__file__)
    assert symbols.path == settings_path
    assert symbols.relative_path == settings_path.name
    assert symbols.local_imports == set()
    assert symbols.classes == ["AskShellSettings"]
    assert symbols.functions == [
        "default_callbacks_funcs",
        "default_remove_os_secrets",
        "as_upper",
        "default_rich_info_style",
    ]


def test_parse_models_module():
    symbols = _parse_src_module(models)
    assert "ask_shell.settings.AskShellSettings" in symbols.local_imports
    assert "ERROR_MESSAGE_INTERACTIVE_SHELL" in symbols.global_vars
    found_symbols = [
        (symbol.name, symbol.type) for symbol in sorted(symbols.iterate_ref_symbols())
    ]
    expected_symbols = [
        ("ERROR_MESSAGE_INTERACTIVE_SHELL", "global_var"),
        ("EmptyOutputError", "exception"),
        ("OutputT", "type_alias"),
        ("RunIncompleteError", "exception"),
        ("ShellConfig", "class"),
        ("ShellError", "exception"),
        ("ShellInput", "class"),
        ("ShellRun", "class"),
    ]
    missing_symbols = set(expected_symbols) - set(found_symbols)
    assert not missing_symbols, f"Missing symbols: {missing_symbols}"


def test_create_refs():
    models_parsed = _parse_src_module(models)
    settings_parsed = _parse_src_module(settings)
    refs = parse_code_symbols(
        [models_parsed, settings_parsed], ASK_SHELL_PKG_IMPORT_NAME
    )
    assert refs
    settings_ref = "ask_shell.settings.AskShellSettings"
    actual_ref = refs.get(settings_ref)
    assert actual_ref is not None, f"Reference for {settings_ref} not found"
    assert actual_ref.src_usages == ["_internal/models.py"]


def test_parse_symbols_run_env():
    symbols = _parse_src_module(_run_env)
    assert symbols.functions == ["interactive_shell"]
    all_symbols = list(symbols.iterate_ref_symbols())
    symbols = {symbol.name: symbol for symbol in all_symbols}
    assert len(symbols) == len(all_symbols)
    assert "interactive_shell" in symbols
    assert symbols["interactive_shell"].type == "function"
    assert "ENV_PREFIX" not in symbols


def test_parse_type_alias_interactive():
    file = _parse_src_module(interactive)
    symbols = parse_code_symbols([file], "ask_shell")
    assert symbols["ask_shell._internal.interactive.FuncT"]
