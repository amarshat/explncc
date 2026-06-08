"""Mermaid and HTML helpers for remark-centric visualizations (not LLVM IR graphs)."""

from __future__ import annotations

import hashlib
import html
import json
import re
from collections import Counter
from typing import Any, Literal

from explncc.models import OptimizationRecord

VizFormat = Literal["mermaid", "html", "json"]
VizStyle = Literal["pass-summary", "missed-top", "pass-remark"]


def _slug_key(prefix: str, key: str) -> str:
    """Stable Mermaid-safe node id (alphanumeric + underscore)."""

    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:10]
    base = re.sub(r"[^a-zA-Z0-9_]+", "_", key)[:32].strip("_")
    if not base:
        base = "n"
    return f"{prefix}_{base}_{digest}"


def _label_escape(text: str, max_len: int = 120) -> str:
    """Text inside Mermaid double-quoted labels (HTML-safe when embedded in pages)."""

    t = text.replace('"', "'").replace("\n", " ")
    t = t.replace("<", "‹").replace(">", "›").replace("&", "+")
    if len(t) > max_len:
        t = t[: max_len - 1] + "…"
    return t


def _html_safe_diagram_body(source: str) -> str:
    """Strip patterns that break HTML or script tags when pasted into a div."""

    return source.replace("</script", "").replace("<script", "")


def _pass_kind_maps(records: list[OptimizationRecord]) -> dict[str, dict[str, int]]:
    """pass_name -> kind -> count."""

    out: dict[str, dict[str, int]] = {}
    for r in records:
        p = r.pass_name or "?"
        k = r.kind or "unknown"
        bucket = out.setdefault(p, {})
        bucket[k] = bucket.get(k, 0) + 1
    return out


def build_pass_summary_mermaid(records: list[OptimizationRecord], *, top: int = 12) -> str:
    """Flowchart of top passes with missed/passed/analysis counts (remark density)."""

    pk = _pass_kind_maps(records)
    ranked = sorted(pk.items(), key=lambda x: sum(x[1].values()), reverse=True)[: max(top, 1)]
    lines = [
        "%% explncc: remark counts by LLVM pass name (not pass execution order)",
        "flowchart TD",
        '  subgraph passes["Top passes by remark count"]',
    ]
    if not ranked:
        lines.append('    empty["No remarks after filters"]')
    for pname, kinds in ranked:
        nid = _slug_key("P", pname)
        total = sum(kinds.values())
        parts = [f"total {total}"]
        for key in ("missed", "passed", "analysis"):
            if kinds.get(key):
                parts.append(f"{key}: {kinds[key]}")
        label = _label_escape(f"{pname}\\n" + ", ".join(parts))
        lines.append(f'    {nid}["{label}"]')
    lines.append("  end")
    return "\n".join(lines) + "\n"


def build_missed_top_mermaid(records: list[OptimizationRecord], *, top: int = 15) -> str:
    """Flowchart of top missed remarks (pass, remark, location hint)."""

    missed = [r for r in records if (r.kind or "").lower() == "missed"]
    lines = [
        "%% explncc: top missed optimization remarks",
        "flowchart LR",
        '  subgraph missed["Missed remarks"]',
    ]
    for i, r in enumerate(missed[: max(top, 1)], start=1):
        nid = _slug_key("M", f"{i}:{r.pass_name}:{r.remark_name}:{r.line}")
        loc = ""
        if r.file:
            loc = r.file
            if r.line is not None:
                loc += f":{r.line}"
        label = _label_escape(
            f"{r.pass_name or '?'} / {r.remark_name or '?'}\\n{r.function or '?'}\\n{loc}",
            max_len=160,
        )
        lines.append(f'    {nid}["{label}"]')
    if not missed:
        lines.append('    empty["No missed remarks in this slice"]')
    lines.append("  end")
    return "\n".join(lines) + "\n"


def build_pass_remark_mermaid(records: list[OptimizationRecord], *, top: int = 20) -> str:
    """Synthetic pass → remark edges from (Pass, Name) pair counts (DAG-like view for triage)."""

    ctr: Counter[tuple[str, str]] = Counter()
    for r in records:
        p = r.pass_name or "?"
        n = r.remark_name or "?"
        ctr[(p, n)] += 1
    pairs = ctr.most_common(max(top, 1))
    lines = [
        "%% explncc: top (pass, remark_name) pairs; edges are analytic, not LLVM pass order",
        "flowchart LR",
    ]
    for (pname, rname), cnt in pairs:
        pid = _slug_key("pass", pname)
        rid = _slug_key("rem", f"{pname}:{rname}")
        plab = _label_escape(f"{pname}\\n({cnt}×)")
        rlab = _label_escape(rname)
        lines.append(f'  {pid}["{plab}"] --> {rid}["{rlab}"]')
    if not pairs:
        lines.append('  empty["No remarks after filters"]')
    return "\n".join(lines) + "\n"


