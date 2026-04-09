"""Export formats."""

from __future__ import annotations

import csv
import json
from io import StringIO
from pathlib import Path

from explncc.exporters import export_csv, export_json, export_jsonl
from explncc.normalizer import load_records_from_path

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "inline_miss_no_definition.opt.yaml"


def test_export_json_roundtrip() -> None:
    recs = load_records_from_path(FIXTURE)
    text = export_json(recs)
    data = json.loads(text)
    assert isinstance(data, list)
    assert data[0]["pass_name"] == "inline"


def test_export_jsonl_lines() -> None:
    recs = load_records_from_path(FIXTURE)
    text = export_jsonl(recs)
    lines = [ln for ln in text.splitlines() if ln.strip()]
    assert len(lines) == len(recs)
    assert json.loads(lines[0])["kind"] == "missed"


def test_export_csv_headers() -> None:
    recs = load_records_from_path(FIXTURE)
    text = export_csv(recs)
    reader = csv.reader(StringIO(text))
    header = next(reader)
    assert "pass_name" in header
    assert "message" in header
