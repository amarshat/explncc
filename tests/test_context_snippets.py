"""Tests for source / IR / assembly snippet attachment."""

from __future__ import annotations

from pathlib import Path

from explncc.context_snippets import (
    ContextSnippetRequest,
    assembly_signal_reasons,
    extract_asm_snippet,
    extract_ir_snippet,
    extract_source_snippet,
    gather_context_snippets,
    resolve_source_path,
    scan_assembly_signals,
)
from explncc.models import OptimizationRecord
from explncc.normalizer import load_records_from_path

FIXTURES = Path(__file__).resolve().parent / "fixtures"
FIXTURE_SIMD = FIXTURES / "simd_vectorized.opt.yaml"
T_CPP = FIXTURES / "t.cpp"
T_LL = FIXTURES / "t.ll"
T_S = FIXTURES / "t.s"


def test_resolve_source_path_by_name() -> None:
    path = resolve_source_path("t.cpp", FIXTURES)
    assert path == T_CPP


def test_extract_source_snippet_window() -> None:
    snippet = extract_source_snippet(T_CPP, 2, context_before=1, context_after=2)
    assert snippet is not None
    assert "void foo()" in snippet
    assert "for (int i = 0" in snippet


def test_extract_ir_snippet_finds_function() -> None:
    snippet = extract_ir_snippet(T_LL, "_Z3foov", max_lines=20)
    assert snippet is not None
    assert "define dso_local void @_Z3foov" in snippet
    assert "for.body" in snippet


def test_extract_ir_snippet_missing_function() -> None:
    assert extract_ir_snippet(T_LL, "_Z9missingv", max_lines=20) is None


def test_extract_asm_snippet_finds_label() -> None:
    snippet = extract_asm_snippet(T_S, "_Z3foov", max_lines=20)
    assert snippet is not None
    assert "_Z3foov:" in snippet
    assert "vmovups" in snippet


def test_scan_assembly_signals_categories() -> None:
    asm = extract_asm_snippet(T_S, "_Z3foov", max_lines=20)
    signals = scan_assembly_signals(asm)
    mnemonics = {s.mnemonic for s in signals}
    assert "vmovups" in mnemonics
    assert "movaps" in mnemonics
    unaligned = next(s for s in signals if s.mnemonic == "vmovups")
    assert unaligned.category == "unaligned_form"
    reasons = assembly_signal_reasons(signals)
    assert any("vmovups" in r for r in reasons)
    assert any("unaligned" in r for r in reasons)


def test_gather_context_snippets_for_simd_fixture() -> None:
    records = load_records_from_path(FIXTURE_SIMD)
    rec = records[0]
    request = ContextSnippetRequest(
        include_source=True,
        source_root=FIXTURES,
        context_before=2,
        context_after=3,
        include_ir=True,
        ir_file=T_LL,
        ir_lines=30,
        include_asm=True,
        asm_file=T_S,
        asm_lines=30,
    )
    snippets = gather_context_snippets(rec, request)
    assert snippets.source_snippet is not None
    assert snippets.ir_snippet is not None
    assert snippets.assembly_snippet is not None
    assert snippets.assembly_signals


def test_missing_source_keeps_none() -> None:
    rec = OptimizationRecord(
        kind="passed",
        pass_name="loop-vectorize",
        remark_name="Vectorized",
        file="missing.cpp",
        line=1,
    )
    request = ContextSnippetRequest(include_source=True, source_root=FIXTURES)
    snippets = gather_context_snippets(rec, request)
    assert snippets.source_snippet is None
