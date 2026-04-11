"""Stable digests over ``.opt.yaml`` inputs for CI cache keys and reproducibility."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from explncc.normalizer import load_records_from_path
from explncc.utils import collect_opt_yaml_paths


def build_digest(path: Path) -> dict[str, Any]:
    """SHA-256 over raw bytes per file plus aggregate key over the sorted file hashes."""

    paths = collect_opt_yaml_paths(path)
    files: list[dict[str, Any]] = []
    for yaml_path in paths:
        raw = yaml_path.read_bytes()
        file_hash = hashlib.sha256(raw).hexdigest()
        record_count = len(load_records_from_path(yaml_path))
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
    return {
        "root": str(path.resolve()),
        "files": files,
        "file_count": len(files),
        "total_records": total_records,
        "cache_key": cache_key,
    }


def format_digest_json(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False)
