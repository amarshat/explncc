"""On-device explanation cache (Chapter 15)."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from explncc.config import load_config
from explncc.explain import backends
from explncc.explain.cache import (
    cache_load,
    cache_store,
    explanation_cache_key,
)
from explncc.models import OptimizationRecord


def _records() -> list[OptimizationRecord]:
    return [
        OptimizationRecord(
            kind="missed",
            pass_name="inline",
            remark_name="NoDefinition",
            function="f",
            file="a.cpp",
            line=1,
            message="callee body unavailable",
        ),
    ]


def test_cache_key_stable_and_sensitive() -> None:
    base = dict(
        evidence_hash="e1", prompt_hash="p1", backend="ollama", model="m", version="0.1.0"
    )
    k = explanation_cache_key(**base)
    assert k == explanation_cache_key(**base)  # stable
    # each input changes the key
    assert k != explanation_cache_key(**{**base, "evidence_hash": "e2"})
    assert k != explanation_cache_key(**{**base, "prompt_hash": "p2"})
    assert k != explanation_cache_key(**{**base, "backend": "openai"})
    assert k != explanation_cache_key(**{**base, "model": "m2"})
    assert k != explanation_cache_key(**{**base, "version": "0.2.0"})


def test_cache_store_load_roundtrip(tmp_path: Path) -> None:
    key = "abc123"
    assert cache_load(tmp_path, key) is None  # miss on empty dir
    cache_store(tmp_path, key, {"text": "hello", "backend": "ollama"})
    loaded = cache_load(tmp_path, key)
    assert loaded is not None and loaded["text"] == "hello"
    assert cache_load(None, key) is None  # no cache dir -> always miss


def test_run_explanation_result_uses_cache(tmp_path: Path, monkeypatch) -> None:
    calls = {"n": 0}

    def fake_run_explanation(records, *, backend, config, ai_limit):  # noqa: ANN001
        calls["n"] += 1
        return "MODEL EXPLANATION TEXT"

    monkeypatch.setattr(backends, "run_explanation", fake_run_explanation)
    cfg = replace(load_config(), cache_dir=str(tmp_path))
    recs = _records()

    first = backends.run_explanation_result(recs, backend="ollama", config=cfg)
    assert first.text == "MODEL EXPLANATION TEXT"
    assert first.cache_hit is False
    assert calls["n"] == 1

    second = backends.run_explanation_result(recs, backend="ollama", config=cfg)
    assert second.text == "MODEL EXPLANATION TEXT"
    assert second.cache_hit is True
    assert calls["n"] == 1  # backend NOT called again


def test_no_cache_dir_means_no_caching(tmp_path: Path, monkeypatch) -> None:
    calls = {"n": 0}

    def fake_run_explanation(records, *, backend, config, ai_limit):  # noqa: ANN001
        calls["n"] += 1
        return "TEXT"

    monkeypatch.setattr(backends, "run_explanation", fake_run_explanation)
    cfg = replace(load_config(), cache_dir=None)
    recs = _records()
    backends.run_explanation_result(recs, backend="ollama", config=cfg)
    r = backends.run_explanation_result(recs, backend="ollama", config=cfg)
    assert r.cache_hit is False
    assert calls["n"] == 2  # called both times, nothing cached


def test_fallback_is_not_cached(tmp_path: Path, monkeypatch) -> None:
    def fallback(records, *, backend, config, ai_limit):  # noqa: ANN001
        return "Showing rule-based explanation only (Auto: Ollama unavailable)"

    monkeypatch.setattr(backends, "run_explanation", fallback)
    cfg = replace(load_config(), cache_dir=str(tmp_path))
    recs = _records()
    r = backends.run_explanation_result(recs, backend="auto", config=cfg)
    assert r.fallback_used is True
    # nothing was written to the cache
    assert not list((tmp_path / "explanations").glob("*.json"))
