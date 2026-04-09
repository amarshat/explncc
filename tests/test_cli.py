"""Smoke tests for the CLI entry point."""

from __future__ import annotations

from typer.testing import CliRunner

from explncc import __version__
from explncc.cli import app

runner = CliRunner()


def test_version_short_flag() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == __version__


def test_version_subcommand() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == __version__


def test_help_no_subcommand() -> None:
    result = runner.invoke(app, [])
    assert result.exit_code == 0
    assert "explncc" in result.stdout
    assert "version" in result.stdout
