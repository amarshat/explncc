"""Feature extraction for the local ranker.

Features are deliberately simple, binary-or-small-integer, and explainable. Each
extracted feature set comes with human-readable reasons so the ranker can show
*why* a finding scored the way it did. No network, no model dependency.

Diff features (appeared/disappeared/changed/cost-increased/vf-decreased) are
optional and only populated when the caller supplies baseline context.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from explncc.evidence import EvidencePack
from explncc.models import OptimizationRecord

# Ordered feature names so vectors are stable across runs and exports.
FEATURE_NAMES: tuple[str, ...] = (
    # Basic
    "kind_is_missed",
    "kind_is_passed",
    "kind_is_analysis",
    "has_source_location",
    "has_function",
    "has_debug_location",
    "has_cost",
    "has_vectorization_factor",
    "has_interleave_count",
    "has_target",
    "has_source_snippet",
    "has_ir_snippet",
    "has_assembly_snippet",
    # Pass family
    "pass_loop_vectorize",
    "pass_slp_vectorize",
    "pass_inline",
    "pass_unroll",
    "pass_licm",
    "pass_instcombine",
    "pass_gvn",
    # Message signals
    "msg_alias",
    "msg_memory_independence",
    "msg_cost",
    "msg_threshold",
    "msg_no_definition",
    "msg_call",
    "msg_trip_count",
    "msg_reduction",
    "msg_alignment",
    "msg_vectorized",
    "msg_runtime_check",
    # Location/context
    "function_name_present",
    "file_present",
    "line_present",
    # Optional diff features
    "appeared_in_current_build",
    "disappeared_from_baseline",
    "changed_from_passed_to_missed",
    "changed_from_missed_to_passed",
    "cost_increased",
    "vectorization_factor_decreased",
)


@dataclass
class FeatureExtraction:
    """Extracted features plus human-readable reasons for one record."""

    features: dict[str, int]
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"features": dict(self.features), "reasons": list(self.reasons)}


@dataclass
class DiffContext:
    """Optional baseline signals for diff-aware features.

    The caller computes these by comparing the current record against a
    baseline build (see :mod:`explncc.diffing`). All fields default to ``None``
    meaning "not evaluated".
    """

    appeared_in_current_build: bool | None = None
    disappeared_from_baseline: bool | None = None
    changed_from_passed_to_missed: bool | None = None
    changed_from_missed_to_passed: bool | None = None
    cost_increased: bool | None = None
    vectorization_factor_decreased: bool | None = None


def _args_text(args_raw: Any) -> str:
    if args_raw is None:
        return ""
    if isinstance(args_raw, str):
        return args_raw.lower()
    if isinstance(args_raw, dict):
        return " ".join(_args_text(v) for v in args_raw.values())
    if isinstance(args_raw, (list, tuple)):
        return " ".join(_args_text(v) for v in args_raw)
    return str(args_raw).lower()


def _record_text(record: OptimizationRecord) -> str:
    parts = [
        record.message or "",
        record.remark_name or "",
        record.reason or "",
        _args_text(record.args_raw),
    ]
    return " ".join(p for p in parts if p).lower()


def _interleave_count(record: OptimizationRecord) -> int | None:
    """Best-effort interleave count from args (Clang emits InterleaveCount)."""

    args = record.args_raw
    if isinstance(args, (list, tuple)):
        for item in args:
            if isinstance(item, dict):
                for key, val in item.items():
                    if "interleave" in str(key).lower():
                        try:
                            return int(str(val))
                        except (TypeError, ValueError):
                            return None
    return None


def extract_features(
    record: OptimizationRecord,
    *,
    pack: EvidencePack | None = None,
    diff: DiffContext | None = None,
) -> FeatureExtraction:
    """Extract an explainable feature vector for one normalized remark."""

    text = _record_text(record)
    pass_l = (record.pass_name or "").lower()
    features: dict[str, int] = {name: 0 for name in FEATURE_NAMES}
    reasons: list[str] = []

    def on(name: str, reason: str) -> None:
        features[name] = 1
        reasons.append(reason)

    # Basic
    if record.kind == "missed":
        on("kind_is_missed", "remark kind is Missed")
    if record.kind == "passed":
        on("kind_is_passed", "remark kind is Passed")
    if record.kind == "analysis":
        on("kind_is_analysis", "remark kind is Analysis")
    if record.file or record.line is not None:
        on("has_source_location", "remark has a source location")
    if record.function:
        on("has_function", "remark has a function name")
    if record.file and record.line is not None:
        on("has_debug_location", "remark has a debug location (file + line)")
    has_cost = bool(record.cost or record.threshold) or (
        pack is not None and pack.has_cost
    )
    if has_cost:
        on("has_cost", "remark carries cost details")
    if record.vectorization_factor is not None:
        on("has_vectorization_factor", "remark carries a vectorization factor")
    interleave = _interleave_count(record)
    if interleave is not None:
        on("has_interleave_count", "remark carries an interleave count")
    has_target = bool(record.tool_version_metadata) or (
        pack is not None and pack.has_target
    )
    if has_target:
        on("has_target", "target metadata is available")
    if pack is not None and pack.source_snippet:
        on("has_source_snippet", "a source snippet is attached")
    if pack is not None and pack.ir_snippet:
        on("has_ir_snippet", "an IR snippet is attached")
    if pack is not None and pack.assembly_context:
        on("has_assembly_snippet", "an assembly snippet is attached")

    # Pass family
    if "loop-vectorize" in pass_l:
        on("pass_loop_vectorize", "pass is loop-vectorize")
    if "slp" in pass_l:
        on("pass_slp_vectorize", "pass is slp-vectorizer")
    if "inline" in pass_l:
        on("pass_inline", "pass is inline")
    if "unroll" in pass_l:
        on("pass_unroll", "pass is loop-unroll")
    if "licm" in pass_l:
        on("pass_licm", "pass is licm")
    if "instcombine" in pass_l:
        on("pass_instcombine", "pass is instcombine")
    if "gvn" in pass_l:
        on("pass_gvn", "pass is gvn")

    # Message signals
    if "alias" in text:
        on("msg_alias", "message mentions aliasing")
    if "memory independence" in text or "memory dependence" in text:
        on("msg_memory_independence", "message mentions memory independence")
    if "cost" in text or "not beneficial" in text or "not profitable" in text:
        on("msg_cost", "message mentions cost / profitability")
    if "threshold" in text:
        on("msg_threshold", "message mentions a threshold")
    if "no definition" in text or "definition is unavailable" in text or "nodefinition" in text:
        on("msg_no_definition", "message mentions an unavailable definition")
    if "call" in text:
        on("msg_call", "message mentions a call")
    if "trip count" in text or "tripcount" in text:
        on("msg_trip_count", "message mentions a trip count")
    if "reduction" in text:
        on("msg_reduction", "message mentions a reduction")
    if "align" in text:
        on("msg_alignment", "message mentions alignment")
    if "vectoriz" in text:
        on("msg_vectorized", "message mentions vectorization")
    if "runtime check" in text or "runtime memory check" in text:
        on("msg_runtime_check", "message mentions a runtime check")

    # Location/context
    if record.function:
        on("function_name_present", "function name present")
    if record.file:
        on("file_present", "file present")
    if record.line is not None:
        on("line_present", "line present")

    # Optional diff features
    if diff is not None:
        _apply_diff_features(diff, features, reasons)

    return FeatureExtraction(features=features, reasons=reasons)


def _apply_diff_features(
    diff: DiffContext,
    features: dict[str, int],
    reasons: list[str],
) -> None:
    mapping = (
        (
            "appeared_in_current_build",
            diff.appeared_in_current_build,
            "appeared in the current build",
        ),
        (
            "disappeared_from_baseline",
            diff.disappeared_from_baseline,
            "disappeared from the baseline",
        ),
        (
            "changed_from_passed_to_missed",
            diff.changed_from_passed_to_missed,
            "changed from Passed to Missed",
        ),
        (
            "changed_from_missed_to_passed",
            diff.changed_from_missed_to_passed,
            "changed from Missed to Passed",
        ),
        ("cost_increased", diff.cost_increased, "cost increased vs baseline"),
        (
            "vectorization_factor_decreased",
            diff.vectorization_factor_decreased,
            "vectorization factor decreased vs baseline",
        ),
    )
    for name, value, reason in mapping:
        if value:
            features[name] = 1
            reasons.append(reason)
