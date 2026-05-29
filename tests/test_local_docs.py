"""Smoke tests for local-mode documentation."""

from __future__ import annotations

from pathlib import Path

from explncc.local.taxonomy import LABEL_IDS

DOCS = Path(__file__).resolve().parent.parent / "docs"


def test_local_docs_exist() -> None:
    for name in ("offline-first.md", "local-mode.md", "local-ranker.md", "classifier-labels.md"):
        assert (DOCS / name).is_file(), f"missing docs/{name}"


def test_classifier_labels_doc_covers_every_label() -> None:
    text = (DOCS / "classifier-labels.md").read_text(encoding="utf-8")
    for label_id in LABEL_IDS:
        assert f"`{label_id}`" in text, f"label {label_id} not documented"


def test_offline_first_states_core_principles() -> None:
    text = (DOCS / "offline-first.md").read_text(encoding="utf-8").lower()
    assert "offline by default" in text
    assert "--no-network" in text
    assert "authoritative" in text


def test_local_ranker_doc_explains_scoring() -> None:
    text = (DOCS / "local-ranker.md").read_text(encoding="utf-8").lower()
    assert "weighted" in text
    assert "severity" in text
    assert "score reasons" in text
    assert "onnx" in text
