"""Stable identity and hashing for normalized optimization records."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from explncc.models import OptimizationRecord

_MISSING = "—"


def _field(value: str | int | None) -> str:
    if value is None:
        return ""
    return str(value)


def normalize_message(message: str | None) -> str:
    if not message:
        return ""
    return re.sub(r"\s+", " ", message).strip()


def build_record_id(record: OptimizationRecord) -> str:
    """Human-readable stable ID from pass, kind, remark, function, location."""

    parts = (
        _field(record.pass_name) or _MISSING,
        _field(record.kind) or _MISSING,
        _field(record.remark_name) or _MISSING,
        _field(record.function) or _MISSING,
        _field(record.file) or _MISSING,
        _field(record.line) or _MISSING,
        _field(record.column) or _MISSING,
    )
    return "/".join(parts)


def build_source_key(record: OptimizationRecord) -> str:
    return (
        f"{_field(record.file)}:{_field(record.line)}:"
        f"{_field(record.column)}:{_field(record.function)}"
    )


def build_semantic_key(record: OptimizationRecord) -> str:
    return (
        f"{_field(record.pass_name)}:{_field(record.kind)}:"
        f"{_field(record.remark_name)}:{_field(record.function)}:"
        f"{normalize_message(record.message)}"
    )


def canonical_record_payload(record: OptimizationRecord) -> dict[str, Any]:
    """Fields included in record_hash (deterministic, no timestamps)."""

    return {
        "kind": record.kind,
        "pass_name": record.pass_name,
        "remark_name": record.remark_name,
        "function": record.function,
        "file": record.file,
        "line": record.line,
        "column": record.column,
        "caller": record.caller,
        "callee": record.callee,
        "reason": record.reason,
        "message": normalize_message(record.message),
        "vectorization_factor": record.vectorization_factor,
        "unroll_factor": record.unroll_factor,
        "cost": record.cost,
        "threshold": record.threshold,
        "hotness": record.hotness,
    }


def hash_payload(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_record_hash(record: OptimizationRecord) -> str:
    return hash_payload(canonical_record_payload(record))


def build_raw_hash(raw_doc: dict[str, Any] | None) -> str | None:
    if raw_doc is None:
        return None
    return hash_payload(raw_doc)


def apply_record_identity(
    record: OptimizationRecord,
    *,
    raw_doc: dict[str, Any] | None = None,
) -> OptimizationRecord:
    """Populate identity fields on a normalized record."""

    return record.model_copy(
        update={
            "record_id": build_record_id(record),
            "record_hash": build_record_hash(record),
            "raw_hash": build_raw_hash(raw_doc),
            "source_key": build_source_key(record),
            "semantic_key": build_semantic_key(record),
        },
    )
