from __future__ import annotations

from ask_shell._internal.typer_command import configure_logging

from pkg_ext.cli.commands import app


def main():
    configure_logging(app)
    app()


if __name__ == "__main__":
    main()
