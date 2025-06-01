from ask_shell._run_env import interactive_shell


def test_interactive_shell():
    assert not interactive_shell()
