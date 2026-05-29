"""Export normalized feature rows for future classifier/ranker training.

Each row pairs the explainable feature vector with the rule-derived label,
confidence, and a normalized relevance score, plus a compact text field and
metadata. This enables later training of sklearn / BERT / ONNX models without
shipping any training code or ML dependency now. Fully offline.
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from explncc.local.classifier import classify_record
from explncc.local.features import FEATURE_NAMES, extract_features
from explncc.local.ranker import LocalRankerV1
from explncc.models import OptimizationRecord

TRAINING_FORMATS = ("jsonl", "csv")
LABEL_SOURCES = ("rules",)


def _text_for(record: OptimizationRecord) -> str:
    parts = [
        record.pass_name or "",
        record.kind or "",
        record.remark_name or "",
        record.message or "",
    ]
    return " ".join(p for p in parts if p).strip()


def build_training_rows(
    records: list[OptimizationRecord],
    *,
    include_labels_from: str = "rules",
    focus: str | None = None,
    include_passed: bool = False,
) -> list[dict[str, Any]]:
    """Build one training row per record (deterministic, offline).

    ``include_labels_from`` currently supports ``"rules"`` (the rule-based
    classifier). The hook exists so future label sources can be added.
    """

    if include_labels_from not in LABEL_SOURCES:
        msg = f"unknown label source: {include_labels_from!r} (expected one of {LABEL_SOURCES})"
        raise ValueError(msg)

    ranker = LocalRankerV1(include_passed=include_passed, focus=focus)
    findings = ranker.rank_records(records)
    score_by_id: dict[int, float] = {id(f.record): f.normalized_score for f in findings}

    rows: list[dict[str, Any]] = []
    for record in records:
        classification = classify_record(record, focus=focus)
        fx = extract_features(record)
        rows.append(
            {
                "record_id": record.record_id,
                "features": fx.features,
                "rule_label": classification.label,
                "rule_confidence": classification.confidence,
                "score": score_by_id.get(id(record), 0.0),
                "text": _text_for(record),
                "metadata": {
                    "pass": record.pass_name,
                    "kind": record.kind,
                    "remark_name": record.remark_name,
                    "function": record.function,
                    "file": record.file,
                    "line": record.line,
                    "source_path": record.source_path,
                    "record_hash": record.record_hash,
                },
            }
        )
    return rows


def rows_to_jsonl(rows: list[dict[str, Any]]) -> str:
    return "\n".join(json.dumps(r, ensure_ascii=False) for r in rows)


def rows_to_csv(rows: list[dict[str, Any]]) -> str:
    """Flatten rows to CSV: feature columns expanded, metadata JSON-encoded."""

    fieldnames = (
        ["record_id", "rule_label", "rule_confidence", "score", "text"]
        + [f"feat_{name}" for name in FEATURE_NAMES]
        + ["metadata"]
    )
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        flat: dict[str, Any] = {
            "record_id": r.get("record_id") or "",
            "rule_label": r.get("rule_label") or "",
            "rule_confidence": r.get("rule_confidence") or "",
            "score": r.get("score", 0.0),
            "text": r.get("text") or "",
            "metadata": json.dumps(r.get("metadata") or {}, ensure_ascii=False),
        }
        features = r.get("features") or {}
        for name in FEATURE_NAMES:
            flat[f"feat_{name}"] = features.get(name, 0)
        writer.writerow(flat)
    return buf.getvalue()


def render_training_rows(rows: list[dict[str, Any]], fmt: str) -> str:
    fmt = fmt.strip().lower()
    if fmt == "jsonl":
        return rows_to_jsonl(rows)
    if fmt == "csv":
        return rows_to_csv(rows)
    raise ValueError(f"unknown training export format: {fmt!r}")
