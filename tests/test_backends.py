"""Optional HTTP backends (mocked)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from explncc.config import ExplnccConfig
from explncc.explain.backends import _ollama_chat, _openai_chat, ollama_available, run_explanation
from explncc.models import OptimizationRecord


def test_ollama_available_false_on_error() -> None:
    with patch("explncc.explain.backends.httpx.get", side_effect=OSError("nope")):
        assert not ollama_available("http://127.0.0.1:11434")


def test_ollama_chat_parses_message() -> None:
    cfg = ExplnccConfig(
        default_backend="ollama",
        ollama_host="http://x",
        ollama_model="m",
        openai_api_key=None,
        openai_model="gpt-4o-mini",
    )
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"message": {"content": "  hello  "}}
    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.post.return_value = mock_response
    with patch("explncc.explain.backends.httpx.Client", return_value=mock_client):
        assert _ollama_chat(cfg, "user") == "hello"


def test_openai_chat_parses_choice() -> None:
    cfg = ExplnccConfig(
        default_backend="openai",
        ollama_host="http://x",
        ollama_model="m",
        openai_api_key="k",
        openai_model="gpt-4o-mini",
    )
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.post.return_value = mock_response
    with patch("explncc.explain.backends.httpx.Client", return_value=mock_client):
        assert _openai_chat(cfg, "u") == "ok"


def test_run_explanation_rule_only() -> None:
    cfg = ExplnccConfig(
        default_backend="rule",
        ollama_host="http://127.0.0.1:11434",
        ollama_model="m",
        openai_api_key=None,
        openai_model="gpt-4o-mini",
    )
    r = OptimizationRecord(
        kind="missed",
        pass_name="inline",
        remark_name="NoDefinition",
        function="main",
        file="f.cpp",
        line=1,
        column=1,
        message="because its definition is unavailable",
    )
    text = run_explanation([r], backend="rule", config=cfg)
    assert "translation unit" in text.lower() or "inliner" in text.lower()
