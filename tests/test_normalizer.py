"""Normalization of raw YAML documents."""

from __future__ import annotations

from pathlib import Path

from explncc.normalizer import load_records_from_path, normalize_document
from explncc.parser import parse_opt_yaml_documents

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "inline_miss_no_definition.opt.yaml"


def test_normalize_inline_miss_fields() -> None:
    text = FIXTURE.read_text(encoding="utf-8")
    docs = parse_opt_yaml_documents(text)
    first = docs[0]
    rec = normalize_document(first, source_path=FIXTURE)
    assert rec.kind == "missed"
    assert rec.pass_name == "inline"
    assert rec.remark_name == "NoDefinition"
    assert rec.function == "main"
    assert rec.callee == "_Z6calleei"
    assert rec.caller == "main"
    assert rec.message and "unavailable" in rec.message


def test_load_records_from_file() -> None:
    recs = load_records_from_path(FIXTURE)
    assert len(recs) >= 2
    assert any(r.kind == "missed" for r in recs)
