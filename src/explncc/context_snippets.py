"""Attach bounded source, LLVM IR, and assembly context around optimization remarks."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from explncc.models import OptimizationRecord

AssemblySignalCategory = Literal["aligned_form", "unaligned_form", "generic_vector_memory"]


class AssemblySignal(BaseModel):
    """Conservative hint from assembly mnemonic presence (not a bug diagnosis)."""

    mnemonic: str
    category: AssemblySignalCategory
    line: str


@dataclass(frozen=True)
class ContextSnippetRequest:
    """Options for optional filesystem-backed context attachment."""

    include_source: bool = False
    source_root: Path | None = None
    context_before: int = 5
    context_after: int = 8
    include_ir: bool = False
    ir_file: Path | None = None
    ir_lines: int = 50
    include_asm: bool = False
    asm_file: Path | None = None
    asm_lines: int = 60


@dataclass
class ContextSnippets:
    """Snippets gathered for one remark (absent fields stay None)."""

    source_snippet: str | None = None
    ir_snippet: str | None = None
    assembly_snippet: str | None = None
    assembly_signals: list[AssemblySignal] = field(default_factory=list)


_ASSEMBLY_MNEMONIC_CATEGORIES: dict[str, AssemblySignalCategory] = {
    "movaps": "aligned_form",
    "movapd": "aligned_form",
    "vmovaps": "aligned_form",
    "vmovapd": "aligned_form",
    "movups": "unaligned_form",
    "movupd": "unaligned_form",
    "vmovups": "unaligned_form",
    "vmovupd": "unaligned_form",
    "lddqu": "unaligned_form",
    "vmovdqu": "generic_vector_memory",
    "vmovdqa": "generic_vector_memory",
    "movdqu": "generic_vector_memory",
    "movdqa": "generic_vector_memory",
}

_MNEMONIC_RE = re.compile(
    r"\b(" + "|".join(re.escape(m) for m in _ASSEMBLY_MNEMONIC_CATEGORIES) + r")\b",
    re.IGNORECASE,
)


def resolve_source_path(debug_file: str | None, source_root: Path | None) -> Path | None:
    """Resolve DebugLoc file path against ``source_root`` without rewriting content."""

    if not debug_file or source_root is None:
        return None
    candidate = Path(debug_file)
    if candidate.is_absolute() and candidate.is_file():
        return candidate
    rooted = source_root / debug_file
    if rooted.is_file():
        return rooted
    by_name = source_root / candidate.name
    if by_name.is_file():
        return by_name
    return None


def extract_source_snippet(
    source_path: Path,
    line: int | None,
    *,
    context_before: int,
    context_after: int,
) -> str | None:
    """Return a contiguous source window; preserve line text exactly."""

    if line is None or line < 1:
        return None
    try:
        lines = source_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    if not lines:
        return None
    idx = line - 1
    start = max(0, idx - context_before)
    end = min(len(lines), idx + context_after + 1)
    if start >= len(lines):
        return None
    return "\n".join(lines[start:end])


def _find_ir_start(lines: list[str], function: str) -> int | None:
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("define ") and function in line:
            return i
    return None


def extract_ir_snippet(
    ir_path: Path,
    function: str | None,
    *,
    max_lines: int,
) -> str | None:
    """Locate a ``define`` for ``function`` and return a bounded IR slice."""

    if not function or max_lines < 1:
        return None
    try:
        lines = ir_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    start = _find_ir_start(lines, function)
    if start is None:
        return None
    end = min(len(lines), start + max_lines)
    return "\n".join(lines[start:end])


def _find_asm_start(lines: list[str], function: str) -> int | None:
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == f"{function}:" or stripped.startswith(f"{function}:"):
            return i
        if stripped.endswith(":") and stripped.rstrip(":") == function:
            return i
    return None


def extract_asm_snippet(
    asm_path: Path,
    function: str | None,
    *,
    max_lines: int,
) -> str | None:
    """Locate a function label and return a bounded assembly slice."""

    if not function or max_lines < 1:
        return None
    try:
        lines = asm_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    start = _find_asm_start(lines, function)
    if start is None:
        return None
    end = min(len(lines), start + max_lines)
    return "\n".join(lines[start:end])


def scan_assembly_signals(assembly_snippet: str | None) -> list[AssemblySignal]:
    """Detect common x86 SIMD load/store mnemonics in an assembly snippet."""

    if not assembly_snippet:
        return []
    seen: set[tuple[str, str]] = set()
    signals: list[AssemblySignal] = []
    for raw_line in assembly_snippet.splitlines():
        for match in _MNEMONIC_RE.finditer(raw_line):
            mnemonic = match.group(1).lower()
            category = _ASSEMBLY_MNEMONIC_CATEGORIES[mnemonic]
            key = (mnemonic, raw_line.strip())
            if key in seen:
                continue
            seen.add(key)
            signals.append(
                AssemblySignal(mnemonic=mnemonic, category=category, line=raw_line.strip()),
            )
    return signals


def assembly_signal_reasons(signals: list[AssemblySignal]) -> list[str]:
    """Conservative evidence reasons derived from assembly mnemonic presence."""

    reasons: list[str] = []
    for sig in signals:
        if sig.category == "unaligned_form":
            reasons.append(
                f"assembly snippet contains unaligned vector move mnemonic {sig.mnemonic}",
            )
        elif sig.category == "aligned_form":
            reasons.append(
                f"assembly snippet contains alignment-sensitive vector move mnemonic {sig.mnemonic}",
            )
        else:
            reasons.append(
                f"assembly snippet contains SIMD memory access mnemonic {sig.mnemonic}",
            )
    return reasons


def gather_context_snippets(
    record: OptimizationRecord,
    request: ContextSnippetRequest | None,
) -> ContextSnippets:
    """Gather optional source / IR / assembly snippets for one remark."""

    out = ContextSnippets()
    if request is None:
        return out

    if request.include_source and request.source_root is not None:
        src_path = resolve_source_path(record.file, request.source_root)
        if src_path is not None:
            out.source_snippet = extract_source_snippet(
                src_path,
                record.line,
                context_before=request.context_before,
                context_after=request.context_after,
            )

    if request.include_ir and request.ir_file is not None:
        out.ir_snippet = extract_ir_snippet(
            request.ir_file,
            record.function,
            max_lines=request.ir_lines,
        )

    if request.include_asm and request.asm_file is not None:
        out.assembly_snippet = extract_asm_snippet(
            request.asm_file,
            record.function,
            max_lines=request.asm_lines,
        )
        out.assembly_signals = scan_assembly_signals(out.assembly_snippet)

    return out


def format_source_snippet_markdown(text: str) -> str:
    """Render a source snippet with 1-based line numbers for Markdown output."""

    lines = text.splitlines()
    if not lines:
        return "    _empty_\n"
    width = len(str(len(lines)))
    return "".join(f"    {str(i + 1).rjust(width)} | {line}\n" for i, line in enumerate(lines))
