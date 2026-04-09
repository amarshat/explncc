"""Orchestrate rule, Ollama, and OpenAI backends."""

from __future__ import annotations

import json
from typing import Any

import httpx

from explncc.config import ExplnccConfig
from explncc.explain import prompts
from explncc.explain.rule_based import build_rule_explanation
from explncc.models import OptimizationRecord


def _records_json_slice(records: list[OptimizationRecord], limit: int) -> str:
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
            },
        )
    return json.dumps(slim, indent=2, ensure_ascii=False)


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

    if mode == "auto":
        ollama_err: str | None = None
        if ollama_available(config.ollama_host):
            try:
                extra = _ollama_chat(config, payload)
                return f"{rule}\n\n---\nModel augmentation (Ollama, auto)\n\n{extra}"
            except Exception as exc:
                ollama_err = str(exc)
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
