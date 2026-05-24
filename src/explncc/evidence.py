"""Evidence packs (Chapter 10/13): deterministic model-facing compiler evidence."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from typing import Any, Literal

from pydantic import BaseModel, Field

from explncc.context_snippets import ContextSnippetRequest, gather_context_snippets
from explncc.exporters import record_to_json_dict
from explncc.models import OptimizationRecord

PackType = Literal["single", "cluster", "diff", "alignment", "ci"]


class DebugLocation(BaseModel):
    """Debug location carried on the remark (may be partial)."""

    file: str | None = None
    line: int | None = None
    column: int | None = None


class RelatedRecordRef(BaseModel):
    """Lightweight pointer to another remark in the same optimization log."""

    kind: str | None = None
    pass_name: str | None = None
    remark_name: str | None = None
    normalized_message: str | None = None
    file: str | None = None
    line: int | None = None
    column: int | None = None


class EvidencePack(BaseModel):
    """Deterministic, minimal evidence derived from one :class:`OptimizationRecord`."""

    pack_id: str
    pack_type: PackType = "single"
    evidence_hash: str | None = None
    prompt_ready: bool = False
    primary_record: dict[str, Any] | None = Field(
        default=None,
        description="Normalized primary remark (JSON-serializable).",
    )
    source_context: str | None = None
    ir_context: str | None = None
    assembly_context: str | None = None
    target_context: dict[str, Any] | None = None
    build_metadata: dict[str, Any] | None = None
    optimization_log_path: str | None = Field(
        default=None,
        description="Path to the .opt.yaml document stream this pack was built from.",
    )
    source_file: str | None = Field(
        default=None,
        description="Source path from the remark's DebugLoc (not the .opt.yaml path).",
    )
    function: str | None = None
    debug_location: DebugLocation = Field(default_factory=DebugLocation)
    primary_pass: str | None = None
    primary_kind: str | None = None
    primary_remark: str | None = None
    normalized_message: str | None = None
    vectorization_factor: int | None = None
    unroll_factor: int | None = None
    related_records: list[RelatedRecordRef] = Field(default_factory=list)
    scalar_cost: str | None = None
    vector_cost: str | None = None
    threshold: str | None = None
    target_triple: str | None = None
    cpu: str | None = None
    march: str | None = None
    source_snippet: str | None = None
    ir_snippet: str | None = None
    has_source: bool = False
    has_ir: bool = False
    has_cost: bool = False
    has_target: bool = False
    missing_context: list[str] = Field(default_factory=list)


def _scalar_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def _target_fields(meta: dict[str, Any] | None) -> tuple[str | None, str | None, str | None]:
    if not meta:
        return None, None, None
    triple = meta.get("Target") or meta.get("Triple") or meta.get("target")
    cpu = meta.get("CPU") or meta.get("Cpu") or meta.get("mcpu") or meta.get("Mcpu")
    march = meta.get("march") or meta.get("March") or meta.get("MArch")
    return _scalar_str(triple), _scalar_str(cpu), _scalar_str(march)


def _cost_fields(record: OptimizationRecord) -> tuple[str | None, str | None]:
    """Map the single YAML ``Cost`` string onto scalar vs vector slots without inventing values."""

    if record.cost is None:
        return None, None
    pass_l = (record.pass_name or "").lower()
    if "vector" in pass_l:
        return None, record.cost
    return record.cost, None


def _is_vector_family(record: OptimizationRecord) -> bool:
    return "vector" in (record.pass_name or "").lower()


def _pack_id(record: OptimizationRecord, *, ordinal: int, pack_type: PackType = "single") -> str:
    payload = {
        "pack_type": pack_type,
        "ordinal": ordinal,
        "record_hash": record.record_hash,
        "opt_yaml": record.source_path,
        "kind": record.kind,
        "pass": record.pass_name,
        "name": record.remark_name,
        "function": record.function,
        "file": record.file,
        "line": record.line,
        "column": record.column,
        "message": record.message,
        "vectorization_factor": record.vectorization_factor,
        "unroll_factor": record.unroll_factor,
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _evidence_hash(pack: EvidencePack) -> str:
    payload = pack.model_dump(
        exclude={"pack_id", "evidence_hash", "prompt_ready"},
        exclude_none=True,
    )
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _target_context_dict(
    triple: str | None,
    cpu: str | None,
    march: str | None,
) -> dict[str, Any] | None:
    if not any((triple, cpu, march)):
        return None
    return {"target_triple": triple, "cpu": cpu, "march": march}


def _is_prompt_ready(pack: EvidencePack) -> bool:
    return bool(pack.primary_kind and pack.primary_pass and pack.normalized_message is not None)


def finalize_evidence_pack(pack: EvidencePack) -> EvidencePack:
    """Set evidence_hash and prompt_ready after all fields are populated."""

    pack.evidence_hash = _evidence_hash(pack)
    pack.prompt_ready = _is_prompt_ready(pack)
    return pack


def _select_related(
    record: OptimizationRecord,
    candidates: Sequence[OptimizationRecord],
    *,
    max_related: int,
) -> list[RelatedRecordRef]:
    if max_related <= 0:
        return []
    fp_self = record.fingerprint()
    out: list[RelatedRecordRef] = []
    for other in candidates:
        if other.fingerprint() == fp_self:
            continue
        if record.source_path and other.source_path != record.source_path:
            continue
        if record.function and other.function != record.function:
            continue
        if not record.function and not other.function:
            continue
        out.append(
            RelatedRecordRef(
                kind=other.kind,
                pass_name=other.pass_name,
                remark_name=other.remark_name,
                normalized_message=other.message,
                file=other.file,
                line=other.line,
                column=other.column,
            ),
        )
        if len(out) >= max_related:
            break
    return out


def _compute_missing_context(record: OptimizationRecord, pack: EvidencePack) -> list[str]:
    """List evidence slots that are absent (no invented defaults).

    Cost keys appear in ``missing_context`` only for vectorization-related passes,
    where cost and threshold are part of the usual decision vocabulary.
    """

    missing: list[str] = []
    if pack.source_snippet is None:
        missing.append("source_snippet")
    if pack.ir_snippet is None:
        missing.append("ir_snippet")
    if pack.assembly_context is None:
        missing.append("assembly_snippet")
    if pack.target_triple is None:
        missing.append("target_triple")
    if _is_vector_family(record):
        if pack.vector_cost is None:
            missing.append("vector_cost")
        if pack.threshold is None:
            missing.append("threshold")
    return missing


def build_evidence_pack(
    record: OptimizationRecord,
    *,
    related_candidates: Sequence[OptimizationRecord] | None = None,
    ordinal: int = 0,
    max_related: int = 20,
    source_snippet: str | None = None,
    ir_snippet: str | None = None,
    assembly_snippet: str | None = None,
    pack_type: PackType = "single",
    build_metadata: dict[str, Any] | None = None,
) -> EvidencePack:
    """Build one evidence pack from a normalized remark.

    Does not read the filesystem for source or IR unless snippets are supplied by the
    caller or via :func:`build_evidence_packs` with a :class:`ContextSnippetRequest`.
    Unknown fields stay null; :attr:`EvidencePack.missing_context` lists gaps explicitly.
    """

    scalar_cost, vector_cost = _cost_fields(record)
    triple, cpu, march = _target_fields(record.tool_version_metadata)
    related: list[RelatedRecordRef] = []
    if related_candidates is not None:
        related = _select_related(record, related_candidates, max_related=max_related)

    pack = EvidencePack(
        pack_id=_pack_id(record, ordinal=ordinal, pack_type=pack_type),
        pack_type=pack_type,
        primary_record=record_to_json_dict(record),
        source_context=source_snippet,
        ir_context=ir_snippet,
        assembly_context=assembly_snippet,
        target_context=_target_context_dict(triple, cpu, march),
        build_metadata=build_metadata,
        optimization_log_path=record.source_path,
        source_file=record.file,
        function=record.function,
        debug_location=DebugLocation(file=record.file, line=record.line, column=record.column),
        primary_pass=record.pass_name,
        primary_kind=record.kind,
        primary_remark=record.remark_name,
        normalized_message=record.message,
        vectorization_factor=record.vectorization_factor,
        unroll_factor=record.unroll_factor,
        related_records=related,
        scalar_cost=scalar_cost,
        vector_cost=vector_cost,
        threshold=record.threshold,
        target_triple=triple,
        cpu=cpu,
        march=march,
        source_snippet=source_snippet,
        ir_snippet=ir_snippet,
        has_source=source_snippet is not None,
        has_ir=ir_snippet is not None,
        has_cost=bool(scalar_cost or vector_cost or record.threshold),
        has_target=bool(triple or cpu or march),
        missing_context=[],
    )
    pack.missing_context = _compute_missing_context(record, pack)
    return finalize_evidence_pack(pack)


def build_evidence_packs(
    records: Sequence[OptimizationRecord],
    *,
    max_related: int = 20,
    context: ContextSnippetRequest | None = None,
) -> list[EvidencePack]:
    """Build one pack per record, with related-remark selection scoped to the full batch."""

    rec_list = list(records)
    packs: list[EvidencePack] = []
    for i, rec in enumerate(rec_list):
        snippets = gather_context_snippets(rec, context)
        pack = build_evidence_pack(
            rec,
            related_candidates=rec_list,
            ordinal=i,
            max_related=max_related,
            source_snippet=snippets.source_snippet,
            ir_snippet=snippets.ir_snippet,
            assembly_snippet=snippets.assembly_snippet,
        )
        packs.append(pack)
    return packs


def build_ci_evidence_pack(
    record: OptimizationRecord,
    *,
    build_metadata: dict[str, Any] | None = None,
) -> EvidencePack:
    """Single-record CI-oriented evidence pack."""

    return build_evidence_pack(
        record,
        pack_type="ci",
        build_metadata=build_metadata,
        max_related=0,
    )
