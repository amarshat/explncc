"""CI-oriented rules over optimization records."""

from __future__ import annotations

from dataclasses import dataclass, field

from explncc.models import OptimizationRecord


@dataclass
class CheckResult:
    ok: bool
    violations: list[str] = field(default_factory=list)


def _count_missed_pass_contains(records: list[OptimizationRecord], needle: str) -> int:
    n = needle.lower()
    return sum(
        1 for r in records if r.kind == "missed" and r.pass_name and n in r.pass_name.lower()
    )


def run_checks(
    records: list[OptimizationRecord],
    *,
    max_missed_loop_vectorize: int | None = None,
    max_missed_inline: int | None = None,
    max_pass_remarks: int | None = None,
    pass_name_exact: str | None = None,
) -> CheckResult:
    """Evaluate simple numeric thresholds. Exit status is decided by the CLI."""

    violations: list[str] = []

    if max_missed_loop_vectorize is not None:
        c = _count_missed_pass_contains(records, "loop-vectorize")
        if c > max_missed_loop_vectorize:
            violations.append(
                f"missed loop-vectorize remarks {c} exceed limit {max_missed_loop_vectorize}",
            )

    if max_missed_inline is not None:
        c = _count_missed_pass_contains(records, "inline")
        if c > max_missed_inline:
            violations.append(f"missed inline remarks {c} exceed limit {max_missed_inline}")

    if max_pass_remarks is not None and pass_name_exact:
        c = sum(1 for r in records if r.pass_name == pass_name_exact)
        if c > max_pass_remarks:
            violations.append(
                f"remarks for pass {pass_name_exact!r} ({c}) exceed limit {max_pass_remarks}",
            )

    return CheckResult(ok=len(violations) == 0, violations=violations)
