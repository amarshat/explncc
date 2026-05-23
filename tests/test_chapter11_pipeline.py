"""End-to-end Chapter 11 pipeline smoke tests (Make-equivalent, no Clang)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CH11_BUILD = ROOT / "build" / "chapter11"
CH11_ROOT = ROOT / "examples" / "chapter11_alignment"
PYTHON = sys.executable


def _run_make(target: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["make", target, f"PYTHON={PYTHON}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture(scope="module", autouse=True)
def _clean_chapter11_build() -> None:
    _run_make("chapter11-clean")
    yield
    # leave artifacts for local inspection after module tests


def test_chapter11_examples_stages_fixtures() -> None:
    result = _run_make("chapter11-examples")
    assert result.returncode == 0, result.stderr
    assert (CH11_BUILD / "vectorized_no_alignment_claim" / "main.opt.yaml").is_file()
    assert (CH11_BUILD / "aliasing_not_alignment" / "main.opt.yaml").is_file()


def test_chapter11_full_pipeline() -> None:
    result = _run_make("chapter11")
    assert result.returncode == 0, result.stderr + result.stdout
    assert (CH11_BUILD / "alignment" / "remarks.json").is_file()
    assert (CH11_BUILD / "packs" / "packs.jsonl").is_file()
    assert (CH11_BUILD / "datasets" / "alignment-guided.jsonl").is_file()
    assert (CH11_BUILD / "prompts" / "bench-prompts.jsonl").is_file()
    assert (CH11_BUILD / "eval" / "sample-predictions.jsonl").is_file()
    assert (CH11_BUILD / "eval" / "report.md").is_file()


def test_alignment_remarks_json_schema() -> None:
    _run_make("chapter11-alignment")
    data = json.loads((CH11_BUILD / "alignment" / "remarks.json").read_text(encoding="utf-8"))
    assert len(data) >= 6
    assert data[0]["alignment_label"]
    assert "evidence_reasons" in data[0]


def test_dataset_row_has_teacher_and_label() -> None:
    _run_make("chapter11-dataset")
    line = (CH11_BUILD / "datasets" / "alignment-guided.jsonl").read_text(encoding="utf-8").strip()
    row = json.loads(line.splitlines()[0])
    assert row["alignment_label"]
    assert row["teacher_response"]
    assert row["expected_behavior"]


def test_bench_prompts_have_traps() -> None:
    _run_make("chapter11-bench-prompts")
    lines = (CH11_BUILD / "prompts" / "bench-prompts.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 6
    row = json.loads(lines[0])
    assert row["variant"]
    assert row["overreach_traps"]


def test_eval_report_markdown() -> None:
    _run_make("chapter11-eval-fixture")
    md = (CH11_BUILD / "eval" / "report.md").read_text(encoding="utf-8")
    assert "Alignment evaluation report" in md
    assert "aggregate score" in md


def test_alignment_pack_with_source_markdown() -> None:
    _run_make("chapter11-packs")
    md = (CH11_BUILD / "packs" / "aliasing-sample.md").read_text(encoding="utf-8")
    assert "Alignment evidence packs" in md
    assert "aliasing_not_alignment" in md or "alignment_unlikely_from_evidence" in md
