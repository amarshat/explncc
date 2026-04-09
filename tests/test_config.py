"""Environment configuration."""

from __future__ import annotations

import explncc.config as cfg


def test_load_config_defaults(monkeypatch) -> None:
    monkeypatch.delenv("EXPLNCC_BACKEND", raising=False)
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    c = cfg.load_config()
    assert c.default_backend == "rule"
    assert "11434" in c.ollama_host
    assert c.ollama_model
    assert c.openai_api_key is None
