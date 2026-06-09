"""bench-backends: honest latency rows, explicit skip rows, no surprises."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from typer.testing import CliRunner

from explncc import bench_backends
from explncc.bench_backends import BenchRow, render_bench, run_bench
from explncc.cli import app
from explncc.config import load_config
from explncc.explain.per_finding import FindingExplanation
from explncc.fusion import fuse_records
from explncc.records_loader import load_records
from explncc.why_output import verdict_tag

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "fusion" / "hot.opt.yaml"

runner = CliRunner()


def _missed_findings():  # noqa: ANN202
    records = load_records(FIXTURE)
    return [f for f in fuse_records(records, name_map={}) if verdict_tag(f) == "MISS"]


def test_rule_backend_benches_offline_and_deterministically() -> None:
    findings = _missed_findings()
    rows = run_bench(findings, config=load_config(), backends=["rule"])
    assert len(rows) == 1
    row = rows[0]
    assert row.backend == "rule"
    assert row.mode == "generate"
    assert row.findings == len(findings)
    assert row.fallbacks == 0
    assert row.chars > 0


def test_unreachable_ollama_becomes_skip_row(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bench_backends, "_ollama_tags", lambda host, timeout=2.0: None)
    rows = run_bench(_missed_findings(), config=load_config(), backends=["ollama"])
    assert rows[0].mode == "skipped"
    assert "unreachable" in (rows[0].note or "")


def test_model_not_pulled_becomes_skip_row(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        bench_backends,
        "_ollama_tags",
        lambda host, timeout=2.0: ["other:latest"],
    )
    rows = run_bench(
        _missed_findings(),
        config=load_config(),
        backends=["ollama"],
        ollama_models=["absent-model"],
    )
    assert rows[0].mode == "skipped"
    assert rows[0].note == "model not pulled"


def test_bare_tag_matches_latest(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        bench_backends, "_ollama_tags", lambda host, timeout=2.0: ["mistral:latest"]
    )

    def fake_explain(finding, *, backend, config, on_chunk=None):  # noqa: ANN001
        return FindingExplanation(
            text="x", backend=backend, model=config.ollama_model, latency_ms=1
        )

    monkeypatch.setattr(bench_backends, "explain_finding", fake_explain)
    rows = run_bench(
        _missed_findings(),
        config=load_config(),
        backends=["ollama"],
        ollama_models=["mistral"],
        include_cached=False,
    )
    assert rows[0].mode == "generate"
    assert rows[0].model == "mistral"


def test_no_network_guardrail_skips_network_backends() -> None:
    cfg = replace(load_config(), no_network=True)
    rows = run_bench(_missed_findings(), config=cfg, backends=["rule", "ollama", "openai"])
    assert rows[0].backend == "rule"
    assert rows[0].mode == "generate"
    assert all(r.mode == "skipped" for r in rows[1:])
    assert all("no-network" in (r.note or "") for r in rows[1:])


def test_missing_api_keys_become_skip_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    rows = run_bench(_missed_findings(), config=load_config(), backends=["openai", "claude"])
    assert [r.mode for r in rows] == ["skipped", "skipped"]
    assert "OPENAI_API_KEY unset" in (rows[0].note or "")
    assert "ANTHROPIC_API_KEY unset" in (rows[1].note or "")


def test_render_text_and_markdown() -> None:
    rows = [
        BenchRow(
            backend="rule",
            model=None,
            mode="generate",
            findings=3,
            total_ms=12,
            cache_hits=0,
            fallbacks=0,
            chars=420,
        ),
        BenchRow(
            backend="ollama",
            model="m:3b",
            mode="skipped",
            findings=0,
            total_ms=0,
            cache_hits=0,
            fallbacks=0,
            chars=0,
            note="model not pulled",
        ),
    ]
    text = render_bench(rows, fmt="text")
    assert "backend" in text and "per finding" in text
    md = render_bench(rows, fmt="markdown")
    assert md.startswith("| backend |")
    assert "| ollama | m:3b | skipped | - | - | - | model not pulled |" in md


def test_bench_cli_rule_only() -> None:
    result = runner.invoke(
        app,
        ["bench-backends", str(FIXTURE), "--backend", "rule", "--format", "markdown"],
    )
    assert result.exit_code == 0
    assert "| rule | - | generate | 3 |" in result.stdout
    assert "wall-clock on this machine" in result.output
