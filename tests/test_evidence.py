"""Tests for Chapter 10 evidence pack schema and builder."""

from __future__ import annotations

from pathlib import Path

from explncc.evidence import (
    EvidencePack,
    build_evidence_pack,
    build_evidence_packs,
)
from explncc.normalizer import load_records_from_path

FIXTURE_SIMD = Path(__file__).resolve().parent / "fixtures" / "simd_vectorized.opt.yaml"
FIXTURE_INLINE = Path(__file__).resolve().parent / "fixtures" / "inline_miss_no_definition.opt.yaml"


def test_evidence_pack_schema_roundtrip() -> None:
    records = load_records_from_path(FIXTURE_SIMD)
    assert len(records) == 1
    pack = build_evidence_pack(records[0], related_candidates=records, ordinal=0)
    raw = pack.model_dump()
    again = EvidencePack.model_validate(raw)
    assert again.pack_id == pack.pack_id


def test_build_vector_remark_missing_context_and_cost_mapping() -> None:
    records = load_records_from_path(FIXTURE_SIMD)
    rec = records[0]
    pack = build_evidence_pack(rec, related_candidates=records, ordinal=0)
    assert pack.primary_pass == "loop-vectorize"
    assert pack.primary_kind == "passed"
    assert pack.primary_remark == "Vectorized"
    assert pack.source_file == "t.cpp"
    assert pack.debug_location.line == 2
    assert pack.normalized_message is not None
    assert "vectorized" in pack.normalized_message
    assert pack.vectorization_factor == 4
    assert pack.scalar_cost is None
    assert pack.vector_cost is None
    assert pack.has_cost is False
    assert "source_snippet" in pack.missing_context
    assert "ir_snippet" in pack.missing_context
    assert "target_triple" in pack.missing_context
    assert "vector_cost" in pack.missing_context
    assert "threshold" in pack.missing_context


def test_pack_id_stable_across_runs() -> None:
    records = load_records_from_path(FIXTURE_SIMD)
    a = build_evidence_pack(records[0], related_candidates=records, ordinal=0)
    b = build_evidence_pack(records[0], related_candidates=records, ordinal=0)
    assert a.pack_id == b.pack_id


def test_pack_id_changes_with_ordinal() -> None:
    records = load_records_from_path(FIXTURE_SIMD)
    a = build_evidence_pack(records[0], related_candidates=records, ordinal=0)
    b = build_evidence_pack(records[0], related_candidates=records, ordinal=1)
    assert a.pack_id != b.pack_id


def test_related_records_same_yaml_and_function() -> None:
    records = load_records_from_path(FIXTURE_INLINE)
    assert len(records) >= 2
    packs = build_evidence_packs(records, max_related=10)
    missed = next(p for p in packs if p.primary_remark == "NoDefinition")
    assert len(missed.related_records) >= 1
    rel = missed.related_records[0]
    assert rel.pass_name == "prologepilog"
    assert rel.remark_name == "StackSize"


def test_inline_non_vector_missing_context_has_no_vector_cost_key() -> None:
    records = load_records_from_path(FIXTURE_INLINE)
    missed = next(r for r in records if r.remark_name == "NoDefinition")
    pack = build_evidence_pack(missed, related_candidates=records, ordinal=0)
    assert "vector_cost" not in pack.missing_context
    assert "threshold" not in pack.missing_context
    assert "source_snippet" in pack.missing_context


def test_scalar_cost_mapped_for_non_vector_pass(tmp_path: Path) -> None:
    yaml_path = tmp_path / "t.opt.yaml"
    yaml_path.write_text(
        """--- !Missed
Pass:            inline
Name:            TooCostly
DebugLoc:        { File: 'x.cpp', Line: 1, Column: 1 }
Function:        foo
Args:
  - String:          'cost'
  - Cost:            '12'
  - String:          ' threshold '
  - Threshold:       '10'
...
""",
        encoding="utf-8",
    )
    records = load_records_from_path(yaml_path)
    pack = build_evidence_pack(records[0], related_candidates=records, ordinal=0)
    assert pack.scalar_cost == "12"
    assert pack.vector_cost is None
    assert pack.threshold == "10"
    assert pack.has_cost is True


def test_target_from_tool_metadata(tmp_path: Path) -> None:
    yaml_path = tmp_path / "meta.opt.yaml"
    yaml_path.write_text(
        """---
Version:         1
Target:          x86_64-pc-linux-gnu
...
--- !Passed
Pass:            inline
Name:            Inlined
DebugLoc:        { File: 'x.cpp', Line: 1, Column: 1 }
Function:        foo
Args:
  - String:          'inlined'
...
""",
        encoding="utf-8",
    )
    records = load_records_from_path(yaml_path)
    assert len(records) == 1
    pack = build_evidence_pack(records[0], related_candidates=records, ordinal=0)
    assert pack.target_triple == "x86_64-pc-linux-gnu"
    assert pack.has_target is True
    assert "target_triple" not in pack.missing_context
