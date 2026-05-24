"""Stable digests over ``.opt.yaml`` inputs for CI cache keys and reproducibility."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from explncc import __version__
from explncc.evidence import build_evidence_packs
from explncc.prompt_registry import render_template_prompt
from explncc.record_identity import hash_payload
from explncc.records_loader import load_records
from explncc.utils import collect_opt_yaml_paths


def _aggregate_hash(parts: list[str]) -> str:
    if not parts:
        return ""
    combined = "".join(sorted(parts))
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


def build_digest(
    path: Path,
    *,
    include_evidence: bool = False,
    include_prompts: bool = False,
    template: str | None = None,
) -> dict[str, Any]:
    """SHA-256 over raw bytes, records, optional evidence and prompt hashes."""

    paths = collect_opt_yaml_paths(path)
    files: list[dict[str, Any]] = []
    record_hashes: list[str] = []
    for yaml_path in paths:
        raw = yaml_path.read_bytes()
        file_hash = hashlib.sha256(raw).hexdigest()
        recs = load_records(yaml_path)
        record_count = len(recs)
        for r in recs:
            if r.record_hash:
                record_hashes.append(r.record_hash)
        files.append(
            {
                "path": str(yaml_path),
                "sha256": file_hash,
                "record_count": record_count,
            },
        )
    combined = "".join(sorted(f["sha256"] for f in files))
    cache_key = hashlib.sha256(combined.encode("utf-8")).hexdigest() if files else ""
    total_records = sum(int(f["record_count"]) for f in files)
    records_aggregate_hash = _aggregate_hash(record_hashes)

    evidence_hashes: list[str] = []
    prompt_hashes: list[str] = []
    if include_evidence or include_prompts:
        all_records = load_records(path)
        if include_evidence and all_records:
            for pack in build_evidence_packs(all_records):
                if pack.evidence_hash:
                    evidence_hashes.append(pack.evidence_hash)
        if include_prompts and all_records and template:
            sample = json.dumps(
                [r.model_dump() for r in all_records[:1]],
                sort_keys=True,
                ensure_ascii=False,
                default=str,
            )
            prompt_text, _, _ = render_template_prompt(template, sample)
            prompt_hashes.append(hash_payload({"template": template, "prompt": prompt_text}))

    evidence_aggregate = _aggregate_hash(evidence_hashes)
    prompt_aggregate = _aggregate_hash(prompt_hashes)

    recommended_parts = [
        cache_key,
        records_aggregate_hash,
        evidence_aggregate if include_evidence else "",
        prompt_aggregate if include_prompts else "",
    ]
    recommended_cache_key = hashlib.sha256("|".join(recommended_parts).encode()).hexdigest()

    return {
        "explncc_version": __version__,
        "root": str(path.resolve()),
        "files": files,
        "file_count": len(files),
        "total_records": total_records,
        "cache_key": cache_key,
        "records_aggregate_hash": records_aggregate_hash,
        "evidence_aggregate_hash": evidence_aggregate if include_evidence else None,
        "prompt_hashes": prompt_hashes if include_prompts else None,
        "recommended_cache_key": recommended_cache_key,
        "note": "Digests hash compiler evidence (.opt.yaml), not binaries.",
    }


def format_digest_json(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False)
