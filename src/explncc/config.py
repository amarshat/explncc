"""Environment-driven configuration for optional model backends."""

from __future__ import annotations

import os
import platform
import sys
from dataclasses import dataclass
from typing import Any

from explncc import __version__

_TRUE_VALUES = {"1", "true", "yes", "on"}


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUE_VALUES


@dataclass(frozen=True)
class ExplnccConfig:
    default_backend: str
    ollama_host: str
    ollama_model: str
    openai_api_key: str | None
    openai_model: str
    anthropic_api_key: str | None
    anthropic_model: str
    cache_dir: str | None = None
    no_network: bool = False


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
        cache_dir=os.environ.get("EXPLNCC_CACHE_DIR"),
        no_network=_env_flag("EXPLNCC_NO_NETWORK") or _env_flag("EXPLNCC_OFFLINE"),
    )


def doctor_payload() -> dict[str, str]:
    """Masked view of backend-related environment for CI debugging."""

    report = build_doctor_report()
    return {k: str(v) for k, v in report.items() if isinstance(v, str)}


def build_doctor_report() -> dict[str, Any]:
    """Safe diagnostic payload for ``explncc doctor`` (never prints raw secrets)."""

    # Imported lazily: keep config.py free of the prompt_registry -> explain ->
    # backends -> config import cycle so ``import explncc.config`` is order-safe.
    from explncc.prompt_registry import list_prompt_template_ids

    c = load_config()
    warnings: list[str] = []
    if c.default_backend != "rule" and not any(
        (c.openai_api_key, c.anthropic_api_key, c.ollama_host),
    ):
        warnings.append("default backend is not rule but no remote backends appear configured")

    return {
        "explncc_version": __version__,
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "offline_first": True,
        "no_network": c.no_network,
        "network_backends_allowed": not c.no_network,
        "default_backend": c.default_backend,
        "ollama_host_configured": bool(c.ollama_host),
        "ollama_host": c.ollama_host,
        "ollama_model_configured": bool(c.ollama_model),
        "ollama_model": c.ollama_model,
        "openai_key_configured": bool(c.openai_api_key),
        "openai_api_key": "set" if c.openai_api_key else "unset",
        "openai_model_configured": bool(c.openai_model),
        "openai_model": c.openai_model,
        "anthropic_key_configured": bool(c.anthropic_api_key),
        "anthropic_api_key": "set" if c.anthropic_api_key else "unset",
        "anthropic_model_configured": bool(c.anthropic_model),
        "anthropic_model": c.anthropic_model,
        "available_report_formats": ["markdown", "json", "github", "html"],
        "available_prompt_templates": list_prompt_template_ids(),
        "cache_dir": c.cache_dir,
        "warnings": warnings,
    }


def render_doctor(fmt: str) -> str:
    data = build_doctor_report()
    if fmt == "json":
        import json

        return json.dumps(data, indent=2, ensure_ascii=False)
    if fmt == "markdown":
        lines = ["# explncc doctor", ""]
        for key, val in data.items():
            if key == "warnings":
                continue
            lines.append(f"- **{key}:** `{val}`")
        if data.get("warnings"):
            lines.append("")
            lines.append("## Warnings")
            for w in data["warnings"]:
                lines.append(f"- {w}")
        return "\n".join(lines)
    import json

    return json.dumps(data, indent=2, ensure_ascii=False)
