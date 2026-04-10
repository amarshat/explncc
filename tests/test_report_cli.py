"""CLI ``report`` command."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from explncc.cli import app

runner = CliRunner()
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "inline_miss_no_definition.opt.yaml"


def test_report_markdown_to_stdout() -> None:
    result = runner.invoke(
        app,
        [
            "report",
            str(FIXTURE),
            "--format",
            "markdown",
            "--no-explain",
            "--top-missed",
            "5",
        ],
    )
    assert result.exit_code == 0
    assert "Total remarks" in result.stdout
    assert "inline" in result.stdout


def test_report_json_stdout() -> None:
    result = runner.invoke(
        app,
        ["report", str(FIXTURE), "--format", "json", "--no-explain"],
    )
    assert result.exit_code == 0
    assert '"stats"' in result.stdout


def test_report_fail_on_check_exits_one(tmp_path: Path) -> None:
    out = tmp_path / "r.md"
    result = runner.invoke(
        app,
        [
            "report",
            str(FIXTURE),
            "-o",
            str(out),
            "--format",
            "markdown",
            "--no-explain",
            "--fail-on-check",
            "--max-missed-inline",
            "0",
        ],
    )
    assert result.exit_code == 1
    assert out.is_file()
