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


def load_config() -> ExplnccConfig:
    return ExplnccConfig(
        default_backend=os.environ.get("EXPLNCC_BACKEND", "rule").strip().lower() or "rule",
        ollama_host=os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/"),
        ollama_model=os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b-instruct").strip(),
        openai_api_key=os.environ.get("OPENAI_API_KEY"),
        openai_model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip(),
    )
