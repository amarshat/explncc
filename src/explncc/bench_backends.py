"""Measure explanation latency per backend on the user's own records.

Marketing numbers are worthless; numbers you can re-run on your own corpus are
not. ``explncc bench-backends`` takes the same fused findings the ``why``
command shows, runs each requested backend over them through the per-finding
short path, and reports wall-clock per finding. Generation is always measured
cold (no cache); an optional second pass per model row primes a throwaway
cache and times the replay, which is what a re-run after an unchanged build
costs.
"""

from __future__ import annotations

import dataclasses
import tempfile
import time
from dataclasses import dataclass

import httpx

from explncc.config import ExplnccConfig
from explncc.explain.per_finding import explain_finding
from explncc.fusion import FusedFinding


@dataclass
class BenchRow:
    backend: str
    model: str | None
    mode: str  # "generate" | "cached" | "skipped"
    findings: int
    total_ms: int
    cache_hits: int
    fallbacks: int
    chars: int
    note: str | None = None

    @property
    def mean_ms(self) -> int:
        return self.total_ms // self.findings if self.findings else 0


def _ollama_tags(host: str, timeout: float = 2.0) -> list[str] | None:
    """Installed model tags, or ``None`` when the server is unreachable."""

    try:
        response = httpx.get(f"{host}/api/tags", timeout=timeout)
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError):
        return None
    models = data.get("models", [])
    if not isinstance(models, list):
        return None
    return [m.get("name", "") for m in models if isinstance(m, dict)]


def _skip_row(backend: str, model: str | None, note: str) -> BenchRow:
    return BenchRow(
        backend=backend,
        model=model,
        mode="skipped",
        findings=0,
        total_ms=0,
        cache_hits=0,
        fallbacks=0,
        chars=0,
        note=note,
    )


def _timed_pass(
    findings: list[FusedFinding],
    *,
    backend: str,
    config: ExplnccConfig,
    mode: str,
) -> BenchRow:
    started = time.perf_counter()
    cache_hits = 0
    fallbacks = 0
    chars = 0
    model: str | None = None
    for finding in findings:
        result = explain_finding(finding, backend=backend, config=config)
        cache_hits += int(result.cache_hit)
        fallbacks += int(result.fallback_used)
        chars += len(result.text)
        model = result.model or model
    total_ms = int((time.perf_counter() - started) * 1000)
    note = None
    if fallbacks:
        note = f"{fallbacks} fell back to evidence text"
    return BenchRow(
        backend=backend,
        model=model,
        mode=mode,
        findings=len(findings),
        total_ms=total_ms,
        cache_hits=cache_hits,
        fallbacks=fallbacks,
        chars=chars,
        note=note,
    )


def run_bench(
    findings: list[FusedFinding],
    *,
    config: ExplnccConfig,
    backends: list[str],
    ollama_models: list[str] | None = None,
    include_cached: bool = True,
) -> list[BenchRow]:
    """Bench each backend over ``findings``; unavailable backends become skip rows."""

    rows: list[BenchRow] = []
    base = dataclasses.replace(config, cache_dir=None)

    for backend in backends:
        mode = backend.strip().lower()
        if mode == "rule":
            rows.append(_timed_pass(findings, backend="rule", config=base, mode="generate"))
            continue
        if config.no_network:
            rows.append(_skip_row(mode, None, "blocked by no-network guardrail"))
            continue
        if mode == "ollama":
            tags = _ollama_tags(base.ollama_host)
            if tags is None:
                rows.append(_skip_row("ollama", None, f"server unreachable at {base.ollama_host}"))
                continue
            models = ollama_models or [base.ollama_model]
            for model in models:
                # A bare tag means ":latest" to Ollama.
                if model not in tags and f"{model}:latest" not in tags:
                    rows.append(_skip_row("ollama", model, "model not pulled"))
                    continue
                cfg = dataclasses.replace(base, ollama_model=model)
                rows.append(_timed_pass(findings, backend="ollama", config=cfg, mode="generate"))
                if include_cached:
                    with tempfile.TemporaryDirectory(prefix="explncc-bench-") as tmp:
                        cached_cfg = dataclasses.replace(cfg, cache_dir=tmp)
                        _timed_pass(findings, backend="ollama", config=cached_cfg, mode="prime")
                        rows.append(
                            _timed_pass(
                                findings,
                                backend="ollama",
                                config=cached_cfg,
                                mode="cached",
                            ),
                        )
            continue
        if mode == "openai":
            if not base.openai_api_key:
                rows.append(_skip_row("openai", base.openai_model, "OPENAI_API_KEY unset"))
                continue
            rows.append(_timed_pass(findings, backend="openai", config=base, mode="generate"))
            continue
        if mode == "claude":
            if not base.anthropic_api_key:
                rows.append(_skip_row("claude", base.anthropic_model, "ANTHROPIC_API_KEY unset"))
                continue
            rows.append(_timed_pass(findings, backend="claude", config=base, mode="generate"))
            continue
        rows.append(_skip_row(mode, None, "unknown backend"))
    return rows


def render_bench(rows: list[BenchRow], *, fmt: str = "text") -> str:
    headers = ["backend", "model", "mode", "findings", "total", "per finding", "note"]

    def cells(row: BenchRow) -> list[str]:
        if row.mode == "skipped":
            total = per = "-"
        else:
            total = f"{row.total_ms / 1000:.1f}s"
            per = f"{row.mean_ms / 1000:.1f}s"
        return [
            row.backend,
            row.model or "-",
            row.mode,
            str(row.findings) if row.findings else "-",
            total,
            per,
            row.note or "",
        ]

    table = [cells(r) for r in rows]
    if fmt == "markdown":
        lines = [
            "| " + " | ".join(headers) + " |",
            "|" + "|".join("---" for _ in headers) + "|",
        ]
        lines += ["| " + " | ".join(c) + " |" for c in table]
        return "\n".join(lines)
    widths = [
        max(len(headers[i]), *(len(c[i]) for c in table)) if table else len(headers[i])
        for i in range(len(headers))
    ]
    out = ["  ".join(h.ljust(widths[i]) for i, h in enumerate(headers))]
    out += ["  ".join(c[i].ljust(widths[i]) for i in range(len(headers))) for c in table]
    return "\n".join(line.rstrip() for line in out)
