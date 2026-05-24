"""CI report builders (Markdown, JSON, GitHub)."""

from __future__ import annotations

import json

import pytest

from explncc.checks import build_policy_result
from explncc.ci_report import (
    build_github_comment,
    build_html_report,
    build_json_payload,
    build_markdown_report,
    parse_report_format,
    render_report,
    top_missed_remarks,
)
from explncc.models import OptimizationRecord
from explncc.report_types import (
    REPORT_SCHEMA_VERSION,
    ExplanationInfo,
    ReportBuildOptions,
    ReportMetadata,
    ReportSourceInfo,
)


def _args(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "source": ReportSourceInfo("build/app.opt.yaml", 1, 1),
        "metadata": ReportMetadata(),
        "options": ReportBuildOptions(title="Compiler Optimization Report"),
        "policy": None,
        "explanation": ExplanationInfo(enabled=False),
    }
    base.update(overrides)
    return base


def test_parse_report_format() -> None:
    assert parse_report_format("GITHUB") == "github"
    assert parse_report_format("HTML") == "html"


def test_parse_report_format_invalid() -> None:
    with pytest.raises(ValueError, match="unknown report format"):
        parse_report_format("docx")


def test_markdown_collapses_gappy_compiler_message() -> None:
    recs = [
        OptimizationRecord(
            kind="missed",
            pass_name="gvn",
            remark_name="LoadClobbered",
            message="load  of  type   double  not eliminated",
            file="f.cpp",
            line=1,
        ),
    ]
    text = build_markdown_report(recs, **_args())
    assert "load of type double not eliminated" in text


def test_top_missed_respects_limit() -> None:
    recs = [
        OptimizationRecord(kind="missed", pass_name="inline", remark_name="A"),
        OptimizationRecord(kind="passed", pass_name="inline", remark_name="B"),
        OptimizationRecord(kind="missed", pass_name="gvn", remark_name="C"),
    ]
    assert len(top_missed_remarks(recs, 1)) == 1
    assert top_missed_remarks(recs, 1)[0].remark_name == "A"


def test_markdown_contains_sections() -> None:
    recs = [
        OptimizationRecord(
            kind="missed",
            pass_name="inline",
            remark_name="X",
            message="too costly",
            file="a.cpp",
            line=3,
        ),
    ]
    text = build_markdown_report(recs, **_args())
    assert "# Compiler Optimization Report" in text
    assert "## Build Metadata" in text
    assert "## Summary" in text
    assert "## Policy" in text
    assert "## Top Missed Optimizations" in text
    assert "## Raw Artifact Notice" in text
    assert "`.opt.yaml` file remains the source of truth" in text
    assert "#### 1." in text
    assert "**Compiler message:**" in text
    assert "too costly" in text


def test_json_payload_schema() -> None:
    recs = [OptimizationRecord(kind="missed", pass_name="inline", remark_name="r")]
    policy = build_policy_result(recs, max_missed_inline=0)
    payload = build_json_payload(
        recs,
        **_args(
            policy=policy,
            metadata=ReportMetadata(git_sha="abc123", ci_provider="github"),
            options=ReportBuildOptions(top_missed=5),
        ),
    )
    assert payload["schema_version"] == REPORT_SCHEMA_VERSION
    assert payload["summary"]["total"] == 1
    assert payload["policy"]["status"] == "fail"
    assert payload["metadata"]["git_sha"] == "abc123"
    assert payload["metadata"]["branch"] is None
    assert payload["explanations"]["enabled"] is False
    assert "source" in payload
    assert "top_missed" in payload


def test_github_comment_has_details_and_collapsible() -> None:
    recs = [OptimizationRecord(kind="missed", pass_name="loop-vectorize", remark_name="M")]
    text = build_github_comment(
        recs,
        **_args(
            explanation=ExplanationInfo(
                enabled=True,
                backend="rule",
                label="Rule-based interpretation",
                items=[{"text": "hello"}],
            ),
            options=ReportBuildOptions(github_collapsible=True),
        ),
    )
    assert "<details>" in text
    assert "Rule-based interpretation" in text
    assert "hello" in text
    assert "source of truth" in text


def test_github_no_collapsible() -> None:
    recs = [OptimizationRecord(kind="missed", pass_name="inline", remark_name="X")]
    text = build_github_comment(
        recs,
        **_args(options=ReportBuildOptions(github_collapsible=False, top_missed=5)),
    )
    assert "<details>" not in text
    assert "#### 1." in text


def test_explanation_label_rule_vs_ai() -> None:
    recs = [OptimizationRecord(kind="missed", pass_name="inline", remark_name="X")]
    rule_text = build_markdown_report(
        recs,
        **_args(
            explanation=ExplanationInfo(
                enabled=True,
                backend="rule",
                label="Rule-based interpretation",
                items=[{"text": "hint"}],
            ),
        ),
    )
    assert "## Rule-based interpretation" in rule_text

    ai_text = build_markdown_report(
        recs,
        **_args(
            explanation=ExplanationInfo(
                enabled=True,
                backend="openai",
                label="AI-assisted interpretation",
                items=[{"text": "hint"}],
            ),
        ),
    )
    assert "## AI-assisted interpretation" in ai_text


def test_html_report_escapes_title_and_message() -> None:
    recs = [
        OptimizationRecord(
            kind="missed",
            pass_name="inline",
            remark_name="X",
            message="<script>alert(1)</script>",
            file="a.cpp",
            line=1,
        ),
    ]
    text = build_html_report(
        recs,
        **_args(options=ReportBuildOptions(title="Report <test>")),
    )
    assert "<!DOCTYPE html>" in text
    assert "Report &lt;test&gt;" in text
    assert "&lt;script&gt;" in text


def test_render_report_json_roundtrip() -> None:
    recs = [OptimizationRecord(kind="passed", pass_name="inline", remark_name="Inlined")]
    s = render_report("json", recs, **_args())
    data = json.loads(s)
    assert data["title"] == "Compiler Optimization Report"
    assert data["summary"]["total"] == 1
    assert data["schema_version"] == REPORT_SCHEMA_VERSION


def test_policy_threshold_structure() -> None:
    recs = [
        OptimizationRecord(kind="missed", pass_name="inline", remark_name="a"),
        OptimizationRecord(kind="missed", pass_name="inline", remark_name="b"),
    ]
    policy = build_policy_result(recs, max_missed_inline=1)
    assert policy is not None
    assert policy.status == "fail"
    assert policy.thresholds[0].name == "max_missed_inline"
    assert policy.thresholds[0].actual == 2
    assert policy.thresholds[0].limit == 1
