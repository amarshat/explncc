"""Named user-prompt templates for Chapter 11-style LLM experiments (alignment / SIMD).

Templates are plain strings with a single ``{compiler_json}`` placeholder. They are
deterministic: same inputs yield the same prompt text for benchmark sweeps.
"""

from __future__ import annotations

CH11_SYSTEM = (
    "You assist engineers interpreting Clang/LLVM optimization remarks relevant to "
    "SIMD (SSE/AVX) and memory access. Ground answers in the JSON remark only; "
    "if the remark does not mention alignment, say what is missing and what to "
    "measure next (e.g. assembly, IR, runtime checks)."
)

# User message bodies (role=user in chat fine-tuning).
CH11_USER_TEMPLATES: dict[str, str] = {
    "minimal": (
        "Here is one normalized Clang optimization remark as JSON.\n"
        "Does memory alignment plausibly matter for this case, and what should "
        "the developer verify next?\n\n"
        "{compiler_json}\n"
    ),
    "guided": (
        "Here is one normalized Clang optimization remark as JSON.\n"
        "Answer in short sections:\n"
        "(1) What the compiler claimed (pass + kind + remark name).\n"
        "(2) Whether SIMD is involved and the stated vectorization width if any.\n"
        "(3) Alignment: cite evidence from the remark text only; if absent, say so.\n"
        "(4) One concrete next step (source change, flag, or measurement).\n\n"
        "{compiler_json}\n"
    ),
    "rubric": (
        "Here is one normalized Clang optimization remark as JSON.\n"
        "Diagnose alignment/SIMD implications, then end with exactly one line:\n"
        "SCORES: alignment_evidence=0-5 actionability=0-5\n"
        "Use 0 when the remark gives no alignment signal.\n\n"
        "{compiler_json}\n"
    ),
}


def list_ch11_template_ids() -> list[str]:
    """Sorted template identifiers for ``bench-prompts`` and docs."""

    return sorted(CH11_USER_TEMPLATES.keys())


def render_ch11_user_prompt(template_id: str, compiler_json: str) -> str:
    """Fill ``{compiler_json}`` for a named Chapter 11 user template."""

    if template_id not in CH11_USER_TEMPLATES:
        unknown = f"unknown template_id: {template_id!r}"
        raise KeyError(unknown)
    return CH11_USER_TEMPLATES[template_id].format(compiler_json=compiler_json)
