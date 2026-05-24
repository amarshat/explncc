"""Versioned prompt template metadata for reproducible explanation caching."""

from __future__ import annotations

import hashlib

from dataclasses import dataclass

from explncc.explain import prompts
from explncc.prompt_templates import CH11_SYSTEM, CH11_USER_TEMPLATES, render_ch11_user_prompt


@dataclass(frozen=True)
class PromptTemplateSpec:
    template_id: str
    template_version: str
    description: str
    required_fields: tuple[str, ...]
    optional_fields: tuple[str, ...]
    grounding_constraints: str


EXPLAIN_DEFAULT = PromptTemplateSpec(
    template_id="explain-default",
    template_version="1.0",
    description="Default optimization remark explanation (rule summary + record JSON).",
    required_fields=("rule_summary", "records_json"),
    optional_fields=(),
    grounding_constraints=(
        "Ground answers in supplied compiler JSON only; do not invent passes or costs."
    ),
)

_BUILTIN_SPECS: dict[str, PromptTemplateSpec] = {
    "explain-default": EXPLAIN_DEFAULT,
}


def _register_ch11_templates() -> None:
    for tid in CH11_USER_TEMPLATES:
        _BUILTIN_SPECS[tid] = PromptTemplateSpec(
            template_id=tid,
            template_version="1.0",
            description=f"Chapter 11 alignment user prompt ({tid}).",
            required_fields=("compiler_json",),
            optional_fields=(),
            grounding_constraints=(
                "Ground alignment claims in the compiler JSON; list missing evidence when absent."
            ),
        )


_register_ch11_templates()


def list_prompt_template_ids() -> list[str]:
    return sorted(_BUILTIN_SPECS.keys())


def get_prompt_template(template_id: str) -> PromptTemplateSpec:
    if template_id not in _BUILTIN_SPECS:
        msg = f"unknown template_id: {template_id!r}"
        raise KeyError(msg)
    return _BUILTIN_SPECS[template_id]


def hash_prompt_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def render_explain_prompt(*, rule_summary: str, records_json: str) -> tuple[str, str, str]:
    """Return (prompt_text, template_id, template_version)."""

    user = prompts.user_message(rule_summary=rule_summary, records_json=records_json)
    full = f"{prompts.SYSTEM_EXPLAIN}\n\n{user}"
    return full, EXPLAIN_DEFAULT.template_id, EXPLAIN_DEFAULT.template_version


def render_template_prompt(template_id: str, compiler_json: str) -> tuple[str, str, str]:
    if template_id == "explain-default":
        msg = f"use render_explain_prompt for {template_id!r}"
        raise ValueError(msg)
    spec = get_prompt_template(template_id)
    body = render_ch11_user_prompt(template_id, compiler_json)
    full = f"{CH11_SYSTEM}\n\n{body}"
    return full, spec.template_id, spec.template_version


def prompt_render_metadata(prompt_text: str, template_id: str) -> dict[str, str]:
    spec = get_prompt_template(template_id)
    return {
        "template_id": spec.template_id,
        "template_version": spec.template_version,
        "prompt_hash": hash_prompt_text(prompt_text),
    }
