"""Shared local-mode types: confidence/severity scales and classification result.

These are deterministic value types used by the local classifier, ranker, and
template explanations. They never depend on network access or model backends.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

Confidence = Literal["low", "medium", "high"]
Severity = Literal["low", "medium", "high", "critical"]

_CONFIDENCE_ORDER: tuple[Confidence, ...] = ("low", "medium", "high")


def confidence_rank(confidence: Confidence) -> int:
    """Return an ordinal rank for a confidence level (low=0, medium=1, high=2)."""

    try:
        return _CONFIDENCE_ORDER.index(confidence)
    except ValueError:
        return 0


def confidence_at_least(value: Confidence, minimum: Confidence) -> bool:
    """True when ``value`` is at least as strong as ``minimum``."""

    return confidence_rank(value) >= confidence_rank(minimum)


@dataclass
class ClassificationResult:
    """Deterministic, rule-based classification of one normalized remark.

    ``score_hint`` is a small relevance prior in [0, 1] that the ranker may use
    as one input among many; it is not a final ranking score.
    """

    label: str
    confidence: Confidence
    score_hint: float = 0.0
    evidence_reasons: list[str] = field(default_factory=list)
    missing_context: list[str] = field(default_factory=list)
    recommended_actions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