def build_mermaid_for_style(
    records: list[OptimizationRecord],
    style: VizStyle,
    *,
    top: int,
) -> str:
    if style == "pass-summary":
        return build_pass_summary_mermaid(records, top=top)
    if style == "missed-top":
        return build_missed_top_mermaid(records, top=top)
    return build_pass_remark_mermaid(records, top=top)


def build_viz_html(
    mermaid_source: str,
    *,
    title: str,
    explanation: str | None = None,
) -> str:
    """Self-contained page: Mermaid CDN + optional escaped explanation (merge AI / rule text)."""

    esc = html.escape
    body_explain = ""
    if explanation and explanation.strip():
        body_explain = f'<h2>Explanation</h2><pre class="explain">{esc(explanation.strip())}</pre>'
    safe_m = _html_safe_diagram_body(mermaid_source.strip())
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en"><head><meta charset="utf-8"/>'
        f"<title>{esc(title)}</title>\n"
        "<script "
        'src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>\n'
        "<style>body{font-family:system-ui,sans-serif;max-width:60rem;margin:1rem auto;}"
        "pre.explain{white-space:pre-wrap;background:#f6f8fa;padding:1rem;border-radius:6px}"
        ".mermaid{margin:1rem 0}</style>\n"
        "</head><body>\n"
        f"<h1>{esc(title)}</h1>\n"
        f"{body_explain}\n"
        "<h2>Diagram</h2>\n"
        f'<div class="mermaid">\n{safe_m}\n</div>\n'
        "<script>mermaid.initialize({startOnLoad:true,theme:'neutral'});</script>\n"
        "</body></html>\n"
    )


def build_viz_json(
    mermaid_source: str,
    *,
    title: str,
    style: str,
    top: int,
    record_count: int,
    explanation: str | None = None,
) -> str:
    """JSON bundle for custom dashboards (D3, React, opt-viewer overlays, etc.)."""

    payload: dict[str, Any] = {
        "title": title,
        "style": style,
        "top": top,
        "record_count": record_count,
        "mermaid": mermaid_source,
        "join_hints": (
            "Pair on (file, line) or function with clang -emit-llvm / opt-viewer; "
            "explncc does not ship IR."
        ),
    }
    if explanation is not None:
        payload["explanation"] = explanation
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def parse_viz_format(value: str) -> VizFormat:
    """Parse CLI ``--format`` for ``viz``."""

    v = value.strip().lower()
    if v == "mermaid":
        return "mermaid"
    if v == "html":
        return "html"
    if v == "json":
        return "json"
    msg = f"unknown viz format: {value!r}"
    raise ValueError(msg)


def parse_viz_style(value: str) -> VizStyle:
    """Parse CLI ``--style`` for ``viz``."""

    v = value.strip().lower()
    if v == "pass-summary":
        return "pass-summary"
    if v == "missed-top":
        return "missed-top"
    if v == "pass-remark":
        return "pass-remark"
    msg = f"unknown viz style: {value!r}"
    raise ValueError(msg)


def render_viz(
    fmt: VizFormat,
    records: list[OptimizationRecord],
    style: VizStyle,
    *,
    top: int,
    title: str,
    explanation: str | None = None,
) -> str:
    """Return mermaid source, standalone HTML, or JSON string."""

    m = build_mermaid_for_style(records, style, top=top)
    if fmt == "mermaid":
        head: list[str] = []
        if title.strip():
            head.append("%% " + _label_escape(title.strip(), max_len=200).replace("\n", " "))
        if explanation and explanation.strip():
            head.append(
                "%% " + _label_escape(explanation.strip(), max_len=500).replace("\n", " "),
            )
        if head:
            return "\n".join(head) + "\n" + m
        return m
    if fmt == "html":
        return build_viz_html(m, title=title, explanation=explanation)
    return build_viz_json(
        m,
        title=title,
        style=style,
        top=top,
        record_count=len(records),
        explanation=explanation,
    )
