from pathlib import Path

from ask_shell import models, settings
from pkg_ext import PkgSrcFile, create_refs, parse_symbols

ASK_SHELL_PKG_IMPORT_NAME = "ask_shell"


def test_parse_symbols():
    settings_path = Path(settings.__file__)
    symbols = parse_symbols(
        settings_path, settings_path.name, ASK_SHELL_PKG_IMPORT_NAME
    )
    assert isinstance(symbols, PkgSrcFile)
    assert symbols.path == settings_path
    assert symbols.relative_path == settings_path.name
    assert symbols.local_imports == {"ask_shell._run_env:interactive_shell"}
    assert symbols.classes == ["AskShellSettings"]
    assert symbols.functions == ["default_callbacks_funcs", "default_rich_info_style"]


def test_parse_type_aliases():
    models_path = Path(models.__file__)
    symbols = parse_symbols(models_path, models_path.name, ASK_SHELL_PKG_IMPORT_NAME)
    assert isinstance(symbols, PkgSrcFile)
    assert symbols.path == models_path
    assert symbols.relative_path == models_path.name
    assert "ask_shell.settings:AskShellSettings" in symbols.local_imports
    assert "OutputCallbackT" in symbols.type_aliases
    assert "ShellRunEventT" in symbols.type_aliases
    assert "ERROR_MESSAGE_INTERACTIVE_SHELL" in symbols.global_vars
    found_symbols = [
        (symbol.name, symbol.type) for symbol in sorted(symbols.iterate_ref_symbols())
    ]
    expected_symbols = [
        ("ERROR_MESSAGE_INTERACTIVE_SHELL", "global_var"),
        ("EmptyOutputError", "exception"),
        ("OutputCallbackT", "type_alias"),
        ("OutputT", "type_alias"),
        ("RunIncompleteError", "exception"),
        ("ShellConfig", "class"),
        ("ShellError", "exception"),
        ("ShellInput", "class"),
        ("ShellRun", "class"),
        ("ShellRunAfter", "class"),
        ("ShellRunBefore", "class"),
        ("ShellRunCallbackT", "type_alias"),
        ("ShellRunEventT", "type_alias"),
        ("ShellRunPOpenStarted", "class"),
        ("ShellRunQueueT", "type_alias"),
        ("ShellRunRetryAttempt", "class"),
        ("ShellRunStdOutput", "class"),
        ("ShellRunStdReadError", "class"),
        ("ShellRunStdStarted", "class"),
    ]
    missing_symbols = set(expected_symbols) - set(found_symbols)
    assert not missing_symbols, f"Missing symbols: {missing_symbols}"


def test_create_refs():
    models_path = Path(models.__file__)
    models_parsed = parse_symbols(
        models_path, models_path.name, ASK_SHELL_PKG_IMPORT_NAME
    )
    assert isinstance(models_parsed, PkgSrcFile)
    settings_path = Path(settings.__file__)
    settings_parsed = parse_symbols(
        settings_path, settings_path.name, ASK_SHELL_PKG_IMPORT_NAME
    )
    assert isinstance(settings_parsed, PkgSrcFile)
    refs = create_refs([models_parsed, settings_parsed], ASK_SHELL_PKG_IMPORT_NAME)
    assert refs
    settings_ref = "ask_shell.settings:AskShellSettings"
    actual_ref = refs.get(settings_ref)
    assert actual_ref is not None, f"Reference for {settings_ref} not found"
    assert actual_ref.src_usages == ["models.py"]


def test_parse_symbols_run_env():
    from ask_shell import _run_env

    run_env_path = Path(_run_env.__file__)
    symbols = parse_symbols(run_env_path, run_env_path.name, ASK_SHELL_PKG_IMPORT_NAME)
    assert isinstance(symbols, PkgSrcFile)
    assert symbols.functions == ["interactive_shell"]
    all_symbols = list(symbols.iterate_ref_symbols())
    symbols = {symbol.name: symbol for symbol in all_symbols}
    assert len(symbols) == len(all_symbols)
    assert "interactive_shell" in symbols
    assert symbols["interactive_shell"].type == "function"
