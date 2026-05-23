"""Alignment bench-prompt fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from explncc.alignment_bench import build_alignment_bench_prompt_lines
from explncc.cli import app
from explncc.models import OptimizationRecord
from explncc.normalizer import load_records_from_path
from explncc.prompt_templates import ALIGNMENT_BENCH_TEMPLATE_IDS, render_ch11_user_prompt

FIXTURE_SIMD = Path(__file__).resolve().parent / "fixtures" / "simd_vectorized.opt.yaml"
CH11 = Path(__file__).resolve().parents[1] / "examples" / "chapter11_alignment"
RUNNER = CliRunner()


def test_all_alignment_bench_variants_exist() -> None:
    assert set(ALIGNMENT_BENCH_TEMPLATE_IDS) == {
        "minimal",
        "guided",
        "rubric",
        "adversarial",
        "missing-context",
    }


def test_bench_row_schema() -> None:
    recs = load_records_from_path(FIXTURE_SIMD)
    lines = build_alignment_bench_prompt_lines(
        recs,
        template_ids=["guided"],
        include_args_raw=False,
    )
    row = lines[0]
    for key in (
        "sample_id",
        "variant",
        "prompt",
        "expected_alignment_label",
        "expected_good_behavior",
        "overreach_traps",
    ):
        assert key in row
    assert row["expected_alignment_label"] == "alignment_plausible_not_proven"
    assert "System:" in row["prompt"]
    assert isinstance(row["overreach_traps"], list)


def test_adversarial_variant_tempts_overclaim() -> None:
    recs = load_records_from_path(FIXTURE_SIMD)
    lines = build_alignment_bench_prompt_lines(
        recs,
        template_ids=["adversarial"],
        include_args_raw=False,
    )
    user = lines[0]["user"]
    traps = lines[0]["overreach_traps"]
    assert "alignment bug" in user.lower() or "misalignment" in user.lower()
    assert "claims alignment bug from leading question" in traps


def test_missing_context_variant() -> None:
    recs = load_records_from_path(FIXTURE_SIMD)
    lines = build_alignment_bench_prompt_lines(
        recs,
        template_ids=["missing-context"],
        include_args_raw=False,
    )
    user = lines[0]["user"]
    assert "No source snippet" in user or "no source snippet" in user.lower()
    assert any("missing" in t for t in lines[0]["overreach_traps"])


def test_aliasing_fixture_overreach_traps() -> None:
    fixture = CH11 / "aliasing_not_alignment" / "fixtures" / "main.opt.yaml"
    recs = load_records_from_path(fixture)
    lines = build_alignment_bench_prompt_lines(
        recs,
        template_ids=["minimal"],
        include_args_raw=False,
    )
    assert lines[0]["expected_alignment_label"] == "alignment_unlikely_from_evidence"
    assert "ignores aliasing remark" in lines[0]["overreach_traps"]


def test_default_five_variants_cross_product() -> None:
    recs = load_records_from_path(FIXTURE_SIMD)
    lines = build_alignment_bench_prompt_lines(recs, template_ids=None, include_args_raw=False)
    assert len(lines) == 5
    assert {ln["variant"] for ln in lines} == set(ALIGNMENT_BENCH_TEMPLATE_IDS)


def test_unknown_variant_raises() -> None:
    recs = load_records_from_path(FIXTURE_SIMD)
    with pytest.raises(KeyError, match="unknown alignment bench template"):
        build_alignment_bench_prompt_lines(
            recs,
            template_ids=["nope"],
            include_args_raw=False,
        )


def test_cli_bench_prompts_alignment_focus() -> None:
    result = RUNNER.invoke(
        app,
        [
            "bench-prompts",
            str(FIXTURE_SIMD),
            "--focus",
            "alignment",
            "--templates",
            "minimal,adversarial,missing-context",
        ],
    )
    assert result.exit_code == 0
    lines = [json.loads(ln) for ln in result.stdout.splitlines() if ln.strip()]
    assert len(lines) == 3
    assert lines[1]["variant"] == "adversarial"
    assert "expected_alignment_label" in lines[0]
