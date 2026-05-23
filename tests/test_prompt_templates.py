"""Chapter 11 prompt templates."""

from __future__ import annotations

import pytest

from explncc.prompt_templates import list_ch11_template_ids, render_ch11_user_prompt


def test_list_ids_sorted() -> None:
    ids = list_ch11_template_ids()
    assert ids == sorted(ids)
    assert "minimal" in ids
    assert "guided" in ids
    assert "adversarial" in ids
    assert "missing-context" in ids


def test_render_substitutes_json() -> None:
    text = render_ch11_user_prompt("minimal", '{"pass_name": "loop-vectorize"}')
    assert "loop-vectorize" in text
    assert "{compiler_json}" not in text


def test_unknown_template_raises() -> None:
    with pytest.raises(KeyError, match="unknown template_id"):
        render_ch11_user_prompt("nope", "{}")
