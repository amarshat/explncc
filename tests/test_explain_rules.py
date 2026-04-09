"""Rule-based explainer."""

from __future__ import annotations

from pathlib import Path

from explncc.explain.rule_based import build_rule_explanation
from explncc.normalizer import load_records_from_path

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "inline_miss_no_definition.opt.yaml"


def test_rule_mentions_translation_unit() -> None:
    recs = load_records_from_path(FIXTURE)
    text = build_rule_explanation(recs)
    assert "translation unit" in text.lower() or "inliner" in text.lower()
