"""Orchestrate rule, Ollama, Anthropic (Claude), and OpenAI backends."""

from __future__ import annotations

import json
import time
from typing import Any

import httpx

from explncc.config import ExplnccConfig
from explncc.evidence import build_evidence_packs
from explncc.explain import prompts
from explncc.explain.contracts import ExplanationResult
from explncc.explain.rule_based import build_rule_explanation
from explncc.models import OptimizationRecord
from explncc.prompt_registry import hash_prompt_text, render_explain_prompt
from explncc.record_identity import hash_payload


def _records_json_slice(records: list[OptimizationRecord], limit: int) -> str:
    """Normalized record JSON for model backends (never raw YAML)."""

    slim: list[dict[str, Any]] = []
    for r in records[:limit]:
        slim.append(
            {
                "kind": r.kind,
                "pass_name": r.pass_name,
                "remark_name": r.remark_name,
                "function": r.function,
                "file": r.file,
                "line": r.line,
                "column": r.column,
                "message": r.message,
                "cost": r.cost,
                "threshold": r.threshold,
                "vectorization_factor": r.vectorization_factor,
                "unroll_factor": r.unroll_factor,
                "record_hash": r.record_hash,
            },
        )
    return json.dumps(slim, indent=2, ensure_ascii=False)


def _evidence_hash(records: list[OptimizationRecord]) -> str | None:
    if not records:
        return None
    packs = build_evidence_packs(records[: min(len(records), 8)])
    parts = [p.evidence_hash for p in packs if p.evidence_hash]
    if not parts:
        return None
    return hash_payload({"evidence_hashes": sorted(parts)})


def ollama_available(host: str, timeout: float = 2.0) -> bool:
    try:
        response = httpx.get(f"{host}/api/tags", timeout=timeout)
        return response.status_code == 200
    except httpx.HTTPError:
        return False
    except Exception:
        return False


def _ollama_chat(config: ExplnccConfig, user: str) -> str:
    url = f"{config.ollama_host}/api/chat"
    payload = {
        "model": config.ollama_model,
        "stream": False,
        "messages": [
            {"role": "system", "content": prompts.SYSTEM_EXPLAIN},
            {"role": "user", "content": user},
        ],
    }
    with httpx.Client(timeout=120.0) as client:
        response = client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
    msg = data.get("message", {})
    content = msg.get("content")
    if not isinstance(content, str) or not content.strip():
        msg = "Ollama returned an empty response."
        raise RuntimeError(msg)
    return content.strip()


def _openai_chat(config: ExplnccConfig, user: str) -> str:
    if not config.openai_api_key:
        msg = "OPENAI_API_KEY is not set."
        raise RuntimeError(msg)
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {config.openai_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config.openai_model,
        "messages": [
            {"role": "system", "content": prompts.SYSTEM_EXPLAIN},
            {"role": "user", "content": user},
        ],
        "temperature": 0.2,
    }
    with httpx.Client(timeout=120.0) as client:
        response = client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
    choices = data.get("choices", [])
    if not choices:
        msg = "OpenAI returned no choices."
        raise RuntimeError(msg)
    message = choices[0].get("message", {})
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        msg = "OpenAI returned an empty message."
        raise RuntimeError(msg)
    return content.strip()


def _anthropic_chat(config: ExplnccConfig, user: str) -> str:
    if not config.anthropic_api_key:
        msg = "ANTHROPIC_API_KEY is not set."
        raise RuntimeError(msg)
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": config.anthropic_api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config.anthropic_model,
        "max_tokens": 4096,
        "system": prompts.SYSTEM_EXPLAIN,
        "messages": [{"role": "user", "content": user}],
    }
    with httpx.Client(timeout=120.0) as client:
        response = client.post(url, json=payload, headers=headers)
        response.raise_for_status()
    data = response.json()
    blocks = data.get("content", [])
    if not isinstance(blocks, list):
        msg = "Anthropic returned unexpected content."
        raise RuntimeError(msg)
    texts: list[str] = []
    for block in blocks:
        if isinstance(block, dict) and block.get("type") == "text":
            t = block.get("text")
            if isinstance(t, str):
                texts.append(t)
    joined = "\n".join(texts).strip()
    if not joined:
        msg = "Anthropic returned an empty response."
        raise RuntimeError(msg)
    return joined


