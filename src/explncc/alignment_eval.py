"""Heuristic scoring for alignment model outputs (Chapter 11 evaluator)."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

_OVERREACH_PHRASES: tuple[tuple[str, str], ...] = (
    (r"\bdefinitely alignment\b", "definitely alignment"),
    (r"\balignment bug\b", "alignment bug"),
    (r"\broot cause is misalignment\b", "root cause is misalignment"),
    (r"\bconfirmed misalignment\b", "confirmed misalignment"),
)

_AVX_RE = re.compile(r"\b(avx2|avx-512|avx512)\b", re.IGNORECASE)
_MISALIGNED_RE = re.compile(r"\bmisalign", re.IGNORECASE)
_VECTOR_WIDTH_RE = re.compile(r"\b(vectorization width|vector width|vf)\s*[:=]?\s*(\d+)", re.IGNORECASE)
_NEXT_STEP_RE = re.compile(
    r"\b(inspect|check|verify|compare|measure|review|attach|generate)\b",
    re.IGNORECASE,
)
_MISSING_CONTEXT_TERMS: tuple[str, ...] = (
    "source",
    "ir",
    "llvm",
    "assembly",
    "asm",
    "target",
    "missing context",
    "insufficient evidence",
)

_WEAK_LABELS: frozenset[str] = frozenset(
    {
        "alignment_plausible_not_proven",
        "alignment_unlikely_from_evidence",
        "insufficient_evidence",
        "not_alignment_related",
    },
)


@dataclass
class OverreachHit:
    category: str
    phrase: str
    detail: str


@dataclass
class SampleScore:
    sample_id: str
    evidence_fidelity: int
    alignment_discipline: int
    missing_context_awareness: int
    next_step_quality: int
    overreach_penalty: int
    conciseness: int
    total: float
    overreach_hits: list[OverreachHit] = field(default_factory=list)
    failure_categories: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["overreach_hits"] = [asdict(h) for h in self.overreach_hits]
        return data


@dataclass
class EvalReport:
    samples: list[SampleScore]
    aggregate_score: float
    failure_categories: dict[str, int]
    overreach_examples: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "samples": [s.to_dict() for s in self.samples],
            "aggregate_score": self.aggregate_score,
            "failure_categories": self.failure_categories,
            "overreach_examples": self.overreach_examples,
        }


def load_predictions_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            msg = f"invalid JSON on line {line_no} of {path}"
            raise ValueError(msg) from exc
        if not isinstance(row, dict):
            msg = f"expected JSON object on line {line_no} of {path}"
            raise TypeError(msg)
        rows.append(row)
    return rows


def _has_target_evidence(row: dict[str, Any]) -> bool:
    evidence = row.get("evidence")
    if isinstance(evidence, dict):
        if evidence.get("target_triple"):
            return True
        compiler = evidence.get("compiler_remark")
        if isinstance(compiler, dict) and compiler.get("tool_version_metadata"):
            return True
    if row.get("target_triple"):
        return True
    return False


def _expected_vf(row: dict[str, Any]) -> int | None:
    evidence = row.get("evidence")
    if isinstance(evidence, dict):
        vf = evidence.get("vectorization_factor")
        if isinstance(vf, int):
            return vf
        compiler = evidence.get("compiler_remark")
        if isinstance(compiler, dict) and isinstance(compiler.get("vectorization_factor"), int):
            return compiler["vectorization_factor"]
    vf = row.get("vectorization_factor")
    return vf if isinstance(vf, int) else None


def detect_overreach(row: dict[str, Any], text: str) -> list[OverreachHit]:
    """Flag conservative overreach patterns in model output."""

    hits: list[OverreachHit] = []
    lower = text.lower()
    label = str(row.get("expected_alignment_label") or "")

    for pattern, phrase in _OVERREACH_PHRASES:
        if re.search(pattern, lower, re.IGNORECASE):
            hits.append(
                OverreachHit(
                    category="overreach_language",
                    phrase=phrase,
                    detail=f"output contains {phrase!r}",
                ),
            )

    if _AVX_RE.search(text) and not _has_target_evidence(row):
        hits.append(
            OverreachHit(
                category="invented_target",
                phrase="AVX2",
                detail="claims AVX2/AVX-512 without target evidence",
            ),
        )

    if _MISALIGNED_RE.search(text) and label in _WEAK_LABELS:
        hits.append(
            OverreachHit(
                category="misalignment_overclaim",
                phrase="misaligned",
                detail=f"claims misalignment when expected label is {label}",
            ),
        )

    if label in _WEAK_LABELS and re.search(
        r"\b(clearly|confirmed|definitely|certainly)\b.*\balign",
        lower,
    ):
        hits.append(
            OverreachHit(
                category="weak_evidence_overclaim",
                phrase="definite alignment claim",
                detail="definite alignment claim on weak expected label",
            ),
        )

    expected_vf = _expected_vf(row)
    for match in _VECTOR_WIDTH_RE.finditer(text):
        claimed = int(match.group(2))
        if expected_vf is not None and claimed != expected_vf:
            hits.append(
                OverreachHit(
                    category="invented_vector_width",
                    phrase=match.group(0),
                    detail=f"claims vector width {claimed} but evidence has {expected_vf}",
                ),
            )
        if expected_vf is None and claimed > 0 and label in _WEAK_LABELS:
            hits.append(
                OverreachHit(
                    category="invented_vector_width",
                    phrase=match.group(0),
                    detail="claims vector width without evidence",
                ),
            )

    if label == "alignment_unlikely_from_evidence":
        msg_bits = json.dumps(row.get("evidence") or row, default=str).lower()
        if any(w in msg_bits for w in ("alias", "independence", "cost", "threshold")):
            if not any(w in lower for w in ("alias", "independence", "cost", "profit")):
                hits.append(
                    OverreachHit(
                        category="ignored_compiler_reason",
                        phrase="aliasing/cost",
                        detail="ignores aliasing or cost remark in evidence",
                    ),
                )

    return hits


def _score_evidence_fidelity(row: dict[str, Any], text: str) -> int:
    evidence = row.get("evidence") if isinstance(row.get("evidence"), dict) else row
    markers = 0
    for key in ("pass_name", "primary_pass", "pass"):
        val = evidence.get(key) if isinstance(evidence, dict) else None
        if val and str(val).lower() in text.lower():
            markers += 1
            break
    for key in ("remark_name", "primary_remark", "kind"):
        val = evidence.get(key) if isinstance(evidence, dict) else None
        if val and str(val).lower() in text.lower():
            markers += 1
            break
    if re.search(r"\b(compiler|remark|pass|vectoriz)\b", text, re.IGNORECASE):
        markers += 1
    if markers >= 2:
        return 2
    if markers == 1:
        return 1
    return 0


def _score_alignment_discipline(row: dict[str, Any], text: str, hits: list[OverreachHit]) -> int:
    label = str(row.get("expected_alignment_label") or "")
    lower = text.lower()
    if hits:
        return 0
    if label == "alignment_explicit":
        if any(w in lower for w in ("align", "aligned", "unaligned", "intrinsic")):
            return 2
        return 1
    if label in _WEAK_LABELS:
        cautious = any(
            w in lower
            for w in (
                "does not prove",
                "not prove",
                "insufficient",
                "may",
                "might",
                "cannot conclude",
                "without evidence",
                "missing",
            )
        )
        return 2 if cautious else 1
    return 1


def _score_missing_context_awareness(row: dict[str, Any], text: str) -> int:
    missing = row.get("missing_context") or []
    if not isinstance(missing, list) or not missing:
        return 2
    lower = text.lower()
    mentioned = sum(1 for term in _MISSING_CONTEXT_TERMS if term in lower)
    if mentioned >= 2 or any(m.replace("_", " ") in lower for m in missing if isinstance(m, str)):
        return 2
    if mentioned == 1:
        return 1
    return 0


def _score_next_step_quality(text: str) -> int:
    matches = _NEXT_STEP_RE.findall(text)
    if len(matches) >= 2:
        return 2
    if len(matches) == 1:
        return 1
    return 0


def _score_conciseness(text: str) -> int:
    if not text.strip():
        return 0
    if len(text) <= 1200:
        return 1
    return 0


def _overreach_penalty(hits: list[OverreachHit]) -> int:
    if not hits:
        return 0
    return max(-3, -len(hits))


def score_prediction(row: dict[str, Any]) -> SampleScore:
    """Score one prediction row heuristically."""

    sample_id = str(row.get("sample_id") or "unknown")
    text = str(row.get("model_output") or "")
    hits = detect_overreach(row, text)
    failure_categories = sorted({h.category for h in hits})

    evidence_fidelity = _score_evidence_fidelity(row, text)
    alignment_discipline = _score_alignment_discipline(row, text, hits)
    missing_context_awareness = _score_missing_context_awareness(row, text)
    next_step_quality = _score_next_step_quality(text)
    overreach_penalty = _overreach_penalty(hits)
    conciseness = _score_conciseness(text)
    total = (
        evidence_fidelity
        + alignment_discipline
        + missing_context_awareness
        + next_step_quality
        + overreach_penalty
        + conciseness
    )

    return SampleScore(
        sample_id=sample_id,
        evidence_fidelity=evidence_fidelity,
        alignment_discipline=alignment_discipline,
        missing_context_awareness=missing_context_awareness,
        next_step_quality=next_step_quality,
        overreach_penalty=overreach_penalty,
        conciseness=conciseness,
        total=float(total),
        overreach_hits=hits,
        failure_categories=failure_categories,
    )


def evaluate_predictions(rows: list[dict[str, Any]]) -> EvalReport:
    """Score all predictions and build aggregate report."""

    samples = [score_prediction(row) for row in rows]
    aggregate = sum(s.total for s in samples) / len(samples) if samples else 0.0
    failures: dict[str, int] = {}
    overreach_examples: list[str] = []
    for sample in samples:
        for cat in sample.failure_categories:
            failures[cat] = failures.get(cat, 0) + 1
        for hit in sample.overreach_hits:
            example = f"{sample.sample_id}: {hit.detail}"
            if example not in overreach_examples:
                overreach_examples.append(example)
    return EvalReport(
        samples=samples,
        aggregate_score=aggregate,
        failure_categories=failures,
        overreach_examples=overreach_examples,
    )
