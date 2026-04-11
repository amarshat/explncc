"""CLI ``viz`` command."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from explncc.cli import app

runner = CliRunner()
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "inline_miss_no_definition.opt.yaml"


def test_viz_mermaid_stdout() -> None:
    result = runner.invoke(
        app,
        ["viz", str(FIXTURE), "--format", "mermaid", "--style", "pass-summary", "--top", "8"],
    )
    assert result.exit_code == 0
    assert "flowchart" in result.stdout


def test_viz_json_stdout() -> None:
    result = runner.invoke(
        app,
        ["viz", str(FIXTURE), "--format", "json", "--style", "pass-remark"],
    )
    assert result.exit_code == 0
    assert '"mermaid"' in result.stdout


def test_viz_unknown_style() -> None:
    result = runner.invoke(app, ["viz", str(FIXTURE), "--style", "galaxy-brain"])
    assert result.exit_code == 2
