"""Offline / no-network guardrails (config + backend runner + CLI env)."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from explncc.cli import app
from explncc.config import load_config
from explncc.explain.backends import run_explanation
from explncc.models import OptimizationRecord

runner = CliRunner()

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "inline_miss_no_definition.opt.yaml"


def _rec() -> OptimizationRecord:
    return OptimizationRecord(kind="missed", pass_name="loop-vectorize", message="may alias")


def test_config_no_network_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXPLNCC_NO_NETWORK", "1")
    assert load_config().no_network is True


def test_config_offline_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXPLNCC_OFFLINE", "true")
    assert load_config().no_network is True


def test_config_default_allows_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EXPLNCC_NO_NETWORK", raising=False)
    monkeypatch.delenv("EXPLNCC_OFFLINE", raising=False)
    assert load_config().no_network is False


def test_run_explanation_blocks_network_when_no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXPLNCC_NO_NETWORK", "1")
    config = load_config()
    with pytest.raises(ValueError, match="no-network"):
        run_explanation([_rec()], backend="openai", config=config)


def test_run_explanation_rule_always_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXPLNCC_NO_NETWORK", "1")
    config = load_config()
    text = run_explanation([_rec()], backend="rule", config=config)
    assert isinstance(text, str)


def test_cli_env_no_network_blocks_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXPLNCC_NO_NETWORK", "1")
    result = runner.invoke(app, ["explain", str(FIXTURE), "--backend", "openai"])
    assert result.exit_code == 2
    assert "no-network" in result.output.lower() or "EXPLNCC_NO_NETWORK" in result.output


def test_doctor_reports_offline_first() -> None:
    result = runner.invoke(app, ["doctor", "--format", "json"])
    assert result.exit_code == 0
    assert "offline_first" in result.output
