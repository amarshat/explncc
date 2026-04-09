"""Path collection helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from explncc.utils import collect_opt_yaml_paths

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


def test_collect_single_file() -> None:
    p = FIXTURE_DIR / "inline_miss_no_definition.opt.yaml"
    assert collect_opt_yaml_paths(p) == [p.resolve()]


def test_collect_directory_recursive() -> None:
    paths = collect_opt_yaml_paths(FIXTURE_DIR)
    assert len(paths) >= 2


def test_reject_non_opt_yaml_file(tmp_path: Path) -> None:
    bad = tmp_path / "x.txt"
    bad.write_text("hello", encoding="utf-8")
    with pytest.raises(ValueError, match="not an optimization record"):
        collect_opt_yaml_paths(bad)
