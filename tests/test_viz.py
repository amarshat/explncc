"""Visualization / Mermaid builders."""

from __future__ import annotations

import json

from explncc.models import OptimizationRecord
from explncc.viz import (
    build_missed_top_mermaid,
    build_pass_remark_mermaid,
    build_pass_summary_mermaid,
    parse_viz_format,
    parse_viz_style,
    render_viz,
)


def test_parse_viz_format() -> None:
    assert parse_viz_format("JSON") == "json"


def test_parse_viz_style_invalid() -> None:
    try:
        parse_viz_style("nope")
    except ValueError as e:
        assert "unknown viz style" in str(e).lower()
    else:
        raise AssertionError


def test_pass_summary_mermaid_stable_ids() -> None:
    recs = [
        OptimizationRecord(kind="missed", pass_name="inline", remark_name="X"),
        OptimizationRecord(kind="passed", pass_name="inline", remark_name="Y"),
        OptimizationRecord(kind="missed", pass_name="gvn", remark_name="Z"),
    ]
    text = build_pass_summary_mermaid(recs, top=5)
    assert "flowchart TD" in text
    assert "inline" in text
    assert "missed" in text and "inline" in text


def test_pass_remark_mermaid_edges() -> None:
    recs = [
        OptimizationRecord(kind="missed", pass_name="inline", remark_name="A"),
        OptimizationRecord(kind="missed", pass_name="inline", remark_name="A"),
        OptimizationRecord(kind="missed", pass_name="gvn", remark_name="B"),
    ]
    text = build_pass_remark_mermaid(recs, top=10)
    assert "-->" in text
    assert "2×" in text or "2" in text


def test_missed_top_empty() -> None:
    text = build_missed_top_mermaid([], top=5)
    assert "No missed" in text


def test_render_viz_json_has_join_hints() -> None:
    recs = [OptimizationRecord(kind="passed", pass_name="inline", remark_name="Inlined")]
    s = render_viz(
        "json",
        recs,
        "pass-summary",
        top=5,
        title="T1",
        explanation=None,
    )
    data = json.loads(s)
    assert data["title"] == "T1"
    assert "mermaid" in data
    assert "join_hints" in data


def test_render_viz_html_contains_mermaid_div() -> None:
    recs = [OptimizationRecord(kind="missed", pass_name="inline", remark_name="N")]
    s = render_viz(
        "html",
        recs,
        "missed-top",
        top=3,
        title="Hi",
        explanation="Rule text",
    )
    assert "<!DOCTYPE html>" in s
    assert 'class="mermaid"' in s
    assert "Rule text" in s
    assert "mermaid.min.js" in s
