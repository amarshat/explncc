"""CI-oriented deterministic policy gates over optimization records."""

from __future__ import annotations

from dataclasses import dataclass, field

from explncc.models import OptimizationRecord


@dataclass
class CheckResult:
    ok: bool
    violations: list[str] = field(default_factory=list)


@dataclass
class PolicyThresholdResult:
    name: str
    actual: int
    limit: int
    ok: bool
    contributors: list[str] = field(default_factory=list)


@dataclass
class PolicyResult:
    status: str
    thresholds: list[PolicyThresholdResult] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status == "pass"

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "thresholds": [
                {
                    "name": t.name,
                    "actual": t.actual,
                    "limit": t.limit,
                    "ok": t.ok,
                    "contributors": t.contributors,
                }
                for t in self.thresholds
            ],
            "failures": self.failures,
        }


def _count_missed_pass_contains(records: list[OptimizationRecord], needle: str) -> int:
    n = needle.lower()
    return sum(
        1 for r in records if r.kind == "missed" and r.pass_name and n in r.pass_name.lower()
    )


def _count_total_missed(records: list[OptimizationRecord]) -> int:
    return sum(1 for r in records if r.kind == "missed")


def _count_analysis(records: list[OptimizationRecord]) -> int:
    return sum(1 for r in records if r.kind == "analysis")


def _contributors_missed_pass(records: list[OptimizationRecord], needle: str, *, limit: int = 5) -> list[str]:
    n = needle.lower()
    out: list[str] = []
    for r in records:
        if r.kind != "missed" or not r.pass_name or n not in r.pass_name.lower():
            continue
        loc = r.file or "?"
        if r.line is not None:
            loc += f":{r.line}"
        out.append(f"{r.pass_name}/{r.remark_name or '?'} @ {loc}")
        if len(out) >= limit:
            break
    return out


def run_checks(
    records: list[OptimizationRecord],
    *,
    max_missed_loop_vectorize: int | None = None,
    max_missed_inline: int | None = None,
    max_missed_vectorize: int | None = None,
    max_missed_unroll: int | None = None,
    max_total_missed: int | None = None,
    max_analysis: int | None = None,
    max_pass_remarks: int | None = None,
    pass_name_exact: str | None = None,
) -> CheckResult:
    """Evaluate numeric thresholds. Exit status is decided by the CLI."""

    violations: list[str] = []

    if max_missed_loop_vectorize is not None:
        c = _count_missed_pass_contains(records, "loop-vectorize")
        if c > max_missed_loop_vectorize:
            violations.append(
                f"missed loop-vectorize remarks {c} exceed limit {max_missed_loop_vectorize}",
            )

    if max_missed_vectorize is not None:
        c = _count_missed_pass_contains(records, "vector")
        if c > max_missed_vectorize:
            violations.append(f"missed vectorize remarks {c} exceed limit {max_missed_vectorize}")

    if max_missed_unroll is not None:
        c = _count_missed_pass_contains(records, "unroll")
        if c > max_missed_unroll:
            violations.append(f"missed unroll remarks {c} exceed limit {max_missed_unroll}")

    if max_missed_inline is not None:
        c = _count_missed_pass_contains(records, "inline")
        if c > max_missed_inline:
            violations.append(f"missed inline remarks {c} exceed limit {max_missed_inline}")

    if max_total_missed is not None:
        c = _count_total_missed(records)
        if c > max_total_missed:
            violations.append(f"total missed remarks {c} exceed limit {max_total_missed}")

    if max_analysis is not None:
        c = _count_analysis(records)
        if c > max_analysis:
            violations.append(f"analysis remarks {c} exceed limit {max_analysis}")

    if max_pass_remarks is not None and pass_name_exact:
        c = sum(1 for r in records if r.pass_name == pass_name_exact)
        if c > max_pass_remarks:
            violations.append(
                f"remarks for pass {pass_name_exact!r} ({c}) exceed limit {max_pass_remarks}",
            )

    return CheckResult(ok=len(violations) == 0, violations=violations)


def build_policy_result(
    records: list[OptimizationRecord],
    *,
    max_missed_loop_vectorize: int | None = None,
    max_missed_inline: int | None = None,
    max_missed_vectorize: int | None = None,
    max_missed_unroll: int | None = None,
    max_total_missed: int | None = None,
    max_analysis: int | None = None,
    max_pass_remarks: int | None = None,
    pass_name_exact: str | None = None,
) -> PolicyResult | None:
    """Structured policy output for JSON/Markdown reports."""

    thresholds: list[PolicyThresholdResult] = []

    if max_missed_loop_vectorize is not None:
        actual = _count_missed_pass_contains(records, "loop-vectorize")
        ok = actual <= max_missed_loop_vectorize
        thresholds.append(
            PolicyThresholdResult(
                name="max_missed_loop_vectorize",
                actual=actual,
                limit=max_missed_loop_vectorize,
                ok=ok,
                contributors=_contributors_missed_pass(records, "loop-vectorize"),
            ),
        )

    if max_missed_vectorize is not None:
        actual = _count_missed_pass_contains(records, "vector")
        ok = actual <= max_missed_vectorize
        thresholds.append(
            PolicyThresholdResult(
                name="max_missed_vectorize",
                actual=actual,
                limit=max_missed_vectorize,
                ok=ok,
                contributors=_contributors_missed_pass(records, "vector"),
            ),
        )

    if max_missed_unroll is not None:
        actual = _count_missed_pass_contains(records, "unroll")
        ok = actual <= max_missed_unroll
        thresholds.append(
            PolicyThresholdResult(
                name="max_missed_unroll",
                actual=actual,
                limit=max_missed_unroll,
                ok=ok,
                contributors=_contributors_missed_pass(records, "unroll"),
            ),
        )

    if max_missed_inline is not None:
        actual = _count_missed_pass_contains(records, "inline")
        ok = actual <= max_missed_inline
        thresholds.append(
            PolicyThresholdResult(
                name="max_missed_inline",
                actual=actual,
                limit=max_missed_inline,
                ok=ok,
                contributors=_contributors_missed_pass(records, "inline"),
            ),
        )

    if max_total_missed is not None:
        actual = _count_total_missed(records)
        ok = actual <= max_total_missed
        thresholds.append(
            PolicyThresholdResult(
                name="max_total_missed",
                actual=actual,
                limit=max_total_missed,
                ok=ok,
                contributors=[],
            ),
        )

    if max_analysis is not None:
        actual = _count_analysis(records)
        ok = actual <= max_analysis
        thresholds.append(
            PolicyThresholdResult(
                name="max_analysis",
                actual=actual,
                limit=max_analysis,
                ok=ok,
                contributors=[],
            ),
        )

    if max_pass_remarks is not None and pass_name_exact:
        actual = sum(1 for r in records if r.pass_name == pass_name_exact)
        ok = actual <= max_pass_remarks
        thresholds.append(
            PolicyThresholdResult(
                name="max_pass_remarks",
                actual=actual,
                limit=max_pass_remarks,
                ok=ok,
                contributors=[],
            ),
        )

    if not thresholds:
        return None

    failures = [t.name for t in thresholds if not t.ok]
    status = "pass" if not failures else "fail"
    return PolicyResult(status=status, thresholds=thresholds, failures=failures)
