"""Pipeline trace: show how explncc layers process an input path."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from explncc import __version__
from explncc.evidence import build_evidence_packs
from explncc.normalizer import load_records_from_path
from explncc.parser import parse_opt_yaml_documents
from explncc.utils import collect_opt_yaml_paths


def _count_tags(docs: list[dict[str, Any]]) -> dict[str, int]:
    c: Counter[str] = Counter()
    for doc in docs:
        kind = doc.get("Kind")
        if isinstance(kind, str):
            c[kind.lower()] += 1
    return dict(c)


def build_trace(
    path: Path,
    *,
    include_evidence: bool = False,
    include_sample_record: bool = False,
    include_sample_evidence: bool = False,
) -> dict[str, Any]:
    paths = collect_opt_yaml_paths(path)
    raw_doc_count = 0
    tag_totals: Counter[str] = Counter()
    for yaml_path in paths:
        text = yaml_path.read_text(encoding="utf-8", errors="replace")
        docs = parse_opt_yaml_documents(text)
        raw_doc_count += len(docs)
        for k, v in _count_tags(docs).items():
            tag_totals[k] += v

    records = load_records_from_path(path)
    kinds = Counter(r.kind or "unknown" for r in records)
    passes = Counter(r.pass_name or "unknown" for r in records)
    with_location = sum(1 for r in records if r.file and r.line is not None)
    with_cost = sum(1 for r in records if r.cost)
    with_vf = sum(1 for r in records if r.vectorization_factor is not None)

    evidence_count = 0
    sample_evidence: dict[str, Any] | None = None
    if include_evidence and records:
        packs = build_evidence_packs(records)
        evidence_count = len(packs)
        if include_sample_evidence and packs:
            sample_evidence = packs[0].model_dump()

    sample_record: dict[str, Any] | None = None
    if include_sample_record and records:
        sample_record = records[0].model_dump()

    return {
        "explncc_version": __version__,
        "input": {
            "root": str(path.resolve()),
            "opt_yaml_files": [str(p) for p in paths],
            "file_count": len(paths),
        },
        "parser": {
            "raw_documents": raw_doc_count,
            "tags": dict(tag_totals),
        },
        "normalizer": {
            "records": len(records),
            "records_with_source_location": with_location,
            "records_with_cost_fields": with_cost,
            "records_with_vectorization_factor": with_vf,
            "by_kind": dict(kinds),
            "by_pass_top": dict(passes.most_common(12)),
        },
        "evidence": {
            "pack_count": evidence_count if include_evidence else None,
            "sample": sample_evidence,
        },
        "deterministic_stages": {
            "summary": "available",
            "stats": "available",
            "check": "available",
            "report": "available",
            "diff": "available",
            "report_diff": "available",
            "digest": "available",
            "evidence": "available",
        },
        "optional_stages": {
            "explain": "rule/ollama/openai/claude/auto",
        },
        "sample_record": sample_record,
    }


def render_trace_text(data: dict[str, Any]) -> str:
    inp = data["input"]
    parser = data["parser"]
    norm = data["normalizer"]
    lines = [
        "Input:",
        f"  {inp['root']}",
        f"  .opt.yaml files: {inp['file_count']}",
        "",
        "Parser:",
        f"  raw documents: {parser['raw_documents']}",
    ]
    if parser.get("tags"):
        tags = ", ".join(f"{k}={v}" for k, v in sorted(parser["tags"].items()))
        lines.append(f"  tags: {tags}")
    lines.extend(
        [
            "",
            "Normalizer:",
            f"  records: {norm['records']}",
            f"  records with source location: {norm['records_with_source_location']}",
            f"  records with cost fields: {norm['records_with_cost_fields']}",
            f"  records with vectorization factor: {norm['records_with_vectorization_factor']}",
            "",
            "Deterministic stages:",
        ],
    )
    for name, status in data["deterministic_stages"].items():
        lines.append(f"  {name}: {status}")
    lines.append("")
    lines.append("Optional stages:")
    for name, status in data["optional_stages"].items():
        lines.append(f"  {name}: {status}")
    ev = data.get("evidence") or {}
    if ev.get("pack_count") is not None:
        lines.append("")
        lines.append(f"Evidence packs: {ev['pack_count']}")
    return "\n".join(lines)


def render_trace_markdown(data: dict[str, Any]) -> str:
    text = render_trace_text(data)
    return f"# explncc pipeline trace\n\n```text\n{text}\n```\n"


def render_trace(fmt: str, data: dict[str, Any]) -> str:
    if fmt == "json":
        return json.dumps(data, indent=2, ensure_ascii=False, default=str)
    if fmt == "markdown":
        return render_trace_markdown(data)
    return render_trace_text(data)
