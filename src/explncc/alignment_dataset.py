"""Build alignment-focused dataset rows with labels and conservative teachers."""

from __future__ import annotations

import json
from typing import Any, Literal

from explncc.alignment import alignment_signals, classify_alignment
from explncc.alignment_teacher import build_conservative_teacher, build_expected_behavior
from explncc.context_snippets import ContextSnippetRequest, ContextSnippets, gather_context_snippets
from explncc.dataset_llm import _sample_id, slim_compiler_json
from explncc.models import OptimizationRecord
from explncc.prompt_templates import CH11_SYSTEM, render_ch11_user_prompt

AlignmentExportFormat = Literal[
    "openai-messages",
    "explncc-record",
    "legacy-prompt-completion",
    "plain-prompt-completion",
    "chatml",
]

ALIGNMENT_EXPORT_FORMATS: frozenset[str] = frozenset(
    {
        "openai-messages",
        "explncc-record",
        "legacy-prompt-completion",
        "plain-prompt-completion",
        "chatml",
    },
)


def _context_object(snippet: str | None) -> dict[str, Any]:
    return {
        "snippet": snippet,
        "present": snippet is not None,
    }


def _assembly_context_object(snippets: ContextSnippets) -> dict[str, Any]:
    return {
        "snippet": snippets.assembly_snippet,
        "present": snippets.assembly_snippet is not None,
        "assembly_signals": [s.model_dump() for s in snippets.assembly_signals],
    }


def build_evidence_object(
    record: OptimizationRecord,
    *,
    include_args_raw: bool,
) -> dict[str, Any]:
    """Structured compiler evidence for dataset rows."""

    classification = classify_alignment(record)
    data = json.loads(slim_compiler_json(record, include_args_raw=include_args_raw))
    return {
        "compiler_remark": data,
        "pass_name": record.pass_name,
        "kind": record.kind,
        "remark_name": record.remark_name,
        "message": record.message,
        "function": record.function,
        "file": record.file,
        "line": record.line,
        "column": record.column,
        "vectorization_factor": record.vectorization_factor,
        "alignment_signals": alignment_signals(record),
        "alignment_label": classification.alignment_label,
        "alignment_confidence": classification.alignment_confidence,
        "evidence_reasons": list(classification.evidence_reasons),
        "missing_context": list(classification.missing_context),
        "recommended_next_steps": list(classification.recommended_next_steps),
    }


def _task_block(template_id: str) -> str:
    return (
        f"Task: interpret alignment/SIMD evidence using template={template_id!r}. "
        "Ground claims in supplied evidence only."
    )


def _constraints_block() -> str:
    return (
        "Constraints: do not invent target triple, vector width, or alignment root cause; "
        "treat heuristic labels as non-oracle; list missing context when absent."
    )


def _format_chatml(system: str, user: str, assistant: str) -> str:
    parts = [
        f"<|im_start|>system\n{system}\n",
        f"<|im_start|>user\n{user}\n",
        f"<|im_start|>assistant\n{assistant}\n",
    ]
    return "".join(parts)


def build_alignment_training_rows(
    records: list[OptimizationRecord],
    *,
    template_id: str,
    export_format: AlignmentExportFormat,
    use_teacher: bool,
    teacher_placeholder: str,
    include_args_raw: bool,
    context: ContextSnippetRequest | None = None,
) -> list[dict[str, Any]]:
    """Build alignment dataset rows with labels, context slots, and conservative teachers."""

    rows: list[dict[str, Any]] = []
    for record in records:
        classification = classify_alignment(record)
        snippets = gather_context_snippets(record, context)
        evidence = build_evidence_object(record, include_args_raw=include_args_raw)
        missing = list(classification.missing_context)
        if snippets.source_snippet is not None and "source_snippet" in missing:
            missing.remove("source_snippet")
        if snippets.ir_snippet is not None and "ir_snippet" in missing:
            missing.remove("ir_snippet")
        if snippets.assembly_snippet is not None and "assembly_snippet" in missing:
            missing.remove("assembly_snippet")

        compiler_json = json.dumps(evidence["compiler_remark"], ensure_ascii=False, indent=2)
        user_content = render_ch11_user_prompt(template_id, compiler_json)
        teacher = (
            build_conservative_teacher(record, classification)
            if use_teacher
            else teacher_placeholder
        )
        expected = build_expected_behavior(classification)
        sid = _sample_id(record)

        core: dict[str, Any] = {
            "sample_id": sid,
            "evidence": evidence,
            "source_context": _context_object(snippets.source_snippet),
            "ir_context": _context_object(snippets.ir_snippet),
            "assembly_context": _assembly_context_object(snippets),
            "alignment_label": classification.alignment_label,
            "alignment_confidence": classification.alignment_confidence,
            "evidence_reasons": list(classification.evidence_reasons),
            "missing_context": missing,
            "teacher_response": teacher,
            "expected_behavior": expected,
            "task": _task_block(template_id),
            "constraints": _constraints_block(),
        }

        if export_format == "plain-prompt-completion":
            prompt = (
                f"{_task_block(template_id)}\n{_constraints_block()}\n\n"
                f"Evidence JSON:\n{compiler_json}\n\nUser:\n{user_content}"
            )
            row = {**core, "prompt": prompt, "completion": teacher}
        elif export_format == "legacy-prompt-completion":
            prompt = f"System:\n{CH11_SYSTEM}\n\nUser:\n{user_content}"
            row = {**core, "prompt": prompt, "completion": teacher}
        elif export_format == "chatml":
            row = {
                **core,
                "text": _format_chatml(CH11_SYSTEM, user_content, teacher),
            }
        elif export_format == "openai-messages":
            row = {
                **core,
                "messages": [
                    {"role": "system", "content": CH11_SYSTEM},
                    {"role": "user", "content": user_content},
                    {"role": "assistant", "content": teacher},
                ],
            }
        else:  # explncc-record
            row = {
                **core,
                "messages": [
                    {"role": "system", "content": CH11_SYSTEM},
                    {"role": "user", "content": user_content},
                    {"role": "assistant", "content": teacher},
                ],
                "metadata": {
                    "sample_id": sid,
                    "template_id": template_id,
                    "source_path": record.source_path,
                    "pass_name": record.pass_name,
                    "remark_kind": record.kind,
                    "remark_name": record.remark_name,
                    "function": record.function,
                    "file": record.file,
                    "line": record.line,
                    "teacher": "alignment_conservative_rule" if use_teacher else "placeholder",
                    "alignment_label": classification.alignment_label,
                },
            }
        rows.append(row)
    return rows
