"""Per-finding short explanations: prompt, cache, fallback, CLI wiring."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from typer.testing import CliRunner

from explncc.cli import app
from explncc.config import load_config
from explncc.explain import per_finding
from explncc.explain.per_finding import (
    build_finding_prompt,
    deterministic_finding_text,
    explain_finding,
    finding_evidence_hash,
)
from explncc.fusion import fuse_records
from explncc.records_loader import load_records

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "fusion" / "hot.opt.yaml"

runner = CliRunner()


def _scan_finding():  # noqa: ANN202
    records = load_records(FIXTURE)
    findings = fuse_records(records, name_map={})
    return next(f for f in findings if f.category == "vectorize-missed")


def test_prompt_is_deterministic_and_evidence_grounded() -> None:
    finding = _scan_finding()
    a = build_finding_prompt(finding)
    b = build_finding_prompt(finding)
    assert a == b
    assert "not vectorized: loop-carried dependence" in a
    assert "Backward loop carried data dependence" in a
    assert "hot.cpp:11" in a
    assert "next:" in a  # the output contract is part of the prompt


def test_finding_evidence_hash_stable_and_distinct() -> None:
    records = load_records(FIXTURE)
    findings = fuse_records(records, name_map={})
    h = [finding_evidence_hash(f) for f in findings]
    assert h == [finding_evidence_hash(f) for f in findings]
    assert len(set(h)) == len(h)


def test_rule_backend_returns_evidence_text_without_model() -> None:
    finding = _scan_finding()
    chunks: list[str] = []
    result = explain_finding(
        finding,
        backend="rule",
        config=load_config(),
        on_chunk=chunks.append,
    )
    assert result.backend == "rule"
    assert result.model is None
    assert result.text == deterministic_finding_text(finding)
    assert "next: Use #pragma clang loop distribute(enable)" in result.text
    assert chunks == [result.text]


def test_model_result_cached_per_finding(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    finding = _scan_finding()
    calls = {"n": 0}

    def fake_stream(config, user, on_chunk):  # noqa: ANN001
        calls["n"] += 1
        if on_chunk:
            on_chunk("SHORT MODEL NOTE")
        return "SHORT MODEL NOTE"

    monkeypatch.setattr(per_finding, "_ollama_stream", fake_stream)
    cfg = replace(load_config(), cache_dir=str(tmp_path))

    first = explain_finding(finding, backend="ollama", config=cfg)
    assert first.text == "SHORT MODEL NOTE"
    assert first.cache_hit is False
    assert calls["n"] == 1

    chunks: list[str] = []
    second = explain_finding(finding, backend="ollama", config=cfg, on_chunk=chunks.append)
    assert second.cache_hit is True
    assert second.text == "SHORT MODEL NOTE"
    assert chunks == ["SHORT MODEL NOTE"]  # cached text still flows through on_chunk
    assert calls["n"] == 1


def test_model_failure_falls_back_to_evidence_text_and_is_not_cached(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    finding = _scan_finding()

    def boom(config, user, on_chunk):  # noqa: ANN001
        raise RuntimeError("ollama is down")

    monkeypatch.setattr(per_finding, "_ollama_stream", boom)
    cfg = replace(load_config(), cache_dir=str(tmp_path))
    result = explain_finding(finding, backend="ollama", config=cfg)
    assert result.fallback_used is True
    assert result.error == "ollama is down"
    assert result.text == deterministic_finding_text(finding)
    assert not list((tmp_path / "explanations").glob("*.json"))


def test_why_explain_rule_backend_is_fully_offline() -> None:
    result = runner.invoke(
        app,
        ["why", str(FIXTURE), "--missed-only", "--explain", "--backend", "rule"],
    )
    assert result.exit_code == 0
    assert "model:" in result.stdout
    assert "deterministic evidence text (no model call)" in result.output


def test_why_explain_respects_no_network_guardrail(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXPLNCC_NO_NETWORK", "1")
    result = runner.invoke(app, ["why", str(FIXTURE), "--explain"])
    assert result.exit_code == 2
    assert "forbids network/model backend" in result.output


def test_why_explain_caps_at_five_and_skips_notes(monkeypatch: pytest.MonkeyPatch) -> None:
    explained: list[str] = []

    def fake_explain(finding, *, backend, config, on_chunk=None):  # noqa: ANN001
        explained.append(finding.headline)
        text = "NOTE TEXT"
        if on_chunk:
            on_chunk(text)
        return per_finding.FindingExplanation(
            text=text,
            backend=backend,
            model="m",
            latency_ms=1,
        )

    monkeypatch.setattr(per_finding, "explain_finding", fake_explain)
    result = runner.invoke(app, ["why", str(FIXTURE), "--explain", "--top", "0"])
    assert result.exit_code == 0
    # Only MISS-tagged findings get model notes; spills and OK lines do not.
    assert len(explained) == 3
    assert all("vectorized (width" not in h for h in explained)
    assert all("register spill" not in h for h in explained)
