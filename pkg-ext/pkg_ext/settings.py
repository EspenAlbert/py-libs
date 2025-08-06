from os import getenv


def get_editor() -> str:
    return getenv("EDITOR", "code")
