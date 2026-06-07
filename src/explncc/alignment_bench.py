"""Alignment-focused bench-prompt fixtures for offline model evaluation."""

from __future__ import annotations

from typing import Any

from explncc.alignment import classify_alignment
from explncc.alignment_teacher import build_expected_behavior
from explncc.dataset_llm import _sample_id, slim_compiler_json
from explncc.models import OptimizationRecord
from explncc.prompt_templates import (
    ALIGNMENT_BENCH_TEMPLATE_IDS,
    CH11_SYSTEM,
    render_ch11_user_prompt,
)

ALIGNMENT_BENCH_VARIANTS: frozenset[str] = frozenset(ALIGNMENT_BENCH_TEMPLATE_IDS)


def _overreach_traps(record: OptimizationRecord, variant: str) -> list[str]:
    """Heuristic traps a good model should avoid for this variant and remark."""

    classification = classify_alignment(record)
    traps: list[str] = ["treats heuristic slice as ground truth"]
    msg = (record.message or "").lower()
    reasons = " ".join(classification.evidence_reasons).lower()

    if variant == "adversarial":
        traps.extend(
            [
                "claims alignment bug from leading question",
                "confirms misalignment as root cause without evidence",
            ],
        )
    if variant == "missing-context":
        traps.append("answers without listing missing source/IR/assembly/target evidence")

    if classification.alignment_label == "alignment_plausible_not_proven":
        traps.append("claims misalignment from vectorization_factor alone")
    if classification.alignment_label == "alignment_unlikely_from_evidence":
        if any(w in msg or w in reasons for w in ("alias", "independence", "aliasing")):
            traps.append("ignores aliasing remark")
        if any(w in msg or w in reasons for w in ("cost", "threshold", "beneficial")):
            traps.append("ignores cost / profitability remark")
        if any(w in msg or w in reasons for w in ("dependent memory", "dependence", "carried")):
            traps.append("ignores loop-carried dependence remark")
    if record.tool_version_metadata is None:
        traps.append("claims AVX2 without target evidence")
    if classification.alignment_label in {
        "insufficient_evidence",
        "alignment_plausible_not_proven",
    }:
        traps.append("claims definite alignment root cause from weak evidence")

    # Stable order, deduplicated.
    seen: set[str] = set()
    out: list[str] = []
    for trap in traps:
        if trap not in seen:
            seen.add(trap)
            out.append(trap)
    return out


def build_alignment_bench_prompt_lines(
    records: list[OptimizationRecord],
    *,
    template_ids: list[str] | None,
    include_args_raw: bool,
) -> list[dict[str, Any]]:
    """Cross-product of records × alignment bench variants with evaluation metadata."""

    ids = list(template_ids if template_ids is not None else ALIGNMENT_BENCH_TEMPLATE_IDS)
    unknown = [t for t in ids if t not in ALIGNMENT_BENCH_VARIANTS]
    if unknown:
        msg = f"unknown alignment bench template(s): {', '.join(unknown)}"
        raise KeyError(msg)

    lines: list[dict[str, Any]] = []
    for record in records:
        sid = _sample_id(record)
        classification = classify_alignment(record)
        compiler_json = slim_compiler_json(record, include_args_raw=include_args_raw)
        expected = build_expected_behavior(classification)

        for tid in ids:
            user_content = render_ch11_user_prompt(tid, compiler_json)
            prompt = f"System:\n{CH11_SYSTEM}\n\nUser:\n{user_content}"
            lines.append(
                {
                    "sample_id": sid,
                    "variant": tid,
                    "prompt": prompt,
                    "system": CH11_SYSTEM,
                    "user": user_content,
                    "expected_alignment_label": classification.alignment_label,
                    "expected_good_behavior": expected,
                    "overreach_traps": _overreach_traps(record, tid),
                },
            )
    return lines
