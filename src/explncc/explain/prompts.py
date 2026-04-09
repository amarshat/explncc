"""Structured prompts for optional HTTP model backends."""

from __future__ import annotations

SYSTEM_EXPLAIN = (
    "You help engineers interpret Clang/LLVM optimization remarks. "
    "You must not invent passes, functions, file paths, or line numbers. "
    "Ground every sentence in the JSON records and the rule-based summary. "
    "If information is missing, say so briefly. Prefer actionable guidance."
)


def user_message(*, rule_summary: str, records_json: str) -> str:
    return (
        "Rule-based summary (authoritative structure):\n"
        f"{rule_summary}\n\n"
        "Normalized records (subset, JSON):\n"
        f"{records_json}\n\n"
        "Write 2–5 short paragraphs: interpret the most important patterns, "
        "tie them to performance tradeoffs, and list concrete next steps "
        "(source changes, flags, or measurements). Do not repeat the JSON."
    )
