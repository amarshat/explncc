"""Short, per-finding model explanations for ``explncc why --explain``.

The batch ``explain`` path serializes dozens of records into one prompt and
asks for an essay; that is the slowest possible shape for a local model and
the model has to re-derive what the fusion layer already knows. This path
inverts it: the fused finding already carries the compiler's verdict, cause,
and suggestion, so the model's job is two sentences and one next step over a
tiny prompt with a hard output cap. Small job, small prompt, small latency.

Each finding is cached individually (content-addressed on the finding's
records, the prompt, the backend, and the model), so a re-run after an
unchanged build answers from disk.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx

from explncc import __version__
from explncc.config import ExplnccConfig
from explncc.explain.cache import cache_load, cache_store, explanation_cache_key
from explncc.fusion import FusedFinding
from explncc.prompt_registry import hash_prompt_text
from explncc.record_identity import hash_payload

# Hard cap on generated tokens: two sentences plus a next-step line.
MAX_OUTPUT_TOKENS = 140
TEMPERATURE = 0.2

SYSTEM_WHY = (
    "You annotate compiler optimization findings for C/C++ engineers. "
    "The compiler evidence given to you is authoritative and complete; never "
    "contradict it and never invent flags, pragmas, functions, file names, or "
    "numbers that are not in the evidence. Plain text only, no markdown."
)

_USER_TEMPLATE = (
    "function: {function}\n"
    "location: {location}\n"
    "verdict: {verdict}\n"
    "compiler cause: {cause}\n"
    "compiler suggestion: {suggestion}\n"
    "pass: {pass_name} ({kind}, remark {remark})\n\n"
    "In at most two sentences, explain what the compiler decided here and why "
    "it matters for performance. Then one line starting 'next:' with one "
    "concrete step grounded in the evidence above."
)


@dataclass
class FindingExplanation:
    text: str
    backend: str
    model: str | None
    latency_ms: int
    cache_hit: bool = False
    fallback_used: bool = False
    error: str | None = None


def build_finding_prompt(finding: FusedFinding) -> str:
    """Deterministic, evidence-only user prompt for one finding."""

    return _USER_TEMPLATE.format(
        function=finding.function_display or finding.function or "<unknown>",
        location=finding.location(),
        verdict=finding.headline,
        cause=finding.cause or "not stated in the record",
        suggestion=finding.suggestion or "none in the record",
        pass_name=finding.pass_name or "?",
        kind=finding.kind or "?",
        remark=finding.remark_name or "?",
    )


def finding_evidence_hash(finding: FusedFinding) -> str:
    """Content hash over the finding's records (stable across runs)."""

    keys = sorted(r.record_hash or r.semantic_key or (r.message or "") for r in finding.records)
    return hash_payload({"finding_records": keys, "headline": finding.headline})


def deterministic_finding_text(finding: FusedFinding) -> str:
    """Rule-tier text assembled from the evidence already on the finding."""

    bits = [finding.headline]
    if finding.cause:
        bits.append(f"compiler evidence: {finding.cause}")
    if finding.suggestion:
        bits.append(f"next: {finding.suggestion}")
    return "\n".join(bits)


def _ollama_stream(
    config: ExplnccConfig,
    user: str,
    on_chunk: Callable[[str], None] | None,
) -> str:
    """Stream a short chat completion from Ollama; return the full text."""

    url = f"{config.ollama_host}/api/chat"
    payload = {
        "model": config.ollama_model,
        "stream": True,
        "options": {"num_predict": MAX_OUTPUT_TOKENS, "temperature": TEMPERATURE},
        "messages": [
            {"role": "system", "content": SYSTEM_WHY},
            {"role": "user", "content": user},
        ],
    }
    parts: list[str] = []
    with httpx.Client(timeout=120.0) as client, client.stream("POST", url, json=payload) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line.strip():
                continue
            try:
                data = json.loads(line)
            except ValueError:
                continue
            chunk = data.get("message", {}).get("content", "")
            if isinstance(chunk, str) and chunk:
                parts.append(chunk)
                if on_chunk is not None:
                    on_chunk(chunk)
            if data.get("done"):
                break
    text = "".join(parts).strip()
    if not text:
        msg = "Ollama returned an empty response."
        raise RuntimeError(msg)
    return text