def run_explanation_result(
    records: list[OptimizationRecord],
    *,
    backend: str,
    config: ExplnccConfig,
    ai_limit: int = 48,
) -> ExplanationResult:
    """Structured backend result with hashes and fallback metadata."""

    started = time.perf_counter()
    rule = build_rule_explanation(records)
    mode = backend.strip().lower()
    records_json = _records_json_slice(records, ai_limit)
    prompt_text, template_id, _ = render_explain_prompt(
        rule_summary=rule,
        records_json=records_json,
    )
    prompt_hash = hash_prompt_text(prompt_text)
    evidence_hash = _evidence_hash(records)

    if mode == "rule":
        return ExplanationResult(
            backend="rule",
            model=None,
            success=True,
            text=rule,
            prompt_hash=prompt_hash,
            evidence_hash=evidence_hash,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

    try:
        text = run_explanation(records, backend=mode, config=config, ai_limit=ai_limit)
    except ValueError as exc:
        return ExplanationResult(
            backend=mode,
            model=None,
            success=False,
            text=rule,
            fallback_used=True,
            warnings=[str(exc)],
            prompt_hash=prompt_hash,
            evidence_hash=evidence_hash,
            error_type="ValueError",
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

    used_fallback = "Showing rule-based explanation only" in text or "Auto: Ollama unavailable" in text
    model_name: str | None = None
    if mode == "ollama":
        model_name = config.ollama_model
    elif mode == "openai":
        model_name = config.openai_model
    elif mode == "claude":
        model_name = config.anthropic_model
    elif mode == "auto":
        model_name = "auto"

    return ExplanationResult(
        backend=mode,
        model=model_name,
        success=not used_fallback or bool(text.strip()),
        text=text,
        fallback_used=used_fallback,
        warnings=[] if not used_fallback else ["model backend failed; rule text retained"],
        prompt_hash=prompt_hash,
        evidence_hash=evidence_hash,
        latency_ms=int((time.perf_counter() - started) * 1000),
    )


_NETWORK_BACKENDS = {"ollama", "openai", "claude", "auto"}


def _guard_no_network(mode: str, config: ExplnccConfig) -> None:
    """Raise when a network backend is requested but the no-network guardrail is set."""

    if config.no_network and mode in _NETWORK_BACKENDS:
        msg = (
            f"network backend {mode!r} is blocked because no-network mode is active "
            "(EXPLNCC_NO_NETWORK/EXPLNCC_OFFLINE). Use backend 'rule' or local mode."
        )
        raise ValueError(msg)


def run_explanation(
    records: list[OptimizationRecord],
    *,
    backend: str,
    config: ExplnccConfig,
    ai_limit: int = 48,
) -> str:
    """Return printable explanation text (rule-only or rule + model augmentation)."""

    rule = build_rule_explanation(records)
    mode = backend.strip().lower()
    if mode == "rule":
        return rule
    _guard_no_network(mode, config)

    payload = prompts.user_message(
        rule_summary=rule,
        records_json=_records_json_slice(records, ai_limit),
    )

    if mode == "ollama":
        try:
            extra = _ollama_chat(config, payload)
        except Exception as exc:
            return (
                f"{rule}\n\n---\nModel augmentation (Ollama) failed: {exc}. "
                "Showing rule-based explanation only."
            )
        return f"{rule}\n\n---\nModel augmentation (Ollama)\n\n{extra}"

    if mode == "openai":
        try:
            extra = _openai_chat(config, payload)
        except Exception as exc:
            return (
                f"{rule}\n\n---\nModel augmentation (OpenAI) failed: {exc}. "
                "Showing rule-based explanation only."
            )
        return f"{rule}\n\n---\nModel augmentation (OpenAI)\n\n{extra}"

    if mode == "claude":
        try:
            extra = _anthropic_chat(config, payload)
        except Exception as exc:
            return (
                f"{rule}\n\n---\nModel augmentation (Claude) failed: {exc}. "
                "Showing rule-based explanation only."
            )
        return f"{rule}\n\n---\nModel augmentation (Claude)\n\n{extra}"

    if mode == "auto":
        ollama_err: str | None = None
        if ollama_available(config.ollama_host):
            try:
                extra = _ollama_chat(config, payload)
                return f"{rule}\n\n---\nModel augmentation (Ollama, auto)\n\n{extra}"
            except Exception as exc:
                ollama_err = str(exc)
        if config.anthropic_api_key:
            try:
                extra = _anthropic_chat(config, payload)
                note = f" (Ollama skipped: {ollama_err})" if ollama_err else ""
                return f"{rule}\n\n---\nModel augmentation (Claude, auto){note}\n\n{extra}"
            except Exception as exc:
                anthropic_err = str(exc)
                if config.openai_api_key:
                    try:
                        extra = _openai_chat(config, payload)
                        note = f" (prior: Ollama={ollama_err!r}; Claude={anthropic_err!r})"
                        return f"{rule}\n\n---\nModel augmentation (OpenAI, auto){note}\n\n{extra}"
                    except Exception as openai_exc:
                        return (
                            f"{rule}\n\n---\nModel augmentation skipped (auto): {openai_exc}. "
                            "Showing rule-based explanation only."
                        )
                return (
                    f"{rule}\n\n---\nModel augmentation skipped (auto, Claude): {anthropic_err}. "
                    "Showing rule-based explanation only."
                )
        if config.openai_api_key:
            try:
                extra = _openai_chat(config, payload)
                note = f" (Ollama skipped: {ollama_err})" if ollama_err else ""
                return f"{rule}\n\n---\nModel augmentation (OpenAI, auto){note}\n\n{extra}"
            except Exception as exc:
                return (
                    f"{rule}\n\n---\nModel augmentation skipped (auto): {exc}. "
                    "Showing rule-based explanation only."
                )
        if ollama_err:
            return f"{rule}\n\n---\nAuto: Ollama unavailable or failed ({ollama_err})."
        return rule

    msg = f"unknown backend: {backend!r}"
    raise ValueError(msg)
