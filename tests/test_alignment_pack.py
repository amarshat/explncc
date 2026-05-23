"""Tests for Chapter 11 alignment evidence pack schema and builder."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from explncc.alignment import AlignmentLabel
from explncc.alignment_pack import (
    ALIGNMENT_LABELS,
    AlignmentEvidencePack,
    build_alignment_evidence_pack,
    build_alignment_evidence_packs,
)
from explncc.alignment_pack_output import render_alignment_evidence_packs
from explncc.context_snippets import ContextSnippetRequest
from explncc.models import OptimizationRecord
from explncc.normalizer import load_records_from_path

FIXTURE_SIMD = Path(__file__).resolve().parent / "fixtures" / "simd_vectorized.opt.yaml"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_alignment_labels_frozen_set() -> None:
    assert "alignment_plausible_not_proven" in ALIGNMENT_LABELS
    assert len(ALIGNMENT_LABELS) == 5


def test_build_pack_schema_fields() -> None:
    records = load_records_from_path(FIXTURE_SIMD)
    rec = records[0]
    pack = build_alignment_evidence_pack(rec, ordinal=0)
    assert pack.pass_name == "loop-vectorize"
    assert pack.kind == "passed"
    assert pack.remark_name == "Vectorized"
    assert pack.file == "t.cpp"
    assert pack.line == 2
    assert pack.vectorization_factor == 4
    assert pack.interleave_count is None
    assert pack.alignment_label == "alignment_plausible_not_proven"
    assert pack.alignment_confidence == "medium"
    assert pack.source_snippet is None
    assert pack.ir_snippet is None
    assert pack.assembly_snippet is None
    assert pack.raw_record_ref == str(FIXTURE_SIMD.resolve())
    assert len(pack.raw_record_hash) == 64
    assert pack.source_record_id
    assert pack.pack_id != pack.source_record_id
    assert "source_snippet" in pack.missing_context
    assert "ir_snippet" in pack.missing_context
    assert "assembly_snippet" in pack.missing_context
    assert "target_triple" in pack.missing_context


def test_pack_id_stable_across_runs() -> None:
    records = load_records_from_path(FIXTURE_SIMD)
    a = build_alignment_evidence_pack(records[0], ordinal=0)
    b = build_alignment_evidence_pack(records[0], ordinal=0)
    assert a.pack_id == b.pack_id
    assert a.raw_record_hash == b.raw_record_hash


def test_label_filter() -> None:
    records = load_records_from_path(FIXTURE_SIMD)
    all_packs = build_alignment_evidence_packs(records)
    filtered = build_alignment_evidence_packs(
        records,
        label=cast(AlignmentLabel, "alignment_plausible_not_proven"),
    )
    assert len(all_packs) == 1
    assert len(filtered) == 1
    empty = build_alignment_evidence_packs(
        records,
        label=cast(AlignmentLabel, "alignment_explicit"),
    )
    assert len(empty) == 0


def test_interleave_count_from_args() -> None:
    rec = OptimizationRecord(
        kind="passed",
        pass_name="loop-vectorize",
        remark_name="Vectorized",
        message="vectorized",
        args_raw=[{"InterleaveCount": "2"}],
    )
    pack = build_alignment_evidence_pack(rec, ordinal=0)
    assert pack.interleave_count == 2


def test_schema_roundtrip() -> None:
    records = load_records_from_path(FIXTURE_SIMD)
    pack = build_alignment_evidence_pack(records[0], ordinal=0)
    again = AlignmentEvidencePack.model_validate(pack.model_dump())
    assert again.pack_id == pack.pack_id


def test_render_formats() -> None:
    records = load_records_from_path(FIXTURE_SIMD)
    packs = build_alignment_evidence_packs(records)
    js = render_alignment_evidence_packs(packs, "json")
    assert '"alignment_label"' in js
    assert '"pack_id"' in js
    jsl = render_alignment_evidence_packs(packs, "jsonl")
    assert jsl.strip().startswith("{")
    md = render_alignment_evidence_packs(packs, "markdown")
    assert "# Alignment evidence packs" in md
    assert "alignment_plausible_not_proven" in md


def test_render_unknown_format_raises() -> None:
    with pytest.raises(ValueError, match="unknown alignment pack format"):
        render_alignment_evidence_packs([], "xml")


def test_pack_with_context_attachment() -> None:
    records = load_records_from_path(FIXTURE_SIMD)
    context = ContextSnippetRequest(
        include_source=True,
        source_root=FIXTURES,
        include_ir=True,
        ir_file=FIXTURES / "t.ll",
        include_asm=True,
        asm_file=FIXTURES / "t.s",
    )
    packs = build_alignment_evidence_packs(records, context=context)
    pack = packs[0]
    assert pack.source_snippet is not None
    assert pack.ir_snippet is not None
    assert pack.assembly_snippet is not None
    assert "source_snippet" not in pack.missing_context
    assert "ir_snippet" not in pack.missing_context
    assert "assembly_snippet" not in pack.missing_context
    assert any("vmovups" in r for r in pack.evidence_reasons)
    md = render_alignment_evidence_packs(packs, "markdown")
    assert "assembly_signals" in md
    assert " | " in md  # numbered source lines
