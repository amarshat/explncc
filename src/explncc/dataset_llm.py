"""Build JSONL-style rows for LLM fine-tuning / instruction tuning experiments.

Rows can be strict OpenAI chat fine-tuning lines (``messages`` only) or extended
``explncc`` lines that add provenance metadata for reproducible papers and ablations.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from explncc.explain.rule_based import build_rule_explanation
from explncc.exporters import record_to_json_dict
from explncc.models import OptimizationRecord
from explncc.prompt_templates import CH11_SYSTEM, CH11_USER_TEMPLATES, render_ch11_user_prompt

ExportFormat = Literal["openai-messages", "explncc-record", "legacy-prompt-completion"]


def _sample_id(record: OptimizationRecord) -> str:
    payload = json.dumps(record.fingerprint(), sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def slim_compiler_json(record: OptimizationRecord, *, include_args_raw: bool) -> str:
    """Serialize a remark for prompts; optionally drop bulky ``args_raw``."""

    data = record_to_json_dict(record)
    if not include_args_raw:
        data.pop("args_raw", None)
    return json.dumps(data, ensure_ascii=False, indent=2)


def build_training_rows(
    records: list[OptimizationRecord],
    *,
    template_id: str,
    export_format: ExportFormat,
    use_teacher: bool,
    teacher_placeholder: str,
    include_args_raw: bool,
) -> list[dict[str, Any]]:
    """One training/example row per record (caller filters e.g. alignment slice)."""

    rows: list[dict[str, Any]] = []
    for record in records:
        compiler_json = slim_compiler_json(record, include_args_raw=include_args_raw)
        user_content = render_ch11_user_prompt(template_id, compiler_json)
        assistant = build_rule_explanation([record]) if use_teacher else teacher_placeholder

        if export_format == "legacy-prompt-completion":
            # Older fine-tuning APIs / some notebooks expect prompt/completion keys.
            prompt = f"System:\n{CH11_SYSTEM}\n\nUser:\n{user_content}"
            row: dict[str, Any] = {
                "prompt": prompt,
                "completion": assistant,
            }
        else:
            row = {
                "messages": [
                    {"role": "system", "content": CH11_SYSTEM},
                    {"role": "user", "content": user_content},
                    {"role": "assistant", "content": assistant},
                ],
            }

        if export_format == "explncc-record":
            row["metadata"] = {
                "sample_id": _sample_id(record),
                "template_id": template_id,
                "source_path": record.source_path,
                "pass_name": record.pass_name,
                "remark_kind": record.kind,
                "remark_name": record.remark_name,
                "function": record.function,
                "file": record.file,
                "line": record.line,
                "teacher": "rule_based" if use_teacher else "placeholder",
            }

        rows.append(row)
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def build_bench_prompt_lines(
    records: list[OptimizationRecord],
    *,
    template_ids: list[str] | None,
    include_args_raw: bool,
) -> list[dict[str, Any]]:
    """Cross-product of records × templates for external model evaluation."""

    ids = template_ids if template_ids is not None else sorted(CH11_USER_TEMPLATES.keys())
    lines: list[dict[str, Any]] = []
    for record in records:
        sid = _sample_id(record)
        compiler_json = slim_compiler_json(record, include_args_raw=include_args_raw)
        for tid in ids:
            user_content = render_ch11_user_prompt(tid, compiler_json)
            lines.append(
                {
                    "sample_id": sid,
                    "variant": tid,
                    "system": CH11_SYSTEM,
                    "user": user_content,
                },
            )
    return lines
