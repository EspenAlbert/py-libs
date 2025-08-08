from pathlib import Path

from ask_shell import configure_logging, run_and_wait
from typer import Argument, Typer

app = Typer()


@app.command()
def run_failing_command(
    provider_dir: Path = Argument(help="Path to terraform example directory"),
):
    run_and_wait(
        "terraform providers schema -json", cwd=Path(provider_dir), ansi_content=False
    )


def main():
    configure_logging(app)
    app()


if __name__ == "__main__":
    main()
