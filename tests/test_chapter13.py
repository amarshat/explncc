"""Chapter 13: record identity, trace, digest, doctor, backends, HTML."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from explncc.cli import app
from explncc.config import build_doctor_report
from explncc.digest import build_digest
from explncc.evidence import build_evidence_pack, build_evidence_packs
from explncc.explain.backends import run_explanation_result
from explncc.config import ExplnccConfig
from explncc.html_report import build_html_report_document
from explncc.models import OptimizationRecord
from explncc.normalizer import load_records_from_path
from explncc.prompt_registry import hash_prompt_text, render_explain_prompt
from explncc.record_identity import (
    apply_record_identity,
    build_record_hash,
    build_record_id,
    build_semantic_key,
    build_source_key,
)
from explncc.report_types import ExplanationInfo, ReportBuildOptions, ReportMetadata, ReportSourceInfo
from explncc.toolchains import get_adapter
from explncc.trace import build_trace, render_trace

runner = CliRunner()
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "inline_miss_no_definition.opt.yaml"
SIMD = Path(__file__).resolve().parent / "fixtures" / "simd_vectorized.opt.yaml"


def test_record_identity_fields_from_fixture() -> None:
    recs = load_records_from_path(FIXTURE)
    assert len(recs) >= 1
    r = recs[0]
    assert r.record_id
    assert r.record_hash
    assert r.raw_hash
    assert r.source_key
    assert r.semantic_key
    assert len(r.record_hash) == 64


def test_record_hash_stable() -> None:
    r = OptimizationRecord(
        kind="missed",
        pass_name="inline",
        remark_name="X",
        function="main",
        file="a.cpp",
        line=3,
        message="too  costly",
    )
    a = apply_record_identity(r)
    b = apply_record_identity(r)
    assert a.record_hash == b.record_hash
    assert build_record_id(a) == build_record_id(b)


def test_semantic_key_normalizes_message_whitespace() -> None:
    r1 = apply_record_identity(
        OptimizationRecord(kind="missed", pass_name="p", remark_name="r", message="a  b"),
    )
    r2 = apply_record_identity(
        OptimizationRecord(kind="missed", pass_name="p", remark_name="r", message="a b"),
    )
    assert r1.semantic_key == r2.semantic_key


def test_evidence_pack_hash_stable() -> None:
    recs = load_records_from_path(SIMD)
    p1 = build_evidence_pack(recs[0], ordinal=0)
    p2 = build_evidence_pack(recs[0], ordinal=0)
    assert p1.evidence_hash == p2.evidence_hash
    assert p1.prompt_ready


def test_evidence_pack_json_roundtrip() -> None:
    recs = load_records_from_path(SIMD)
    pack = build_evidence_packs(recs)[0]
    data = json.loads(pack.model_dump_json())
    assert data["pack_type"] == "single"
    assert data["primary_record"]


def test_trace_text_output() -> None:
    data = build_trace(FIXTURE, include_evidence=True)
    text = render_trace("text", data)
    assert "Parser:" in text
    assert "Normalizer:" in text
    assert "Deterministic stages:" in text


def test_trace_cli_json() -> None:
    result = runner.invoke(app, ["trace", str(FIXTURE), "--format", "json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["parser"]["raw_documents"] >= 1


def test_doctor_masks_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret")
    report = build_doctor_report()
    assert report["openai_api_key"] == "set"
    assert "sk-secret" not in json.dumps(report)
    assert report["explncc_version"]


def test_doctor_cli_markdown() -> None:
    result = runner.invoke(app, ["doctor", "--format", "markdown"])
    assert result.exit_code == 0
    assert "explncc doctor" in result.stdout


def test_digest_include_evidence() -> None:
    data = build_digest(FIXTURE, include_evidence=True)
    assert data["evidence_aggregate_hash"]
    assert data["recommended_cache_key"]
    assert "not binaries" in data["note"]


def test_digest_include_prompts() -> None:
    data = build_digest(FIXTURE, include_prompts=True, template="guided")
    assert data["prompt_hashes"]


def test_prompt_hash_stable() -> None:
    text, tid, ver = render_explain_prompt(rule_summary="r", records_json="[]")
    assert tid == "explain-default"
    assert ver == "1.0"
    assert hash_prompt_text(text) == hash_prompt_text(text)


def test_backend_result_rule() -> None:
    recs = load_records_from_path(FIXTURE)
    cfg = ExplnccConfig(
        default_backend="rule",
        ollama_host="http://x",
        ollama_model="m",
        openai_api_key=None,
        openai_model="gpt-4o-mini",
        anthropic_api_key=None,
        anthropic_model="claude",
    )
    result = run_explanation_result(recs[:1], backend="rule", config=cfg)
    assert result.success
    assert result.prompt_hash
    assert not result.fallback_used


def test_backend_auto_fallback_no_network() -> None:
    recs = load_records_from_path(FIXTURE)
    cfg = ExplnccConfig(
        default_backend="auto",
        ollama_host="http://127.0.0.1:11434",
        ollama_model="m",
        openai_api_key=None,
        openai_model="gpt-4o-mini",
        anthropic_api_key=None,
        anthropic_model="claude",
    )
    with patch("explncc.explain.backends.ollama_available", return_value=False):
        result = run_explanation_result(recs[:1], backend="auto", config=cfg)
    assert result.text


def test_html_report_escapes_injection() -> None:
    recs = [
        OptimizationRecord(
            kind="missed",
            pass_name="inline",
            remark_name="X",
            message="<script>alert(1)</script>",
            file="a.cpp",
            line=1,
        ),
    ]
    html = build_html_report_document(
        recs,
        source=ReportSourceInfo("t.opt.yaml", 1, 1),
        metadata=ReportMetadata(),
        options=ReportBuildOptions(title="Report <test>"),
        policy=None,
        explanation=ExplanationInfo(enabled=False),
    )
    assert "&lt;script&gt;" in html
    assert "Report &lt;test&gt;" in html
    assert "Raw Artifact Notice" in html
    assert "Top Missed Optimizations" in html


def test_html_report_cli() -> None:
    result = runner.invoke(
        app,
        ["report", str(FIXTURE), "--format", "html", "--embed-json", "--top-missed", "3"],
    )
    assert result.exit_code == 0
    assert "<!DOCTYPE html>" in result.stdout
    assert "application/json" in result.stdout


def test_clang_toolchain_adapter() -> None:
    adapter = get_adapter("clang")
    assert adapter.name == "clang"
    recs = adapter.parse_records(FIXTURE)
    assert recs


def test_clang_toolchain_unsupported() -> None:
    with pytest.raises(ValueError, match="unsupported toolchain"):
        get_adapter("gcc")
