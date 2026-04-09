"""Command-line entry point for explncc."""

from __future__ import annotations

import typer

from explncc import __version__

app = typer.Typer(
    name="explncc",
    no_args_is_help=False,
    add_completion=False,
    help="Parse and analyze Clang/LLVM optimization remark logs (.opt.yaml).",
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def _main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        callback=_version_callback,
        is_eager=True,
        help="Print version and exit.",
    ),
) -> None:
    """Explain Compiler — optimization logs for real-world performance work."""
    if ctx.invoked_subcommand is not None:
        return
    typer.echo(ctx.get_help())


@app.command("version")
def version_cmd() -> None:
    """Print the explncc version string."""
    typer.echo(__version__)


def main() -> None:
    """Invoke the Typer application (used by setuptools entry point)."""
    app()


if __name__ == "__main__":
    main()
