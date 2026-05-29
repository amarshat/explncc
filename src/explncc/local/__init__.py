"""Offline-first local intelligence: taxonomy, classifier, features, and ranker.

This package implements deterministic, network-free analysis of normalized
optimization remarks. No hosted LLMs, no API keys, no Ollama, no external model
server are required. The local pipeline is:

    .opt.yaml -> parse -> normalize -> classify (rules) -> rank (weighted) ->
    template explanations -> reports

Compiler evidence remains authoritative; local labels and scores express
*developer relevance*, not absolute truth.
"""

from __future__ import annotations

from explncc.local.classifier import classify_record, classify_records
from explncc.local.contracts import (
    ClassificationResult,
    Confidence,
    Severity,
    confidence_at_least,
    confidence_rank,
)
from explncc.local.features import (
    FEATURE_NAMES,
    DiffContext,
    FeatureExtraction,
    extract_features,
)
from explncc.local.ml_ranker import LocalModelRanker, ModelRankerUnavailable
from explncc.local.ranker import LocalRankerV1, RankedFinding, rank_records
from explncc.local.taxonomy import (
    LABEL_IDS,
    TAXONOMY,
    LocalLabel,
    get_label,
    is_known_label,
)

__all__ = [
    "Confidence",
    "Severity",
    "ClassificationResult",
    "confidence_at_least",
    "confidence_rank",
    "LABEL_IDS",
    "TAXONOMY",
    "LocalLabel",
    "get_label",
    "is_known_label",
    "classify_record",
    "classify_records",
    "FEATURE_NAMES",
    "DiffContext",
    "FeatureExtraction",
    "extract_features",
    "LocalRankerV1",
    "RankedFinding",
    "rank_records",
    "LocalModelRanker",
    "ModelRankerUnavailable",
]
