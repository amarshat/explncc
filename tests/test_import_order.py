"""Low-level modules must be import-order-safe.

prompt_registry and config sit at the bottom of a prompt_registry -> explain ->
backends import chain. Importing either of them first used to crash with a
partially-initialized-module ImportError. These imports run each module as the
first explncc import in a fresh interpreter, which is the case the cycle broke.
"""

from __future__ import annotations

import subprocess
import sys

import pytest


@pytest.mark.parametrize(
    "stmt",
    [
        "from explncc.prompt_registry import list_prompt_template_ids; list_prompt_template_ids()",
        "import explncc.config; explncc.config.load_config()",
        "from explncc.explain.cache import explanation_cache_key",
    ],
)
def test_module_imports_first_without_cycle(stmt: str) -> None:
    result = subprocess.run(
        [sys.executable, "-c", stmt],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
