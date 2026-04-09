"""Aggregate statistics over optimization records."""

from __future__ import annotations

from collections import Counter
from typing import Any

from explncc.models import OptimizationRecord


def aggregate(records: list[OptimizationRecord]) -> dict[str, Any]:
    """Return count maps keyed by pass, kind, function, and reason."""

    by_pass: Counter[str] = Counter()
    by_kind: Counter[str] = Counter()
    by_function: Counter[str] = Counter()
    by_reason: Counter[str] = Counter()
    for r in records:
        if r.pass_name:
            by_pass[r.pass_name] += 1
        if r.kind:
            by_kind[r.kind] += 1
        if r.function:
            by_function[r.function] += 1
        key = r.reason or r.remark_name or ""
        if key:
            by_reason[key] += 1
    return {
        "by_pass": dict(by_pass.most_common()),
        "by_kind": dict(by_kind.most_common()),
        "by_function": dict(by_function.most_common()),
        "by_reason": dict(by_reason.most_common()),
        "total": len(records),
    }
