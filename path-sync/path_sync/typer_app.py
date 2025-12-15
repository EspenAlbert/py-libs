import typer

app = typer.Typer(
    name="path-sync",
    help="Sync files across repositories",
    pretty_exceptions_enable=False,
    pretty_exceptions_show_locals=False,
)
