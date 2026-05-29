"""Serialize :class:`~explncc.alignment_pack.AlignmentEvidencePack` lists for CLI and files."""

from __future__ import annotations

import json
from collections.abc import Sequence

from explncc.alignment_pack import AlignmentEvidencePack
from explncc.context_snippets import format_source_snippet_markdown


def render_alignment_evidence_packs(packs: Sequence[AlignmentEvidencePack], fmt: str) -> str:
    """Render alignment evidence packs as JSON array, JSON Lines, or Markdown."""

    fmt_l = fmt.strip().lower()
    if fmt_l == "json":
        data = [p.model_dump(mode="json") for p in packs]
        return json.dumps(data, indent=2, ensure_ascii=False)
    if fmt_l == "jsonl":
        lines = [json.dumps(p.model_dump(mode="json"), ensure_ascii=False) for p in packs]
        return "\n".join(lines) + ("\n" if lines else "")
    if fmt_l == "markdown":
        return _render_markdown(packs)
    msg = f"unknown alignment pack format: {fmt!r} (expected json, jsonl, markdown)"
    raise ValueError(msg)


def _indented_block(text: str | None) -> str:
    if not text:
        return "    _empty_\n"
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return "".join(f"    {line}\n" for line in lines)


def _render_markdown(packs: Sequence[AlignmentEvidencePack]) -> str:
    parts: list[str] = [f"# Alignment evidence packs ({len(packs)})\n"]
    for i, p in enumerate(packs):
        parts.append(f"\n## Pack {i + 1}\n\n")
        loc = ""
        if p.file:
            loc = p.file
            if p.line is not None:
                loc += f":{p.line}"
                if p.column is not None:
                    loc += f":{p.column}"

        vf_s = str(p.vectorization_factor) if p.vectorization_factor is not None else ""
        ic_s = str(p.interleave_count) if p.interleave_count is not None else ""
        lines_out = [
            ("pack_id", f"`{p.pack_id}`"),
            ("source_record_id", f"`{p.source_record_id}`"),
            ("raw_record_ref", f"`{p.raw_record_ref}`" if p.raw_record_ref else ""),
            ("raw_record_hash", f"`{p.raw_record_hash}`"),
            ("function", f"`{p.function}`" if p.function else ""),
            ("location", f"`{loc}`" if loc else ""),
            ("pass_name", f"`{p.pass_name}`" if p.pass_name else ""),
            ("kind", f"`{p.kind}`" if p.kind else ""),
            ("remark_name", f"`{p.remark_name}`" if p.remark_name else ""),
            ("vectorization_factor", vf_s),
            ("interleave_count", ic_s),
            ("scalar_cost", f"`{p.scalar_cost}`" if p.scalar_cost else ""),
            ("vector_cost", f"`{p.vector_cost}`" if p.vector_cost else ""),
            ("target_triple", f"`{p.target_triple}`" if p.target_triple else ""),
            ("cpu", f"`{p.cpu}`" if p.cpu else ""),
            ("march", f"`{p.march}`" if p.march else ""),
            ("alignment_label", f"`{p.alignment_label}`"),
            ("alignment_confidence", f"`{p.alignment_confidence}`"),
        ]
        for label, val in lines_out:
            if val:
                parts.append(f"- **{label}:** {val}\n")

        parts.append("\n**message:**\n\n")
        parts.append(_indented_block(p.message))

        if p.evidence_reasons:
            parts.append("\n**evidence_reasons:**\n\n")
            for reason in p.evidence_reasons:
                parts.append(f"- {reason}\n")

        if p.recommended_next_steps:
            parts.append("\n**recommended_next_steps:**\n\n")
            for step in p.recommended_next_steps:
                parts.append(f"- {step}\n")

        if p.source_snippet:
            parts.append("\n**source_snippet:**\n\n")
            parts.append(format_source_snippet_markdown(p.source_snippet))

        if p.ir_snippet:
            parts.append("\n**ir_snippet:**\n\n")
            parts.append(_indented_block(p.ir_snippet))

        if p.assembly_snippet:
            parts.append("\n**assembly_snippet:**\n\n")
            parts.append(_indented_block(p.assembly_snippet))

        if p.assembly_signals:
            parts.append("\n**assembly_signals:**\n\n")
            for sig in p.assembly_signals:
                parts.append(
                    f"- `{sig.mnemonic}` ({sig.category}) — `{sig.line}`\n",
                )

        if p.missing_context:
            parts.append("\n**missing_context:**\n\n")
            for m in p.missing_context:
                parts.append(f"- `{m}`\n")

    return "".join(parts).rstrip() + "\n"
