"""CI report builders (Markdown, JSON, GitHub)."""

from __future__ import annotations

import json

import pytest

from explncc.checks import CheckResult
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
    text = build_markdown_report(
        recs,
        top_missed=5,
        check_result=None,
        explain_text=None,
        title="T",
    )
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
    text = build_markdown_report(
        recs,
        top_missed=5,
        check_result=None,
        explain_text=None,
        title="T",
    )
    assert "# T" in text
    assert "Total remarks" in text
    assert "#### 1." in text
    assert "`inline`" in text
    assert "**Compiler message:**" in text
    assert "```text" in text
    assert "too costly" in text


def test_json_payload_check_block() -> None:
    recs = [OptimizationRecord(kind="missed", pass_name="p", remark_name="r")]
    cr = CheckResult(ok=False, violations=["bad"])
    payload = build_json_payload(
        recs,
        top_missed=5,
        check_result=cr,
        explain_text=None,
        title="T",
    )
    assert payload["check"]["ok"] is False
    assert "bad" in payload["check"]["violations"]


def test_github_comment_has_details() -> None:
    recs = [OptimizationRecord(kind="missed", pass_name="loop-vectorize", remark_name="M")]
    text = build_github_comment(
        recs,
        top_missed=5,
        check_result=CheckResult(ok=True, violations=[]),
        explain_text="hello",
        title="CI",
    )
    assert "<details>" in text
    assert "hello" in text
    assert "```text" in text or "_No message" in text


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
        top_missed=5,
        check_result=None,
        explain_text=None,
        title="Report <test>",
    )
    assert "<!DOCTYPE html>" in text
    assert "Report &lt;test&gt;" in text
    assert "&lt;script&gt;" in text


def test_render_report_json_roundtrip() -> None:
    recs = [OptimizationRecord(kind="passed", pass_name="inline", remark_name="Inlined")]
    s = render_report(
        "json",
        recs,
        top_missed=3,
        check_result=None,
        explain_text=None,
        title="X",
    )
    data = json.loads(s)
    assert data["title"] == "X"
    assert data["stats"]["total"] == 1
