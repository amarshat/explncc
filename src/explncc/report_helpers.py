"""Helpers for Chapter 12 report construction."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from explncc.checks import PolicyResult
from explncc.config import ExplnccConfig
from explncc.explain.backends import run_explanation
from explncc.models import OptimizationRecord
from explncc.report_types import ExplanationInfo, ReportSourceInfo


def report_source_info(
    target: Path,
    records: list[OptimizationRecord],
    *,
    toolchain: str = "clang",
) -> ReportSourceInfo:
    from explncc.toolchains import get_adapter

    paths = get_adapter(toolchain).discover_inputs(target)
    return ReportSourceInfo(
        input_path=str(target.resolve()),
        file_count=len(paths),
        remark_count=len(records),
    )


def _explain_label(backend: str | None) -> str | None:
    if not backend:
        return None
    if backend.lower() == "rule":
        return "Rule-based interpretation"
    return "AI-assisted interpretation"


def resolve_explanation(
    records: list[OptimizationRecord],
    *,
    enabled: bool,
    backend: str | None,
    config: ExplnccConfig,
    explain_limit: int,
    ai_limit: int,
    only_on_failure: bool,
    policy: PolicyResult | None,
    strict: bool,
) -> tuple[ExplanationInfo, int | None]:
    """Build explanation block from normalized records (never raw YAML). Returns (info, exit_code)."""

    if not enabled:
        return ExplanationInfo(enabled=False), None

    if only_on_failure and (policy is None or policy.ok):
        return ExplanationInfo(enabled=False), None

    mode = (backend or config.default_backend).strip().lower()
    if mode == "openai" and not config.openai_api_key:
        msg = "openai backend requires OPENAI_API_KEY"
        if strict:
            return ExplanationInfo(enabled=True, backend=mode, warning=msg), 2
        return ExplanationInfo(enabled=True, backend=mode, warning=msg), None
    if mode == "claude" and not config.anthropic_api_key:
        msg = "claude backend requires ANTHROPIC_API_KEY"
        if strict:
            return ExplanationInfo(enabled=True, backend=mode, warning=msg), 2
        return ExplanationInfo(enabled=True, backend=mode, warning=msg), None

    subset = records[:explain_limit] if explain_limit > 0 else records
    try:
        text = run_explanation(subset, backend=mode, config=config, ai_limit=ai_limit)
    except Exception as exc:  # noqa: BLE001 — CI must continue unless --strict-explain
        msg = f"explanation backend failed: {exc}"
        if strict:
            return ExplanationInfo(enabled=True, backend=mode, warning=msg), 1
        return ExplanationInfo(
            enabled=True,
            backend=mode,
            label=_explain_label(mode),
            warning=msg,
        ), None

    items: list[dict[str, Any]] = []
    if text and text.strip():
        items.append({"text": text.strip()})
    return ExplanationInfo(
        enabled=True,
        backend=mode,
        label=_explain_label(mode),
        items=items,
    ), None


def policy_thresholds_active(
    *,
    max_missed_loop_vectorize: int | None = None,
    max_missed_inline: int | None = None,
    max_missed_vectorize: int | None = None,
    max_missed_unroll: int | None = None,
    max_total_missed: int | None = None,
    max_analysis: int | None = None,
    max_pass_remarks: int | None = None,
    pass_name_exact: str | None = None,
) -> bool:
    if max_pass_remarks is not None and pass_name_exact:
        return True
    return any(
        v is not None
        for v in (
            max_missed_loop_vectorize,
            max_missed_inline,
            max_missed_vectorize,
            max_missed_unroll,
            max_total_missed,
            max_analysis,
        )
    )
