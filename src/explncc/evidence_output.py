"""Serialize :class:`~explncc.evidence.EvidencePack` lists for CLI and files."""

from __future__ import annotations

import json
from collections.abc import Sequence

from explncc.context_snippets import format_source_snippet_markdown
from explncc.evidence import EvidencePack


def render_evidence_packs(packs: Sequence[EvidencePack], fmt: str) -> str:
    """Render packs as JSON array, JSON Lines, or Markdown."""

    fmt_l = fmt.strip().lower()
    if fmt_l == "json":
        data = [p.model_dump(mode="json") for p in packs]
        return json.dumps(data, indent=2, ensure_ascii=False)
    if fmt_l == "jsonl":
        lines = [json.dumps(p.model_dump(mode="json"), ensure_ascii=False) for p in packs]
        return "\n".join(lines) + ("\n" if lines else "")
    if fmt_l == "markdown":
        return _render_markdown(packs)
    msg = f"unknown evidence format: {fmt!r} (expected json, jsonl, markdown)"
    raise ValueError(msg)


def _indented_block(text: str | None) -> str:
    if not text:
        return "    _empty_\n"
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return "".join(f"    {line}\n" for line in lines)


def _render_markdown(packs: Sequence[EvidencePack]) -> str:
    parts: list[str] = [f"# Evidence packs ({len(packs)})\n"]
    for i, p in enumerate(packs):
        parts.append(f"\n## Pack {i + 1}\n\n")
        loc = p.debug_location
        loc_s = ""
        if loc.file:
            loc_s = loc.file
            if loc.line is not None:
                loc_s += f":{loc.line}"
                if loc.column is not None:
                    loc_s += f":{loc.column}"

        opt_log = f"`{p.optimization_log_path}`" if p.optimization_log_path else ""
        vf_s = str(p.vectorization_factor) if p.vectorization_factor is not None else ""
        lines_out = [
            ("pack_id", f"`{p.pack_id}`"),
            ("optimization_log_path", opt_log),
            ("source_file (DebugLoc)", f"`{p.source_file}`" if p.source_file else ""),
            ("function", f"`{p.function}`" if p.function else ""),
            ("debug_location", f"`{loc_s}`" if loc_s else ""),
            ("primary_pass", f"`{p.primary_pass}`" if p.primary_pass else ""),
            ("primary_kind", f"`{p.primary_kind}`" if p.primary_kind else ""),
            ("primary_remark", f"`{p.primary_remark}`" if p.primary_remark else ""),
            ("vectorization_factor", vf_s),
            ("unroll_factor", str(p.unroll_factor) if p.unroll_factor is not None else ""),
            ("scalar_cost", f"`{p.scalar_cost}`" if p.scalar_cost else ""),
            ("vector_cost", f"`{p.vector_cost}`" if p.vector_cost else ""),
            ("threshold", f"`{p.threshold}`" if p.threshold else ""),
            ("target_triple", f"`{p.target_triple}`" if p.target_triple else ""),
            ("cpu", f"`{p.cpu}`" if p.cpu else ""),
            ("march", f"`{p.march}`" if p.march else ""),
            ("has_source", str(p.has_source)),
            ("has_ir", str(p.has_ir)),
            ("has_cost", str(p.has_cost)),
            ("has_target", str(p.has_target)),
        ]
        for label, val in lines_out:
            if val:
                parts.append(f"- **{label}:** {val}\n")

        parts.append("\n**normalized_message:**\n\n")
        parts.append(_indented_block(p.normalized_message))

        if p.source_snippet:
            parts.append("\n**source_snippet:**\n\n")
            parts.append(format_source_snippet_markdown(p.source_snippet))

        if p.ir_snippet:
            parts.append("\n**ir_snippet:**\n\n")
            parts.append(_indented_block(p.ir_snippet))

        if p.missing_context:
            parts.append("\n**missing_context:**\n\n")
            for m in p.missing_context:
                parts.append(f"- `{m}`\n")

        if p.related_records:
            parts.append("\n**related_records:**\n\n")
            for rel in p.related_records:
                bits = [
                    rel.kind or "",
                    rel.pass_name or "",
                    rel.remark_name or "",
                ]
                head = " / ".join(x for x in bits if x) or "(remark)"
                parts.append(f"- **{head}**")
                if rel.file and rel.line is not None:
                    parts.append(f" @ `{rel.file}:{rel.line}`")
                parts.append("\n")
                if rel.normalized_message:
                    parts.append("\n")
                    parts.append(_indented_block(rel.normalized_message))
                    parts.append("\n")

    return "".join(parts).rstrip() + "\n"
