# CLI interface domain

from pkg_ext.cli.commands import app


def main():
    from ask_shell._internal.typer_command import configure_logging

    configure_logging(app)
    app()


__all__ = ["main", "app"]
