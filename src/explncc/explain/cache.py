"""On-device cache for model-backed explanations.

Model explanations cost money and time, but for an unchanged input they should
not be recomputed. The cache is content-addressed: the key folds in the evidence
hash, the prompt hash, the backend, the model, and the explncc version, so a
change to any of those produces a fresh key and a stale explanation is never
served. Only successful model-backed results are cached; the rule backend is
already free and deterministic. Cache I/O is best-effort and never raises into
the pipeline: a missing or unreadable cache simply behaves as a miss.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

# Bump when the cached payload shape changes so old entries are ignored.
CACHE_SCHEMA = 1


def explanation_cache_key(
    *,
    evidence_hash: str | None,
    prompt_hash: str | None,
    backend: str,
    model: str | None,
    version: str,
) -> str:
    """Stable content-addressed key for one explanation."""

    parts = [
        f"schema={CACHE_SCHEMA}",
        f"evidence={evidence_hash or ''}",
        f"prompt={prompt_hash or ''}",
        f"backend={backend}",
        f"model={model or ''}",
        f"version={version}",
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _entry_path(cache_dir: str | Path, key: str) -> Path:
    return Path(cache_dir).expanduser() / "explanations" / f"{key}.json"


def cache_load(cache_dir: str | Path | None, key: str) -> dict[str, Any] | None:
    """Return the cached payload for ``key`` or ``None`` on any miss/error."""

    if not cache_dir:
        return None
    path = _entry_path(cache_dir, key)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def cache_store(cache_dir: str | Path | None, key: str, payload: dict[str, Any]) -> None:
    """Write ``payload`` for ``key``. Best-effort: errors are swallowed."""

    if not cache_dir:
        return
    path = _entry_path(cache_dir, key)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        return
