import logging

from path_sync import cmd_boot, cmd_copy, cmd_validate  # noqa: F401
from path_sync.models import LOG_FORMAT
from path_sync.typer_app import app


def main() -> None:
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
    app()


if __name__ == "__main__":
    main()
