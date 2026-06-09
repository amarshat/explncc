"""Plain-text rendering for ``explncc why`` findings.

Output is deterministic and pipe-safe: plain lines, stable ordering, optional
ANSI color on the verdict tag only (and only when the caller asks for it).
The source snippet quotes the file exactly, with a caret under the column the
compiler reported for the cause.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import typer

from explncc.context_snippets import resolve_source_path
from explncc.fusion import FusedFinding

_WRAP_WIDTH = 88

_VERDICT_TAGS = {
    "vectorize-missed": "MISS",
    "hls-missed": "MISS",
    "inline-missed": "MISS",
    "slp-missed": "MISS",
    "other-missed": "MISS",
    "spills": "NOTE",
    "analysis": "NOTE",
    "passed": "OK",
}

_TAG_COLORS = {
    "MISS": typer.colors.RED,
    "NOTE": typer.colors.YELLOW,
    "OK": typer.colors.GREEN,
}


def verdict_tag(finding: FusedFinding) -> str:
    return _VERDICT_TAGS.get(finding.category, "NOTE")


def _styled_tag(tag: str, use_color: bool) -> str:
    if not use_color:
        return tag
    return typer.style(tag, fg=_TAG_COLORS.get(tag), bold=True)


def _source_lines(
    finding: FusedFinding,
    source_root: Path | None,
) -> list[str]:
    """Snippet lines with a caret under the compiler-reported column."""

    if finding.line is None:
        return []
    path = resolve_source_path(finding.file, source_root)
    if path is None:
        return []
    try:
        all_lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    if finding.line > len(all_lines):
        return []
    start = max(1, finding.line - 1)
    width = len(str(finding.line))
    out: list[str] = []
    for lineno in range(start, finding.line + 1):
        text = all_lines[lineno - 1].replace("\t", " ")
        if lineno != finding.line and not text.strip():
            continue
        out.append(f"   {str(lineno).rjust(width)} | {text}")
    col = finding.caret_column or finding.column
    # A column of 1 is the compiler pointing at "the whole line"; a caret there
    # adds nothing.
    if col is not None and col > 1:
        out.append(f"   {' ' * width} | {' ' * (col - 1)}^")
    return out


def _wrapped_field(label: str, text: str) -> list[str]:
    """``label: text`` with a hanging indent under the text column."""

    prefix = f"  {label} "
    body = textwrap.wrap(
        text,
        width=_WRAP_WIDTH,
        initial_indent=prefix,
        subsequent_indent=" " * len(prefix),
        break_long_words=False,
        break_on_hyphens=False,
    )
    return body if body else [prefix.rstrip()]


def render_finding(
    finding: FusedFinding,
    *,
    source_root: Path | None = None,
    use_color: bool = False,
) -> list[str]:
    lines: list[str] = []
    fn = finding.function_display or finding.function or "<unknown function>"
    lines.append(f"{finding.location()}  {fn}")
    tag = _styled_tag(verdict_tag(finding), use_color)
    extra = f", {finding.count} records" if finding.count > 1 else ""
    lines.append(f"  {tag}  {finding.headline}  [{finding.pass_name or '?'}{extra}]")
    snippet = _source_lines(finding, source_root)
    lines.extend(snippet)
    if finding.cause and finding.cause.lower() != finding.headline.lower():
        lines.extend(_wrapped_field("compiler:", finding.cause))
    if finding.suggestion:
        lines.extend(_wrapped_field("suggest: ", finding.suggestion))
    return lines


def render_findings(
    findings: list[FusedFinding],
    *,
    shown: int,
    total_records: int,
    source_root: Path | None = None,
    use_color: bool = False,
    noise_hidden: bool = True,
) -> str:
    header_bits = [
        f"{len(findings)} finding{'s' if len(findings) != 1 else ''}",
        f"{total_records} records",
    ]
    if noise_hidden:
        header_bits.append("noise hidden; --all to show")
    out: list[str] = [f"explncc why: {', '.join(header_bits)}", ""]
    for finding in findings[:shown]:
        out.extend(render_finding(finding, source_root=source_root, use_color=use_color))
        out.append("")
    if shown < len(findings):
        out.append(
            f"... {len(findings) - shown} more finding(s); use --top 0 to show everything",
        )
    while out and out[-1] == "":
        out.pop()
    return "\n".join(out)
