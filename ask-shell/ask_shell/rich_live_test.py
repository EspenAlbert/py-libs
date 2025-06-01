from ask_shell.rich_live import get_live


def test_stopping_live_twice_leads_to_error():
    live = get_live()
    live.stop()
