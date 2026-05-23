"""Alignment evidence packs (Chapter 11) built from normalized remarks + classification."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, Field

from explncc.alignment import (
    AlignmentClassification,
    AlignmentConfidence,
    AlignmentLabel,
    classify_alignment,
)
from explncc.context_snippets import (
    AssemblySignal,
    ContextSnippetRequest,
    ContextSnippets,
    assembly_signal_reasons,
    gather_context_snippets,
)
from explncc.evidence import build_evidence_pack
from explncc.models import OptimizationRecord

ALIGNMENT_LABELS: frozenset[str] = frozenset(
    {
        "alignment_explicit",
        "alignment_plausible_not_proven",
        "alignment_unlikely_from_evidence",
        "insufficient_evidence",
        "not_alignment_related",
    },
)


class AlignmentEvidencePack(BaseModel):
    """Deterministic alignment evidence derived from one normalized remark."""

    pack_id: str
    source_record_id: str
    function: str | None = None
    file: str | None = None
    line: int | None = None
    column: int | None = None
    pass_name: str | None = None
    kind: str | None = None
    remark_name: str | None = None
    message: str | None = None
    vectorization_factor: int | None = None
    interleave_count: int | None = None
    scalar_cost: str | None = None
    vector_cost: str | None = None
    target_triple: str | None = None
    cpu: str | None = None
    march: str | None = None
    alignment_label: AlignmentLabel
    alignment_confidence: AlignmentConfidence
    evidence_reasons: list[str] = Field(default_factory=list)
    missing_context: list[str] = Field(default_factory=list)
    recommended_next_steps: list[str] = Field(default_factory=list)
    source_snippet: str | None = None
    ir_snippet: str | None = None
    assembly_snippet: str | None = None
    assembly_signals: list[AssemblySignal] = Field(default_factory=list)
    raw_record_ref: str | None = Field(
        default=None,
        description="Path to the .opt.yaml document stream this pack was built from.",
    )
    raw_record_hash: str = Field(
        description="Stable hash of the normalized remark fingerprint payload.",
    )


def _record_hash(record: OptimizationRecord) -> str:
    payload = {
        "kind": record.kind,
        "pass": record.pass_name,
        "name": record.remark_name,
        "function": record.function,
        "file": record.file,
        "line": record.line,
        "column": record.column,
        "message": record.message,
        "vectorization_factor": record.vectorization_factor,
        "source_path": record.source_path,
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _alignment_pack_id(record: OptimizationRecord, *, ordinal: int) -> str:
    payload = {
        "type": "alignment_evidence_pack",
        "ordinal": ordinal,
        "opt_yaml": record.source_path,
        "recorded": record.kind,
        "pass": record.pass_name,
        "name": record.remark_name,
        "function": record.function,
        "file": record.file,
        "line": record.line,
        "column": record.column,
        "message": record.message,
        "vectorization_factor": record.vectorization_factor,
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _interleave_count(record: OptimizationRecord) -> int | None:
    """Extract InterleaveCount from Args when present; do not invent."""

    args = record.args_raw
    if args is None:
        return None

    found: int | None = None

    def visit(node: Any) -> None:
        nonlocal found
        if found is not None:
            return
        if isinstance(node, dict):
            if "InterleaveCount" in node:
                val = node["InterleaveCount"]
                if isinstance(val, int):
                    found = val
                elif isinstance(val, str) and val.isdigit():
                    found = int(val)
            for val in node.values():
                if isinstance(val, (dict, list)):
                    visit(val)
        elif isinstance(node, list):
            for item in node:
                visit(item)

    visit(args)
    return found


def _merge_missing_context(
    classification: AlignmentClassification,
    *,
    source_snippet: str | None,
    ir_snippet: str | None,
    assembly_snippet: str | None,
    target_triple: str | None,
) -> list[str]:
    missing = list(classification.missing_context)
    if source_snippet is not None and "source_snippet" in missing:
        missing.remove("source_snippet")
    if ir_snippet is not None and "ir_snippet" in missing:
        missing.remove("ir_snippet")
    if assembly_snippet is not None and "assembly_snippet" in missing:
        missing.remove("assembly_snippet")
    if target_triple is not None and "target_triple" in missing:
        missing.remove("target_triple")
    return missing


def _merge_evidence_reasons(
    base: list[str],
    snippets: ContextSnippets,
) -> list[str]:
    merged = list(base)
    for reason in assembly_signal_reasons(snippets.assembly_signals):
        if reason not in merged:
            merged.append(reason)
    return merged


def build_alignment_evidence_pack(
    record: OptimizationRecord,
    *,
    ordinal: int = 0,
    classification: AlignmentClassification | None = None,
    snippets: ContextSnippets | None = None,
) -> AlignmentEvidencePack:
    """Build one alignment evidence pack from a normalized remark."""

    ctx = snippets or ContextSnippets()
    base = build_evidence_pack(record, related_candidates=None, ordinal=ordinal)
    cls = classification or classify_alignment(record)
    reasons = _merge_evidence_reasons(list(cls.evidence_reasons), ctx)

    return AlignmentEvidencePack(
        pack_id=_alignment_pack_id(record, ordinal=ordinal),
        source_record_id=base.pack_id,
        function=record.function,
        file=record.file,
        line=record.line,
        column=record.column,
        pass_name=record.pass_name,
        kind=record.kind,
        remark_name=record.remark_name,
        message=record.message,
        vectorization_factor=record.vectorization_factor,
        interleave_count=_interleave_count(record),
        scalar_cost=base.scalar_cost,
        vector_cost=base.vector_cost,
        target_triple=base.target_triple,
        cpu=base.cpu,
        march=base.march,
        alignment_label=cls.alignment_label,
        alignment_confidence=cls.alignment_confidence,
        evidence_reasons=reasons,
        missing_context=_merge_missing_context(
            cls,
            source_snippet=ctx.source_snippet,
            ir_snippet=ctx.ir_snippet,
            assembly_snippet=ctx.assembly_snippet,
            target_triple=base.target_triple,
        ),
        recommended_next_steps=list(cls.recommended_next_steps),
        source_snippet=ctx.source_snippet,
        ir_snippet=ctx.ir_snippet,
        assembly_snippet=ctx.assembly_snippet,
        assembly_signals=list(ctx.assembly_signals),
        raw_record_ref=record.source_path,
        raw_record_hash=_record_hash(record),
    )


def build_alignment_evidence_packs(
    records: Sequence[OptimizationRecord],
    *,
    label: AlignmentLabel | None = None,
    context: ContextSnippetRequest | None = None,
) -> list[AlignmentEvidencePack]:
    """Build alignment evidence packs for a batch of normalized remarks."""

    packs: list[AlignmentEvidencePack] = []
    for i, rec in enumerate(records):
        snippets = gather_context_snippets(rec, context)
        pack = build_alignment_evidence_pack(rec, ordinal=i, snippets=snippets)
        if label is not None and pack.alignment_label != label:
            continue
        packs.append(pack)
    return packs
