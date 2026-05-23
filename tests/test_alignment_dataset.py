"""Alignment dataset rows and conservative teacher text."""

from __future__ import annotations

import json
from pathlib import Path

from explncc.alignment import classify_alignment
from explncc.alignment_dataset import build_alignment_training_rows, build_evidence_object
from explncc.alignment_teacher import build_conservative_teacher
from explncc.context_snippets import ContextSnippetRequest
from explncc.models import OptimizationRecord
from explncc.normalizer import load_records_from_path

FIXTURE_SIMD = Path(__file__).resolve().parent / "fixtures" / "simd_vectorized.opt.yaml"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
CH11 = Path(__file__).resolve().parents[1] / "examples" / "chapter11_alignment"


def test_conservative_teacher_plausible_does_not_claim_misalignment() -> None:
    rec = OptimizationRecord(
        kind="passed",
        pass_name="loop-vectorize",
        remark_name="Vectorized",
        message="vectorized loop",
        vectorization_factor=4,
    )
    text = build_conservative_teacher(rec, classify_alignment(rec))
    assert "does not explicitly mention alignment" in text
    assert "does not prove a misalignment issue" in text
    assert "definitely alignment" not in text.lower()


def test_conservative_teacher_explicit_mentions_vocabulary() -> None:
    rec = OptimizationRecord(
        kind="passed",
        pass_name="loop-vectorize",
        remark_name="Vectorized",
        message="uses _mm256_load_ps",
        vectorization_factor=8,
    )
    text = build_conservative_teacher(rec, classify_alignment(rec))
    assert "explicit" in text.lower()
    assert "not proof of a runtime bug" in text


def test_conservative_teacher_unlikely_points_to_other_cause() -> None:
    rec = OptimizationRecord(
        kind="missed",
        pass_name="loop-vectorize",
        remark_name="MissedDetails",
        message="cannot prove memory independence",
    )
    text = build_conservative_teacher(rec, classify_alignment(rec))
    assert "should not be read as an alignment diagnosis" in text


def test_explncc_record_row_schema() -> None:
    recs = load_records_from_path(FIXTURE_SIMD)
    rows = build_alignment_training_rows(
        recs,
        template_id="guided",
        export_format="explncc-record",
        use_teacher=True,
        teacher_placeholder="x",
        include_args_raw=False,
    )
    row = rows[0]
    for key in (
        "sample_id",
        "evidence",
        "source_context",
        "ir_context",
        "assembly_context",
        "alignment_label",
        "alignment_confidence",
        "evidence_reasons",
        "missing_context",
        "teacher_response",
        "expected_behavior",
        "task",
        "constraints",
        "messages",
        "metadata",
    ):
        assert key in row
    assert row["alignment_label"] == "alignment_plausible_not_proven"
    assert row["messages"][2]["content"] == row["teacher_response"]
    assert row["metadata"]["teacher"] == "alignment_conservative_rule"


def test_openai_messages_includes_core_fields() -> None:
    recs = load_records_from_path(FIXTURE_SIMD)
    rows = build_alignment_training_rows(
        recs,
        template_id="minimal",
        export_format="openai-messages",
        use_teacher=True,
        teacher_placeholder="x",
        include_args_raw=False,
    )
    row = rows[0]
    assert "messages" in row
    assert row["evidence"]["alignment_label"] == "alignment_plausible_not_proven"
    assert row["task"]
    assert row["constraints"]


def test_chatml_format() -> None:
    recs = load_records_from_path(FIXTURE_SIMD)
    rows = build_alignment_training_rows(
        recs,
        template_id="minimal",
        export_format="chatml",
        use_teacher=True,
        teacher_placeholder="x",
        include_args_raw=False,
    )
    assert "<|im_start|>system" in rows[0]["text"]
    assert "<|im_start|>assistant" in rows[0]["text"]


def test_plain_prompt_completion_format() -> None:
    recs = load_records_from_path(FIXTURE_SIMD)
    rows = build_alignment_training_rows(
        recs,
        template_id="guided",
        export_format="plain-prompt-completion",
        use_teacher=True,
        teacher_placeholder="x",
        include_args_raw=False,
    )
    assert "prompt" in rows[0]
    assert "completion" in rows[0]
    assert "Evidence JSON:" in rows[0]["prompt"]


def test_dataset_with_source_context() -> None:
    recs = load_records_from_path(FIXTURE_SIMD)
    context = ContextSnippetRequest(include_source=True, source_root=FIXTURES)
    rows = build_alignment_training_rows(
        recs,
        template_id="guided",
        export_format="explncc-record",
        use_teacher=True,
        teacher_placeholder="x",
        include_args_raw=False,
        context=context,
    )
    assert rows[0]["source_context"]["present"] is True
    assert "source_snippet" not in rows[0]["missing_context"]


def test_chapter11_aliasing_fixture_teacher() -> None:
    fixture = CH11 / "aliasing_not_alignment" / "fixtures" / "main.opt.yaml"
    recs = load_records_from_path(fixture)
    row = build_alignment_training_rows(
        recs,
        template_id="guided",
        export_format="explncc-record",
        use_teacher=True,
        teacher_placeholder="x",
        include_args_raw=False,
    )[0]
    assert row["alignment_label"] == "alignment_unlikely_from_evidence"
    assert "alignment diagnosis" in row["teacher_response"].lower()


def test_evidence_object_json_serializable() -> None:
    recs = load_records_from_path(FIXTURE_SIMD)
    obj = build_evidence_object(recs[0], include_args_raw=False)
    json.dumps(obj)
