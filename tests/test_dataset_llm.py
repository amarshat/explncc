"""Training / benchmark row builders."""

from __future__ import annotations

from pathlib import Path

from explncc.dataset_llm import build_bench_prompt_lines, build_training_rows, write_jsonl
from explncc.normalizer import load_records_from_path

FIXTURE_SIMD = Path(__file__).resolve().parent / "fixtures" / "simd_vectorized.opt.yaml"


def test_openai_messages_row_shape() -> None:
    recs = load_records_from_path(FIXTURE_SIMD)
    rows = build_training_rows(
        recs,
        template_id="minimal",
        export_format="openai-messages",
        use_teacher=True,
        teacher_placeholder="x",
        include_args_raw=False,
    )
    assert len(rows) == 1
    msg = rows[0]["messages"]
    assert len(msg) == 3
    assert {m["role"] for m in msg} == {"system", "user", "assistant"}


def test_explncc_record_has_metadata() -> None:
    recs = load_records_from_path(FIXTURE_SIMD)
    rows = build_training_rows(
        recs,
        template_id="guided",
        export_format="explncc-record",
        use_teacher=False,
        teacher_placeholder="[LABEL_ME]",
        include_args_raw=False,
    )
    assert rows[0]["metadata"]["template_id"] == "guided"
    assert rows[0]["metadata"]["teacher"] == "placeholder"
    assert rows[0]["messages"][2]["content"] == "[LABEL_ME]"


def test_bench_cross_product() -> None:
    recs = load_records_from_path(FIXTURE_SIMD)
    lines = build_bench_prompt_lines(
        records=recs,
        template_ids=["minimal", "rubric"],
        include_args_raw=False,
    )
    assert len(lines) == 2
    variants = {x["variant"] for x in lines}
    assert variants == {"minimal", "rubric"}


def test_write_jsonl_roundtrip(tmp_path: Path) -> None:
    recs = load_records_from_path(FIXTURE_SIMD)
    rows = build_training_rows(
        recs,
        template_id="minimal",
        export_format="openai-messages",
        use_teacher=True,
        teacher_placeholder="",
        include_args_raw=False,
    )
    path = tmp_path / "out.jsonl"
    write_jsonl(path, rows)
    text = path.read_text(encoding="utf-8")
    assert '"role": "system"' in text
