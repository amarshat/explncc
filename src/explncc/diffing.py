"""Compare two optimization record collections."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from explncc.models import OptimizationRecord


def _missed_map(records: list[OptimizationRecord]) -> dict[tuple[Any, ...], OptimizationRecord]:
    m: dict[tuple[Any, ...], OptimizationRecord] = {}
    for r in records:
        if r.kind == "missed":
            fp = r.fingerprint()
            m.setdefault(fp, r)
    return m


def _pass_counts(records: list[OptimizationRecord]) -> Counter[str]:
    c: Counter[str] = Counter()
    for r in records:
        if r.pass_name:
            c[r.pass_name] += 1
    return c


def _reason_counts_missed(records: list[OptimizationRecord]) -> Counter[str]:
    c: Counter[str] = Counter()
    for r in records:
        if r.kind != "missed":
            continue
        key = r.reason or r.remark_name or ""
        if key:
            c[key] += 1
    return c


def _function_counts_missed(records: list[OptimizationRecord]) -> Counter[str]:
    c: Counter[str] = Counter()
    for r in records:
        if r.kind != "missed":
            continue
        if r.function:
            c[r.function] += 1
    return c


@dataclass
class DiffReport:
    """Human- and machine-oriented diff summary."""

    new_missed: list[OptimizationRecord] = field(default_factory=list)
    resolved_missed: list[OptimizationRecord] = field(default_factory=list)
    pass_count_before: dict[str, int] = field(default_factory=dict)
    pass_count_after: dict[str, int] = field(default_factory=dict)
    pass_count_delta: dict[str, int] = field(default_factory=dict)
    reason_delta_missed: dict[str, int] = field(default_factory=dict)
    function_delta_missed: dict[str, int] = field(default_factory=dict)


def diff_records(before: list[OptimizationRecord], after: list[OptimizationRecord]) -> DiffReport:
    """Compute remark-level deltas (missed set semantics + aggregate counters)."""

    bm = _missed_map(before)
    am = _missed_map(after)
    new_fps = set(am) - set(bm)
    resolved_fps = set(bm) - set(am)
    new_missed = [am[fp] for fp in sorted(new_fps, key=str)]
    resolved_missed = [bm[fp] for fp in sorted(resolved_fps, key=str)]

    pb = _pass_counts(before)
    pa = _pass_counts(after)
    all_passes = sorted(set(pb) | set(pa))
    pass_delta = {p: pa[p] - pb[p] for p in all_passes if pa[p] - pb[p] != 0}

    rb = _reason_counts_missed(before)
    ra = _reason_counts_missed(after)
    all_reasons = sorted(set(rb) | set(ra))
    reason_delta = {k: ra[k] - rb[k] for k in all_reasons if ra[k] - rb[k] != 0}

    fb = _function_counts_missed(before)
    fa = _function_counts_missed(after)
    all_funcs = sorted(set(fb) | set(fa))
    function_delta = {k: fa[k] - fb[k] for k in all_funcs if fa[k] - fb[k] != 0}

    return DiffReport(
        new_missed=new_missed,
        resolved_missed=resolved_missed,
        pass_count_before=dict(pb.most_common()),
        pass_count_after=dict(pa.most_common()),
        pass_count_delta=pass_delta,
        reason_delta_missed=reason_delta,
        function_delta_missed=function_delta,
    )
