"""Conservative rule-based teacher text for alignment dataset rows (not an oracle)."""

from __future__ import annotations

from explncc.alignment import AlignmentClassification, AlignmentLabel, classify_alignment
from explncc.models import OptimizationRecord


def build_expected_behavior(classification: AlignmentClassification) -> str:
    """Describe what a good model output should do for this evidence class."""

    label = classification.alignment_label
    if label == "alignment_explicit":
        return (
            "Cite explicit alignment vocabulary from the compiler remark; propose "
            "IR/assembly/source checks to confirm allocation and load/store forms; "
            "do not invent vector width or target features absent from evidence."
        )
    if label == "alignment_plausible_not_proven":
        return (
            "Acknowledge SIMD/vectorization involvement without claiming misalignment; "
            "state missing context; recommend allocation, pointer arithmetic, IR "
            "alignment metadata, or assembly inspection next."
        )
    if label == "alignment_unlikely_from_evidence":
        return (
            "Follow the compiler's stated non-alignment reason (e.g. aliasing or cost); "
            "do not attribute the remark to alignment without new evidence."
        )
    if label == "insufficient_evidence":
        return (
            "State that evidence is insufficient for an alignment diagnosis; list missing "
            "artifacts (source, IR, assembly, target) before recommending fixes."
        )
    return "Explain that the remark is not alignment-related under the heuristic slice."


def build_conservative_teacher(
    record: OptimizationRecord,
    classification: AlignmentClassification | None = None,
) -> str:
    """Build conservative teacher text grounded in classification (heuristic, not oracle)."""

    cls = classification or classify_alignment(record)
    label = cls.alignment_label
    pass_s = record.pass_name or "unknown pass"
    kind_s = record.kind or "unknown kind"
    remark_s = record.remark_name or "unknown remark"
    vf = record.vectorization_factor

    if label == "alignment_explicit":
        reasons = "; ".join(cls.evidence_reasons[:2]) if cls.evidence_reasons else (
            "explicit alignment vocabulary in the remark"
        )
        return (
            f"The compiler record ({pass_s}, {kind_s}, {remark_s}) includes explicit "
            f"alignment-related evidence: {reasons}. Treat this as grounded vocabulary "
            "from the remark, not proof of a runtime bug. Confirm with source allocation "
            "contracts, IR alignment metadata, and assembly load/store mnemonics before "
            "recommending code changes."
        )

    if label == "alignment_plausible_not_proven":
        vf_part = f" Vectorization factor {vf} is present." if vf is not None else ""
        return (
            f"The compiler record ({pass_s}, {kind_s}, {remark_s}) confirms SIMD/"
            f"vectorization involvement,{vf_part} but it does not explicitly mention "
            "alignment. Alignment may affect performance in principle, but this evidence "
            "alone does not prove a misalignment issue. Inspect allocation guarantees, "
            "pointer arithmetic, IR alignment metadata, or assembly load/store forms next."
        )

    if label == "alignment_unlikely_from_evidence":
        reason = cls.evidence_reasons[0] if cls.evidence_reasons else (
            "the remark points to a non-alignment cause"
        )
        return (
            f"The compiler record ({pass_s}, {kind_s}, {remark_s}) should not be read as "
            f"an alignment diagnosis: {reason}. Follow the stated compiler reason (e.g. "
            "aliasing contract, cost model) and do not attribute this miss to alignment "
            "without further evidence."
        )

    if label == "insufficient_evidence":
        return (
            f"The remark ({pass_s}, {kind_s}, {remark_s}) matches alignment-adjacent "
            "heuristics but lacks text to classify alignment relevance. Do not claim "
            "alignment or misalignment. Attach source, IR, assembly, and target context "
            "before drawing conclusions."
        )

    return (
        f"The remark ({pass_s}, {kind_s}, {remark_s}) is not alignment-related under "
        "explncc heuristics. Do not force an alignment narrative."
    )


def teacher_for_label(label: AlignmentLabel) -> str:
    """Build conservative teacher text for a label (test helper)."""

    templates: dict[AlignmentLabel, str] = {
        "alignment_explicit": "explicit alignment vocabulary",
        "alignment_plausible_not_proven": "does not explicitly mention alignment",
        "alignment_unlikely_from_evidence": "should not be read as an alignment diagnosis",
        "insufficient_evidence": "insufficient for an alignment diagnosis",
        "not_alignment_related": "not alignment-related",
    }
    record = OptimizationRecord(
        kind="passed" if label == "alignment_plausible_not_proven" else "missed",
        pass_name="loop-vectorize",
        remark_name="Vectorized" if label == "alignment_plausible_not_proven" else "MissedDetails",
        message=templates.get(label, ""),
        vectorization_factor=4 if label == "alignment_plausible_not_proven" else None,
    )
    return build_conservative_teacher(record, classify_alignment(record))
