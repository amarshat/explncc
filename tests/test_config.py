"""Environment configuration."""

from __future__ import annotations

import explncc.config as cfg


def test_load_config_defaults(monkeypatch) -> None:
    monkeypatch.delenv("EXPLNCC_BACKEND", raising=False)
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    c = cfg.load_config()
    assert c.default_backend == "rule"
    assert "11434" in c.ollama_host
    assert c.ollama_model
    assert c.openai_api_key is None
    assert c.anthropic_api_key is None
    assert "claude" in c.anthropic_model.lower()


def test_doctor_payload_masks_secrets(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ant-secret")
    p = cfg.doctor_payload()
    assert p["openai_api_key"] == "set"
    assert p["anthropic_api_key"] == "set"
