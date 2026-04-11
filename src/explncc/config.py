"""Environment-driven configuration for optional model backends."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ExplnccConfig:
    default_backend: str
    ollama_host: str
    ollama_model: str
    openai_api_key: str | None
    openai_model: str
    anthropic_api_key: str | None
    anthropic_model: str


def load_config() -> ExplnccConfig:
    return ExplnccConfig(
        default_backend=os.environ.get("EXPLNCC_BACKEND", "rule").strip().lower() or "rule",
        ollama_host=os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/"),
        ollama_model=os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b-instruct").strip(),
        openai_api_key=os.environ.get("OPENAI_API_KEY"),
        openai_model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip(),
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
        anthropic_model=os.environ.get(
            "ANTHROPIC_MODEL",
            "claude-3-5-haiku-20241022",
        ).strip(),
    )


def doctor_payload() -> dict[str, str]:
    """Masked view of backend-related environment for CI debugging."""

    c = load_config()
    return {
        "default_backend": c.default_backend,
        "ollama_host": c.ollama_host,
        "ollama_model": c.ollama_model,
        "openai_api_key": "set" if c.openai_api_key else "unset",
        "openai_model": c.openai_model,
        "anthropic_api_key": "set" if c.anthropic_api_key else "unset",
        "anthropic_model": c.anthropic_model,
    }
