"""LocalRankerV1: deterministic, explainable weighted scoring.

This is the first local ranker. It answers a single question: *which compiler
remarks are most likely worth a developer's attention?* It does this with a
transparent weighted sum over classification + extracted features, and it
records a human-readable reason for every weight it applies.

No ML dependency, no network. Scores express developer relevance, not absolute
truth; compiler evidence remains authoritative.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from explncc.evidence import EvidencePack
from explncc.exporters import record_to_json_dict
from explncc.local.classifier import ClassifyFocus, classify_record
from explncc.local.contracts import ClassificationResult, Confidence, Severity
from explncc.local.features import DiffContext, FeatureExtraction, extract_features
from explncc.local.taxonomy import get_label
from explncc.models import OptimizationRecord

# Severity thresholds on the raw weighted score.
_SEVERITY_CRITICAL = 85.0
_SEVERITY_HIGH = 70.0
_SEVERITY_MEDIUM = 45.0

_COST_LABELS = {"vectorize_cost_rejected", "inline_too_costly", "unroll_cost_rejected"}


@dataclass
class RankedFinding:
    """One ranked finding with a fully explainable score."""

    rank: int
    score: float
    normalized_score: float
    record_id: str | None
    label: str
    confidence: Confidence
    severity: Severity
    evidence_reasons: list[str] = field(default_factory=list)
    score_reasons: list[str] = field(default_factory=list)
    recommended_actions: list[str] = field(default_factory=list)
    record: OptimizationRecord | None = None

    def to_dict(self, *, include_record: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "rank": self.rank,
            "score": self.score,
            "normalized_score": self.normalized_score,
            "record_id": self.record_id,
            "label": self.label,
            "confidence": self.confidence,
            "severity": self.severity,
            "evidence_reasons": list(self.evidence_reasons),
            "score_reasons": list(self.score_reasons),
            "recommended_actions": list(self.recommended_actions),
        }
        if include_record and self.record is not None:
            payload["record"] = record_to_json_dict(self.record)
        return payload


def _severity_for_score(score: float) -> Severity:
    if score >= _SEVERITY_CRITICAL:
        return "critical"
    if score >= _SEVERITY_HIGH:
        return "high"
    if score >= _SEVERITY_MEDIUM:
        return "medium"
    return "low"


def _hotness_value(record: OptimizationRecord) -> float | None:
    if record.hotness is None:
        return None
    try:
        return float(str(record.hotness))
    except (TypeError, ValueError):
        return None


def _score_one(
    record: OptimizationRecord,
    classification: ClassificationResult,
    fx: FeatureExtraction,
    *,
    cluster_size: int,
    include_passed: bool,
) -> tuple[float, list[str]]:
    """Compute a raw weighted score and the reasons behind each weight."""

    f = fx.features
    score = 0.0
    reasons: list[str] = []

    def add(weight: float, reason: str) -> None:
        nonlocal score
        score += weight
        sign = "+" if weight >= 0 else ""
        reasons.append(f"{sign}{weight:g} because {reason}")

    if f["kind_is_missed"]:
        add(30, "remark is Missed")
    if f["pass_loop_vectorize"] and f["kind_is_missed"]:
        add(25, "pass is loop-vectorize and the remark is Missed")
    if f["pass_inline"] and f["kind_is_missed"]:
        add(20, "pass is inline and the remark is Missed")
    if classification.label in _COST_LABELS or (f["msg_cost"] and f["kind_is_missed"]):
        add(15, "the miss is a cost-model rejection")
    is_aliasing = (
        classification.label == "vectorize_aliasing"
        or bool(f["msg_memory_independence"])
        or bool(f["msg_alias"])
    )
    if is_aliasing:
        add(20, "message mentions memory independence / aliasing")

    if f["has_source_location"]:
        add(5, "a source location is available")
    else:
        add(-5, "no source location is available")
    if f["has_cost"]:
        add(8, "cost details are available")

    if f["appeared_in_current_build"]:
        add(20, "the remark appeared in the current build")
    if f["changed_from_passed_to_missed"]:
        add(40, "the remark changed from Passed to Missed")

    hot = _hotness_value(record)
    if hot is not None and hot > 0:
        contribution = min(30.0, round(math.log1p(hot) * 5.0, 2))
        if contribution > 0:
            add(contribution, f"profile hotness is available (hotness={record.hotness})")

    if cluster_size > 1:
        contribution = float(min(20, 5 * (cluster_size - 1)))
        add(contribution, f"repeated in the same function cluster (x{cluster_size})")

    if classification.label == "generic_analysis" or f["kind_is_analysis"]:
        add(-10, "remark is a generic analysis observation")
    if f["kind_is_passed"] and not include_passed:
        add(-20, "remark is Passed and successes are not the focus")

    return score, reasons


def _cluster_key(record: OptimizationRecord) -> tuple[str, str]:
    return ((record.function or ""), (record.pass_name or ""))


def _sort_key(finding_tuple: tuple[float, str, int]) -> tuple[float, str, int]:
    score, record_id, index = finding_tuple
    return (-score, record_id, index)


class LocalRankerV1:
    """Deterministic weighted ranker over records or evidence packs."""

    def __init__(self, *, include_passed: bool = False, focus: ClassifyFocus = None) -> None:
        self.include_passed = include_passed
        self.focus = focus

    def rank_records(
        self,
        records: Sequence[OptimizationRecord],
        *,
        packs: Sequence[EvidencePack] | None = None,
        diffs: Sequence[DiffContext | None] | None = None,
    ) -> list[RankedFinding]:
        rec_list = list(records)
        pack_list = list(packs) if packs is not None else [None] * len(rec_list)
        diff_list = list(diffs) if diffs is not None else [None] * len(rec_list)

        cluster_counts: Counter[tuple[str, str]] = Counter()
        for r in rec_list:
            if r.function:
                cluster_counts[_cluster_key(r)] += 1

        scored: list[tuple[float, str, int]] = []
        prepared: dict[int, RankedFinding] = {}
        for i, record in enumerate(rec_list):
            pack = pack_list[i] if i < len(pack_list) else None
            diff = diff_list[i] if i < len(diff_list) else None
            classification = classify_record(record, pack=pack, focus=self.focus)
            fx = extract_features(record, pack=pack, diff=diff)
            cluster_size = cluster_counts.get(_cluster_key(record), 1) if record.function else 1
            score, score_reasons = _score_one(
                record,
                classification,
                fx,
                cluster_size=cluster_size,
                include_passed=self.include_passed,
            )
            severity = _severity_for_score(score)
            label_def = get_label(classification.label)
            finding = RankedFinding(
                rank=0,
                score=round(score, 2),
                normalized_score=round(min(max(score, 0.0) / 100.0, 1.0), 4),
                record_id=record.record_id,
                label=classification.label,
                confidence=classification.confidence,
                severity=severity,
                evidence_reasons=list(classification.evidence_reasons),
                score_reasons=score_reasons,
                recommended_actions=list(classification.recommended_actions)
                or list(label_def.recommended_actions),
                record=record,
            )
            prepared[i] = finding
            scored.append((score, record.record_id or "", i))

        scored.sort(key=_sort_key)
        ordered: list[RankedFinding] = []
        for rank, (_score, _rid, index) in enumerate(scored, start=1):
            finding = prepared[index]
            finding.rank = rank
            ordered.append(finding)
        return ordered


def rank_records(
    records: Sequence[OptimizationRecord],
    *,
    include_passed: bool = False,
    focus: ClassifyFocus = None,
    packs: Sequence[EvidencePack] | None = None,
) -> list[RankedFinding]:
    """Convenience wrapper around :class:`LocalRankerV1`."""

    ranker = LocalRankerV1(include_passed=include_passed, focus=focus)
    return ranker.rank_records(records, packs=packs)