def _api_chat_short(backend: str, config: ExplnccConfig, user: str) -> str:
    """Short-completion variants of the hosted backends (no streaming)."""

    if backend == "openai":
        if not config.openai_api_key:
            msg = "OPENAI_API_KEY is not set."
            raise RuntimeError(msg)
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {config.openai_api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, object] = {
            "model": config.openai_model,
            "messages": [
                {"role": "system", "content": SYSTEM_WHY},
                {"role": "user", "content": user},
            ],
            "temperature": TEMPERATURE,
            "max_tokens": MAX_OUTPUT_TOKENS,
        }
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        content = (data.get("choices") or [{}])[0].get("message", {}).get("content")
        if not isinstance(content, str) or not content.strip():
            msg = "OpenAI returned an empty message."
            raise RuntimeError(msg)
        return content.strip()
    if backend == "claude":
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
            "max_tokens": MAX_OUTPUT_TOKENS,
            "system": SYSTEM_WHY,
            "messages": [{"role": "user", "content": user}],
        }
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        texts = [
            b.get("text", "")
            for b in data.get("content", [])
            if isinstance(b, dict) and b.get("type") == "text"
        ]
        joined = "\n".join(t for t in texts if t).strip()
        if not joined:
            msg = "Anthropic returned an empty response."
            raise RuntimeError(msg)
        return joined
    msg = f"unsupported per-finding backend: {backend}"
    raise ValueError(msg)


def _model_name(backend: str, config: ExplnccConfig) -> str | None:
    return {
        "ollama": config.ollama_model,
        "openai": config.openai_model,
        "claude": config.anthropic_model,
    }.get(backend)


def explain_finding(
    finding: FusedFinding,
    *,
    backend: str,
    config: ExplnccConfig,
    on_chunk: Callable[[str], None] | None = None,
) -> FindingExplanation:
    """Explain one finding: cache first, model second, evidence text as fallback.

    ``on_chunk`` receives streamed text as it arrives (Ollama only). Cached and
    fallback texts are delivered through ``on_chunk`` in one piece so callers
    can render every path the same way.
    """

    started = time.perf_counter()
    mode = backend.strip().lower()

    def _elapsed() -> int:
        return int((time.perf_counter() - started) * 1000)

    if mode == "rule":
        text = deterministic_finding_text(finding)
        if on_chunk is not None:
            on_chunk(text)
        return FindingExplanation(
            text=text,
            backend="rule",
            model=None,
            latency_ms=_elapsed(),
        )

    model = _model_name(mode, config)
    prompt = build_finding_prompt(finding)
    cache_key = None
    if config.cache_dir:
        cache_key = explanation_cache_key(
            evidence_hash=finding_evidence_hash(finding),
            prompt_hash=hash_prompt_text(SYSTEM_WHY + "\n" + prompt),
            backend=mode,
            model=model,
            version=__version__,
        )
        cached = cache_load(config.cache_dir, cache_key)
        if cached and isinstance(cached.get("text"), str) and cached["text"].strip():
            if on_chunk is not None:
                on_chunk(cached["text"])
            return FindingExplanation(
                text=cached["text"],
                backend=mode,
                model=model,
                latency_ms=_elapsed(),
                cache_hit=True,
            )

    try:
        if mode == "ollama":
            text = _ollama_stream(config, prompt, on_chunk)
        else:
            text = _api_chat_short(mode, config, prompt)
            if on_chunk is not None:
                on_chunk(text)
    except Exception as exc:  # noqa: BLE001 (fallback must never crash triage)
        fallback = deterministic_finding_text(finding)
        if on_chunk is not None:
            on_chunk(fallback)
        return FindingExplanation(
            text=fallback,
            backend=mode,
            model=model,
            latency_ms=_elapsed(),
            fallback_used=True,
            error=str(exc),
        )

    if cache_key:
        cache_store(
            config.cache_dir,
            cache_key,
            {"text": text, "backend": mode, "model": model},
        )
    return FindingExplanation(
        text=text,
        backend=mode,
        model=model,
        latency_ms=_elapsed(),
    )
