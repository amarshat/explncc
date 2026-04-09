"""Export normalized records to JSON, JSONL, and CSV."""

from __future__ import annotations

import csv
import json
from io import StringIO
from pathlib import Path
from typing import Any

from explncc.models import OptimizationRecord

_JSON_FIELDS: tuple[str, ...] = (
    "kind",
    "pass_name",
    "remark_name",
    "function",
    "file",
    "line",
    "column",
    "caller",
    "callee",
    "reason",
    "message",
    "vectorization_factor",
    "unroll_factor",
    "cost",
    "threshold",
    "hotness",
    "args_raw",
    "source_path",
    "tool_version_metadata",
)


def record_to_json_dict(r: OptimizationRecord) -> dict[str, Any]:
    return r.model_dump(mode="json", exclude_none=False)


def export_json(records: list[OptimizationRecord], path: Path | None = None) -> str:
    payload = [record_to_json_dict(r) for r in records]
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    if path is not None:
        path.write_text(text, encoding="utf-8")
    return text


def export_jsonl(records: list[OptimizationRecord], path: Path | None = None) -> str:
    lines = [json.dumps(record_to_json_dict(r), ensure_ascii=False) for r in records]
    text = "\n".join(lines) + ("\n" if lines else "")
    if path is not None:
        path.write_text(text, encoding="utf-8")
    return text


def export_csv(records: list[OptimizationRecord], path: Path | None = None) -> str:
    buf = StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(_JSON_FIELDS), extrasaction="ignore")
    writer.writeheader()
    for r in records:
        row = r.model_dump(mode="json", exclude_none=False)
        flat: dict[str, Any] = {}
        for k in _JSON_FIELDS:
            v = row.get(k)
            if isinstance(v, (dict, list)):
                flat[k] = json.dumps(v, ensure_ascii=False)
            elif v is None:
                flat[k] = ""
            else:
                flat[k] = v
        writer.writerow(flat)
    text = buf.getvalue()
    if path is not None:
        path.write_text(text, encoding="utf-8")
    return text
