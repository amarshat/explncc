"""YAML stream and tag parsing."""

from __future__ import annotations

from pathlib import Path

from explncc.parser import parse_opt_yaml_documents

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "inline_miss_no_definition.opt.yaml"


def test_parse_stream_preserves_kinds() -> None:
    text = FIXTURE.read_text(encoding="utf-8")
    docs = parse_opt_yaml_documents(text)
    kinds = [d.get("Kind") for d in docs if isinstance(d, dict)]
    assert "missed" in kinds
    assert "analysis" in kinds
    assert docs[0].get("Pass") == "inline"
    assert docs[0].get("Name") == "NoDefinition"
