"""Summarize normalized optimization records."""

from __future__ import annotations

from explncc.models import OptimizationRecord


def apply_filters(
    records: list[OptimizationRecord],
    *,
    pass_contains: str | None = None,
    function_contains: str | None = None,
    kind: str | None = None,
) -> list[OptimizationRecord]:
    """Filter records by substring and remark kind."""

    out = records
    if pass_contains:
        needle = pass_contains.lower()
        out = [r for r in out if r.pass_name and needle in r.pass_name.lower()]
    if function_contains:
        needle = function_contains.lower()
        out = [r for r in out if r.function and needle in r.function.lower()]
    if kind:
        k = kind.lower()
        out = [r for r in out if r.kind and r.kind.lower() == k]
    return out


def truncate_message(message: str | None, max_len: int) -> str:
    if message is None:
        return ""
    if max_len <= 0 or len(message) <= max_len:
        return message
    return message[: max_len - 1] + "…"


def rows_for_table(
    records: list[OptimizationRecord],
    *,
    max_message: int = 120,
) -> list[list[str]]:
    rows: list[list[str]] = []
    for r in records:
        loc = ""
        if r.file:
            loc = r.file
            if r.line is not None:
                loc += f":{r.line}"
                if r.column is not None:
                    loc += f":{r.column}"
        rows.append(
            [
                r.kind or "",
                r.pass_name or "",
                r.remark_name or "",
                r.function or "",
                loc,
                truncate_message(r.message, max_message),
            ],
        )
    return rows
