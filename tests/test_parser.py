"""YAML stream and tag parsing."""

from __future__ import annotations

from pathlib import Path

from explncc.parser import _kind_from_tag, parse_opt_yaml_documents

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "inline_miss_no_definition.opt.yaml"


def test_parse_stream_preserves_kinds() -> None:
    text = FIXTURE.read_text(encoding="utf-8")
    docs = parse_opt_yaml_documents(text)
    kinds = [d.get("Kind") for d in docs if isinstance(d, dict)]
    assert "missed" in kinds
    assert "analysis" in kinds
    assert docs[0].get("Pass") == "inline"
    assert docs[0].get("Name") == "NoDefinition"


def test_analysis_variant_tags_do_not_crash() -> None:
    """LLVM emits !AnalysisFPCommute / !AnalysisAliasing beyond the base three."""
    text = (
        "--- !AnalysisFPCommute\n"
        "Pass:            loop-vectorize\n"
        "Name:            CantReorderFPOps\n"
        "Function:        dot\n"
        "...\n"
        "--- !AnalysisAliasing\n"
        "Pass:            loop-vectorize\n"
        "Name:            CantReorderMemOps\n"
        "Function:        dot\n"
        "...\n"
    )
    docs = parse_opt_yaml_documents(text)
    assert len(docs) == 2
    assert all(d.get("Kind") == "analysis" for d in docs)
    assert docs[0].get("Name") == "CantReorderFPOps"


def test_unknown_tag_degrades_to_unknown() -> None:
    text = "--- !SomethingNew\nPass: x\nName: y\n...\n"
    docs = parse_opt_yaml_documents(text)
    assert docs[0].get("Kind") == "unknown"


def test_kind_from_tag_mapping() -> None:
    assert _kind_from_tag("!AnalysisFPCommute") == "analysis"
    assert _kind_from_tag("!Missed") == "missed"
    assert _kind_from_tag("!Passed") == "passed"
    assert _kind_from_tag("!Whatever") == "unknown"
