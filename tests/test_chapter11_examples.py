"""Chapter 11 alignment example fixtures — expected labels and CLI smoke."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from explncc.alignment import classify_alignment
from explncc.cli import app
from explncc.normalizer import load_records_from_path

RUNNER = CliRunner()
ROOT = Path(__file__).resolve().parents[1] / "examples" / "chapter11_alignment"

CHAPTER11_CASES: tuple[tuple[str, str], ...] = (
    ("vectorized_no_alignment_claim", "alignment_plausible_not_proven"),
    ("aliasing_not_alignment", "alignment_unlikely_from_evidence"),
    ("cost_not_alignment", "alignment_unlikely_from_evidence"),
    ("aligned_intrinsic", "alignment_explicit"),
    ("unaligned_intrinsic", "alignment_explicit"),
    ("offset_pointer_plausible", "alignment_plausible_not_proven"),
)


@pytest.mark.parametrize(("example_dir", "expected_label"), CHAPTER11_CASES)
def test_fixture_expected_alignment_label(example_dir: str, expected_label: str) -> None:
    fixture = ROOT / example_dir / "fixtures" / "main.opt.yaml"
    assert fixture.is_file(), f"missing fixture: {fixture}"
    records = load_records_from_path(fixture)
    assert len(records) >= 1
    label = classify_alignment(records[0]).alignment_label
    assert label == expected_label


@pytest.mark.parametrize(("example_dir", "expected_label"), CHAPTER11_CASES)
def test_each_example_has_readme_and_source(example_dir: str, expected_label: str) -> None:
    base = ROOT / example_dir
    assert (base / "README.md").is_file()
    assert (base / "main.cpp").is_file()
    readme = (base / "README.md").read_text(encoding="utf-8")
    assert expected_label in readme


def test_alignment_on_all_chapter11_fixtures() -> None:
    result = RUNNER.invoke(app, ["alignment", str(ROOT), "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert len(data) == len(CHAPTER11_CASES)
    labels = {row["alignment_label"] for row in data}
    assert "alignment_explicit" in labels
    assert "alignment_plausible_not_proven" in labels
    assert "alignment_unlikely_from_evidence" in labels


def test_alignment_pack_on_aliasing_fixture_with_source() -> None:
    fixture = ROOT / "aliasing_not_alignment" / "fixtures" / "main.opt.yaml"
    source_root = ROOT / "aliasing_not_alignment"
    result = RUNNER.invoke(
        app,
        [
            "alignment-pack",
            str(fixture),
            "--include-source",
            "--source-root",
            str(source_root),
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data[0]["alignment_label"] == "alignment_unlikely_from_evidence"
    assert data[0]["source_snippet"] is not None
    assert "cannot prove memory independence" in data[0]["message"]
