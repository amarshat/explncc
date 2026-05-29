"""Local label taxonomy for compiler optimization remarks.

Each label is a deterministic, documentary category for a normalized remark. The
taxonomy carries human-readable titles, default severities, recommended actions,
and template explanation text. Templates are filled deterministically; they never
invent compiler facts or target details.

Labels describe *what the compiler reported and why it likely matters to a
developer* — they are heuristics layered on top of authoritative compiler
evidence, not oracle truth.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from explncc.local.contracts import Severity


@dataclass(frozen=True)
class LocalLabel:
    """One entry in the local label taxonomy."""

    label_id: str
    title: str
    description: str
    severity_default: Severity
    recommended_actions: list[str] = field(default_factory=list)
    explanation_template: str = ""
    matching_hints: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "label_id": self.label_id,
            "title": self.title,
            "description": self.description,
            "severity_default": self.severity_default,
            "recommended_actions": list(self.recommended_actions),
            "explanation_template": self.explanation_template,
            "matching_hints": list(self.matching_hints),
        }


def _label(
    label_id: str,
    *,
    title: str,
    description: str,
    severity_default: Severity,
    recommended_actions: list[str],
    explanation_template: str,
    matching_hints: list[str],
) -> LocalLabel:
    return LocalLabel(
        label_id=label_id,
        title=title,
        description=description,
        severity_default=severity_default,
        recommended_actions=recommended_actions,
        explanation_template=explanation_template,
        matching_hints=matching_hints,
    )


_LABELS: tuple[LocalLabel, ...] = (
    _label(
        "vectorize_aliasing",
        title="Vectorization blocked by possible aliasing",
        description=(
            "The compiler reported a loop-vectorization miss tied to memory "
            "independence: it could not prove that memory accesses are safe to "
            "reorder or widen."
        ),
        severity_default="medium",
        recommended_actions=[
            "Inspect whether input/output buffers can overlap",
            "Consider restrict/noalias contracts if semantically valid",
            "Check call sites for overlapping ranges",
        ],
        explanation_template=(
            "The compiler attempted loop vectorization but could not prove memory "
            "independence. This usually means it could not prove that memory "
            "accesses in the loop are safe to reorder or widen without changing "
            "behavior if pointers happen to overlap."
        ),
        matching_hints=[
            "cannot prove memory independence",
            "may alias",
            "memory dependence",
            "aliasing",
        ],
    ),
    _label(
        "vectorize_cost_rejected",
        title="Vectorization rejected by the cost model",
        description=(
            "The compiler decided vectorizing this loop was not profitable based "
            "on its cost model, not because it was unsafe."
        ),
        severity_default="low",
        recommended_actions=[
            "Review scalar vs vector cost estimates in the remark",
            "Consider loop structure, trip count, and body size",
            "Avoid forcing vectorization unless benchmarks justify it",
        ],
        explanation_template=(
            "The compiler analyzed this loop and concluded that vectorizing it was "
            "not beneficial under its cost model. This is a profitability decision, "
            "not a correctness blocker: the loop could be vectorized but the "
            "compiler estimated no net win."
        ),
        matching_hints=[
            "cost",
            "not beneficial",
            "not profitable",
            "threshold",
        ],
    ),
    _label(
        "vectorize_call_in_loop",
        title="Vectorization blocked by a call in the loop",
        description=(
            "A function call inside the loop body prevented vectorization because "
            "the compiler could not vectorize across the call."
        ),
        severity_default="medium",
        recommended_actions=[
            "Check whether the called function can be inlined",
            "Consider hoisting or replacing the call with a vectorizable form",
            "Look for vectorized math library variants if the call is a libm function",
        ],
        explanation_template=(
            "The compiler could not vectorize this loop because it contains a "
            "function call it cannot vectorize across. Calls usually act as "
            "barriers unless the callee can be inlined or has a vector variant."
        ),
        matching_hints=[
            "call in loop",
            "function call",
            "cannot vectorize",
        ],
    ),
    _label(
        "vectorize_unknown_trip_count",
        title="Vectorization limited by unknown trip count",
        description=(
            "The compiler could not determine the loop trip count, which limited "
            "or blocked vectorization."
        ),
        severity_default="low",
        recommended_actions=[
            "Make loop bounds compile-time constant where possible",
            "Check whether runtime checks are being added or rejected",
            "Inspect whether the loop count is derived from opaque inputs",
        ],
        explanation_template=(
            "The compiler could not establish the loop's trip count. Without a "
            "known or bounded iteration count it is harder to prove vectorization "
            "is safe and profitable, so the loop stayed scalar or required runtime "
            "checks."
        ),
        matching_hints=[
            "trip count",
            "loop count",
            "backedge taken",
        ],
    ),
    _label(
        "vectorize_success",
        title="Loop vectorization succeeded",
        description="The compiler successfully vectorized this loop.",
        severity_default="low",
        recommended_actions=[
            "Validate with benchmarks if performance is a concern",
            "Inspect assembly to confirm the expected SIMD width",
        ],
        explanation_template=(
            "The compiler successfully vectorized this loop and emitted SIMD code. "
            "This is a positive outcome; confirm with benchmarks and assembly if "
            "performance regresses elsewhere."
        ),
        matching_hints=[
            "vectorized",
            "vectorization width",
        ],
    ),
    _label(
        "inline_no_definition",
        title="Inlining blocked: callee definition unavailable",
        description=(
            "The inliner could not inline a callee because its definition was not "
            "visible in this translation unit."
        ),
        severity_default="medium",
        recommended_actions=[
            "Place small hot definitions in headers, or compile sources together",
            "Enable link-time optimization (LTO) to expose cross-TU definitions",
            "Confirm the callee is not only declared but defined where it is used",
        ],
        explanation_template=(
            "The inliner could not merge the callee into the caller because the "
            "callee's body is not available in this translation unit. Inlining "
            "requires the optimizer to see the callee IR."
        ),
        matching_hints=[
            "NoDefinition",
            "definition is unavailable",
            "definition unavailable",
            "no definition",
        ],
    ),
    _label(
        "inline_too_costly",
        title="Inlining rejected as too costly",
        description=(
            "The inliner evaluated the callee against a cost threshold and rejected "
            "the expansion to limit code growth."
        ),
        severity_default="low",
        recommended_actions=[
            "Reduce callee size or split cold paths into outlined helpers",
            "Use always_inline only when you accept binary growth",
            "Review the reported cost vs threshold before forcing inlining",
        ],
        explanation_template=(
            "The inliner compared the callee's inline cost against a threshold and "
            "decided not to inline it. When cost exceeds the threshold the inliner "
            "declines to expand the call to avoid excessive code growth."
        ),
        matching_hints=[
            "too costly",
            "cost",
            "threshold",
        ],
    ),
    _label(
        "inline_success",
        title="Inlining succeeded",
        description="The inliner successfully inlined a callee into the caller.",
        severity_default="low",
        recommended_actions=[
            "No action required; verify code size if many callees are inlined",
        ],
        explanation_template=(
            "The inliner successfully inlined the callee into the caller. This can "
            "improve performance by removing call overhead and enabling further "
            "optimization across the inlined body."
        ),
        matching_hints=[
            "inlined",
            "Inlined",
        ],
    ),
    _label(
        "unroll_unknown_trip_count",
        title="Unrolling limited by unknown trip count",
        description=(
            "The compiler could not fully unroll the loop because the trip count "
            "was unknown or not a compile-time constant."
        ),
        severity_default="low",
        recommended_actions=[
            "Make loop bounds compile-time constant where possible",
            "Consider splitting kernels with fixed iteration counts",
            "Measure before adding unroll pragmas",
        ],
        explanation_template=(
            "The compiler did not fully unroll this loop because the trip count is "
            "unknown. Full unrolling typically requires a fixed, compile-time "
            "iteration count."
        ),
        matching_hints=[
            "trip count",
            "unknown trip",
            "runtime trip count",
        ],
    ),
    _label(
        "unroll_cost_rejected",
        title="Unrolling rejected by the cost model",
        description=(
            "The compiler decided unrolling this loop was not profitable or would "
            "grow code beyond a threshold."
        ),
        severity_default="low",
        recommended_actions=[
            "Review whether code-size growth is acceptable",
            "Consider partial unrolling or leaving the decision to the compiler",
            "Measure before forcing unroll counts",
        ],
        explanation_template=(
            "The compiler analyzed this loop and decided unrolling was not "
            "profitable under its cost model or would exceed a size threshold. This "
            "is a profitability decision, not a correctness blocker."
        ),
        matching_hints=[
            "cost",
            "not beneficial",
            "threshold",
            "code size",
        ],
    ),
    _label(
        "alignment_explicit",
        title="Alignment explicitly referenced by the remark",
        description=(
            "The remark text explicitly references alignment vocabulary (aligned/"
            "unaligned loads, alignment metadata, alignment intrinsics)."
        ),
        severity_default="medium",
        recommended_actions=[
            "Inspect allocation guarantees and pointer alignment assumptions",
            "Check IR alignment metadata on the relevant loads/stores",
            "Compare assembly load/store forms (e.g. movaps vs movups)",
        ],
        explanation_template=(
            "The remark explicitly mentions alignment. The compiler's wording points "
            "to alignment of memory accesses; confirm allocation and pointer "
            "alignment guarantees before changing code."
        ),
        matching_hints=[
            "aligned",
            "unaligned",
            "misaligned",
            "alignment",
        ],
    ),
    _label(
        "alignment_plausible_not_proven",
        title="Alignment plausibly involved but not proven",
        description=(
            "Vectorization/SIMD is involved but the remark does not explicitly "
            "establish that alignment is the cause. Reported only when the command "
            "focus is alignment."
        ),
        severity_default="low",
        recommended_actions=[
            "Inspect allocation guarantees and pointer arithmetic",
            "Check IR alignment metadata before attributing a miss to alignment",
            "Do not treat vectorization factor alone as proof of misalignment",
        ],
        explanation_template=(
            "SIMD or vectorization is involved here, but the remark does not prove "
            "that alignment is the issue. Treat alignment as a hypothesis to verify, "
            "not a conclusion."
        ),
        matching_hints=[
            "vectorized",
            "simd",
            "interleave",
        ],
    ),
    _label(
        "target_specific_drift",
        title="Target-specific optimization difference",
        description=(
            "The remark suggests behavior that may differ across targets/ISAs. "
            "Reported conservatively; details are not invented."
        ),
        severity_default="low",
        recommended_actions=[
            "Confirm the active target triple and CPU before drawing conclusions",
            "Compare the same source across the targets you ship",
            "Avoid assuming a specific ISA without target evidence",
        ],
        explanation_template=(
            "This remark may reflect target-specific behavior. Optimization "
            "decisions can differ across instruction sets; verify the active target "
            "before attributing the difference to a specific ISA."
        ),
        matching_hints=[
            "target",
            "triple",
            "cpu",
        ],
    ),
    _label(
        "wasm_simd_limitation",
        title="WebAssembly SIMD limitation",
        description=(
            "The remark indicates a WebAssembly SIMD limitation. Reported only with "
            "explicit wasm/SIMD target evidence."
        ),
        severity_default="low",
        recommended_actions=[
            "Confirm the wasm SIMD feature flags enabled at build time",
            "Check whether the operation has a wasm SIMD equivalent",
            "Compare against a native build to isolate the limitation",
        ],
        explanation_template=(
            "The remark points to a WebAssembly SIMD limitation. WebAssembly SIMD "
            "supports a narrower set of operations than native ISAs; some patterns "
            "cannot be expressed and stay scalar."
        ),
        matching_hints=[
            "wasm",
            "webassembly",
            "wasm-simd",
        ],
    ),
    _label(
        "arm_neon_difference",
        title="ARM NEON-specific difference",
        description=(
            "The remark indicates an ARM/NEON-specific behavior. Reported only with "
            "explicit ARM/NEON target evidence."
        ),
        severity_default="low",
        recommended_actions=[
            "Confirm the ARM target and NEON/SVE feature flags",
            "Compare against another ISA to isolate the difference",
            "Check for NEON-specific intrinsics or lowering",
        ],
        explanation_template=(
            "The remark points to ARM NEON-specific behavior. NEON has different "
            "vector widths and operation support than x86 SIMD; verify the target "
            "before generalizing."
        ),
        matching_hints=[
            "neon",
            "aarch64",
            "arm",
        ],
    ),
    _label(
        "x86_avx_difference",
        title="x86 AVX-specific difference",
        description=(
            "The remark indicates an x86 AVX/SSE-specific behavior. Reported only "
            "with explicit x86 target evidence."
        ),
        severity_default="low",
        recommended_actions=[
            "Confirm the x86 target and AVX/SSE feature flags",
            "Compare against another ISA to isolate the difference",
            "Check whether wider AVX registers change the cost model outcome",
        ],
        explanation_template=(
            "The remark points to x86 AVX/SSE-specific behavior. Available vector "
            "width depends on enabled features (SSE/AVX/AVX-512); verify the target "
            "before generalizing."
        ),
        matching_hints=[
            "avx",
            "sse",
            "x86",
        ],
    ),
    _label(
        "insufficient_evidence",
        title="Insufficient evidence to classify",
        description=(
            "The remark matched a relevant area but the available evidence is too "
            "weak to assign a specific cause. The conservative fallback."
        ),
        severity_default="low",
        recommended_actions=[
            "Attach a source snippet around the debug location",
            "Generate IR and assembly snippets for the function",
            "Re-run classification after adding grounded compiler artifacts",
        ],
        explanation_template=(
            "There is not enough grounded evidence in this remark to assign a "
            "specific cause. Add source, IR, or assembly context and re-run before "
            "drawing conclusions."
        ),
        matching_hints=[],
    ),
    _label(
        "generic_missed_optimization",
        title="Generic missed optimization",
        description=(
            "A missed optimization that does not match a more specific local label."
        ),
        severity_default="low",
        recommended_actions=[
            "Read the full remark message for the specific guard",
            "Compare against a variant where the optimization applies",
        ],
        explanation_template=(
            "The compiler reported a missed optimization that does not match a more "
            "specific local category. Inspect the full remark message to understand "
            "the guard the compiler hit."
        ),
        matching_hints=[],
    ),
    _label(
        "generic_analysis",
        title="Generic analysis remark",
        description=(
            "An analysis remark that reports compiler observations rather than a "
            "missed or applied optimization."
        ),
        severity_default="low",
        recommended_actions=[
            "Use as context; analysis remarks rarely require direct action",
        ],
        explanation_template=(
            "This is an analysis remark: the compiler is reporting an observation "
            "(such as a measurement) rather than a missed or applied optimization. "
            "It is usually contextual rather than directly actionable."
        ),
        matching_hints=[],
    ),
    _label(
        "generic_passed",
        title="Generic applied optimization",
        description=(
            "An applied optimization that does not match a more specific local label."
        ),
        severity_default="low",
        recommended_actions=[
            "No action required; informational",
        ],
        explanation_template=(
            "The compiler applied an optimization here. This is informational and "
            "does not match a more specific local category."
        ),
        matching_hints=[],
    ),
)


TAXONOMY: dict[str, LocalLabel] = {label.label_id: label for label in _LABELS}
"""Mapping of label_id -> :class:`LocalLabel` for every local label."""

LABEL_IDS: tuple[str, ...] = tuple(label.label_id for label in _LABELS)
"""Stable, declaration-ordered tuple of all known label ids."""


def get_label(label_id: str) -> LocalLabel:
    """Return the :class:`LocalLabel` for ``label_id``.

    Falls back to ``insufficient_evidence`` when the id is unknown so callers
    never crash on an unexpected label.
    """

    return TAXONOMY.get(label_id, TAXONOMY["insufficient_evidence"])


def is_known_label(label_id: str) -> bool:
    """True if ``label_id`` is a known local label."""

    return label_id in TAXONOMY
