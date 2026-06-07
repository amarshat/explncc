"""Deterministic explanations derived from normalized records."""

from __future__ import annotations

from explncc.models import OptimizationRecord


def _loc(r: OptimizationRecord) -> str:
    parts: list[str] = []
    if r.file:
        parts.append(r.file)
    if r.line is not None:
        parts.append(str(r.line))
    return ":".join(parts) if parts else "unknown location"


def _paragraphs_for_record(r: OptimizationRecord) -> list[str]:
    lines: list[str] = []
    p = (r.pass_name or "").lower()
    name = r.remark_name or ""
    msg = (r.message or "").lower()

    if name == "NoDefinition" or "definition is unavailable" in msg:
        lines.append(
            f"At {_loc(r)} the inliner cannot merge callee {r.callee or '<unknown>'} into "
            f"{r.function or '<unknown>'} because the callee body is not available in this "
            "translation unit. Inlining requires the optimizer to see the callee IR; place "
            "definitions in headers (carefully), use LTO, or compile sources together.",
        )
    elif p == "inline" and "cost=" in msg and "threshold=" in msg:
        lines.append(
            f"At {_loc(r)} LLVM evaluated inline cost for {r.callee or 'a callee'} vs a "
            "threshold. When cost exceeds threshold, the inliner rejects the expansion to "
            "limit code growth. Reduce callee size, split cold paths into outlined helpers, "
            "or use `always_inline` only when you accept binary growth.",
        )
    elif p == "loop-vectorize" and r.kind == "missed":
        if "alias" in msg or "dependence" in msg or "unsafe" in msg:
            lines.append(
                f"Loop-vectorize missed at {_loc(r)} likely due to memory dependence or "
                "aliasing uncertainty. SIMD needs independent lanes; if pointers may "
                "overlap, the compiler must stay scalar. Try `__restrict` (where valid), "
                "separate buffers, structure-of-arrays layout, or `llvm.assume` patterns "
                "only after proving independence.",
            )
        else:
            lines.append(
                f"Loop-vectorize missed at {_loc(r)} ({name}). Inspect the full remark "
                "message for the specific guard (runtime checks, cost model, alignment). "
                "Compare against a variant with proven stride-one independent accesses.",
            )
    elif p == "loop-vectorize" and r.kind == "passed" and name == "Vectorized":
        vf = r.vectorization_factor
        vf_s = f" width {vf}" if vf else ""
        lines.append(
            f"Loop-vectorize succeeded at {_loc(r)}{vf_s}. The compiler emitted SIMD for "
            "this loop; validate with benchmarks and assembly if performance regresses.",
        )
    elif "loop-unroll" in p and name == "FullyUnrolled":
        u = r.unroll_factor
        u_s = f" ({u} iterations)" if u else ""
        lines.append(
            f"Loop unrolling at {_loc(r)} removed the loop entirely{u_s}. Fixed trip counts "
            "make this predictable; watch code size if the body grows.",
        )
    elif "loop-unroll" in p and r.kind == "missed":
        lines.append(
            f"Loop unroll did not fully apply at {_loc(r)}. Unknown trip counts, size "
            "limits, or profitability heuristics often block full unroll. Consider making "
            "bounds compile-time constant, splitting kernels, or measuring before pragmas.",
        )
    elif name == "LoadClobbered" or "clobbered" in msg:
        lines.append(
            f"GVN or load elimination stalled at {_loc(r)}: a load may be clobbered by "
            "another memory operation. This is related to aliasing and memory order; "
            "narrow lifetimes of pointers or separate memory regions to help the optimizer.",
        )
    elif name == "IINotAchieved" or (p.startswith("hls") and "achieve" in msg):
        ii = r.initiation_interval
        tgt = r.target_ii
        gap = ""
        if ii is not None and tgt is not None:
            gap = f" (achieved II={ii} vs target II={tgt})"
        lines.append(
            f"HLS could not pipeline {r.function or 'this loop'} at the target initiation "
            f"interval{gap}. An II above target almost always means a loop-carried dependency "
            "(an accumulator or a read-after-write through the same array/BRAM port) or a "
            "resource limit (too few memory ports or DSPs). Break the recurrence (partial sums, "
            "wider accumulators), partition or widen the array so more elements are readable per "
            "cycle, or relax the target II if the dependency is fundamental.",
        )
    elif name == "LoopNotPipelined" or (p.startswith("hls") and "not pipelined" in msg):
        lines.append(
            f"HLS left {r.function or 'this loop'} un-pipelined at {_loc(r)}, so iterations run "
            "back-to-back instead of overlapping. Common causes: a called subfunction is itself "
            "not pipelined, the loop bound is not analyzable, or there is variable-latency "
            "control flow inside the body. Add a pipeline directive to the hot loop, inline or "
            "pipeline the callee, and make trip counts statically bounded.",
        )
    elif name == "Pipelined" or (p.startswith("hls") and r.kind == "passed"):
        ii = r.initiation_interval
        ii_s = f" at II={ii}" if ii is not None else ""
        lines.append(
            f"HLS pipelined {r.function or 'this loop'}{ii_s}. A new iteration enters the "
            "pipeline every II cycles; II=1 is the throughput-optimal case. Confirm against the "
            "synthesis report and watch resource usage if you push II lower across more loops.",
        )

    if not lines and r.kind == "missed":
        lines.append(
            f"Missed optimization: pass={r.pass_name or '?'}, remark={name or '?'} at "
            f"{_loc(r)}. Message: {r.message or '<empty>'}",
        )
    return lines


def build_rule_explanation(records: list[OptimizationRecord]) -> str:
    """Aggregate deterministic paragraphs for a batch of records."""

    chunks: list[str] = []
    seen: set[tuple[str, str, str, str | None, int | None]] = set()
    for r in records:
        key = (r.pass_name or "", r.remark_name or "", r.function or "", r.file, r.line)
        if key in seen:
            continue
        seen.add(key)
        for para in _paragraphs_for_record(r):
            chunks.append(para)
    if not chunks:
        return "No specific rule-based templates matched these records; inspect raw messages."
    return "\n\n".join(chunks)
