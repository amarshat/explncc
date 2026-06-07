"""Map raw Clang YAML documents to :class:`OptimizationRecord`."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from explncc.models import OptimizationRecord

_INT_RE = re.compile(r"^-?\d+$")


def _coerce_int(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and _INT_RE.match(value):
        return int(value)
    return None


def _debug_loc(doc: dict[str, Any]) -> tuple[str | None, int | None, int | None]:
    loc = doc.get("DebugLoc")
    if not isinstance(loc, dict):
        return None, None, None
    file_val = loc.get("File")
    file_s = str(file_val) if file_val is not None else None
    line_i = _coerce_int(loc.get("Line"))
    col_i = _coerce_int(loc.get("Column"))
    return file_s, line_i, col_i


def _scalar_to_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def _walk_args(
    args: Any,
    strings: list[str],
    pairs: dict[str, str],
) -> tuple[str | None, str | None]:
    """Render the message stream, callee/caller names, and typed keys from Args.

    LLVM emits ``Args`` as an ordered list where ``String`` fragments and typed
    values (``Callee``, ``Caller``, ``VectorizationFactor``, ``Cost``, ...)
    interleave to form the human-readable remark. Append every primary value in
    order so the rendered message matches what the compiler prints (for example
    ``vectorized loop (vectorization width: 4)`` rather than dropping the ``4``).
    ``DebugLoc`` is positional metadata and is skipped.
    """

    caller: str | None = None
    callee: str | None = None

    def visit(node: Any) -> None:
        nonlocal caller, callee
        if isinstance(node, dict):
            for key, val in node.items():
                if key == "DebugLoc":
                    continue
                if isinstance(val, (dict, list)):
                    visit(val)
                    continue
                sval = _scalar_to_str(val)
                sval = sval if sval is not None else ""
                strings.append(sval)
                if key == "Caller":
                    caller = sval or caller
                elif key == "Callee":
                    callee = sval or callee
                elif key != "String":
                    pairs[key] = sval
        elif isinstance(node, list):
            for item in node:
                visit(item)

    if args is not None:
        visit(args)
    return caller, callee


def _pick_int(pairs: dict[str, str], *keys: str) -> int | None:
    for k in keys:
        if k in pairs and pairs[k] and _INT_RE.match(pairs[k]):
            return int(pairs[k])
    return None


def normalize_document(
    doc: dict[str, Any],
    *,
    source_path: Path | None = None,
    tool_version_metadata: dict[str, Any] | None = None,
) -> OptimizationRecord:
    """Convert one YAML document dict into a normalized record."""

    kind = doc.get("Kind")
    kind_s = str(kind).lower() if isinstance(kind, str) else None

    pass_name = _scalar_to_str(doc.get("Pass"))
    remark_name = _scalar_to_str(doc.get("Name"))
    function = _scalar_to_str(doc.get("Function"))
    file_s, line_i, col_i = _debug_loc(doc)

    args = doc.get("Args")
    strings: list[str] = []
    pairs: dict[str, str] = {}
    caller, callee = _walk_args(args, strings, pairs)

    message = "".join(strings) if strings else None
    reason = remark_name

    vf = _pick_int(pairs, "VectorizationFactor")
    unroll = _pick_int(pairs, "UnrollCount")

    cost = pairs.get("Cost") or None
    threshold = pairs.get("Threshold") or pairs.get("Treshold") or None
    hotness = _scalar_to_str(doc.get("Hotness"))

    from explncc.record_identity import apply_record_identity

    record = OptimizationRecord(
        kind=kind_s,
        pass_name=pass_name,
        remark_name=remark_name,
        function=function,
        file=file_s,
        line=line_i,
        column=col_i,
        caller=caller,
        callee=callee,
        reason=reason,
        message=message,
        vectorization_factor=vf,
        unroll_factor=unroll,
        cost=cost,
        threshold=threshold,
        hotness=hotness,
        args_raw=args,
        source_path=str(source_path) if source_path is not None else None,
        tool_version_metadata=tool_version_metadata,
    )
    return apply_record_identity(record, raw_doc=doc)


def split_tool_metadata(
    documents: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """If the first document looks like toolchain metadata, peel it off."""

    if not documents:
        return None, []
    first = documents[0]
    if not isinstance(first, dict):
        return None, documents
    if first.get("Kind") is not None:
        return None, documents
    # Heuristic: version-ish keys without optimization remark shape.
    keys = set(first.keys())
    meta_keys = {"Version", "LLVMVersion", "ClangVersion", "Producer", "Target"}
    if keys & meta_keys:
        return first, documents[1:]
    if "Pass" in first or "Function" in first:
        return None, documents
    # Ambiguous short dict — treat as data, not metadata.
    return None, documents


def load_records_from_path(path: Path) -> list[OptimizationRecord]:
    """Load every record from all ``.opt.yaml`` files under or at ``path``."""

    from explncc.parser import parse_opt_yaml_documents
    from explncc.utils import collect_opt_yaml_paths

    records: list[OptimizationRecord] = []
    for yaml_path in collect_opt_yaml_paths(path):
        text = yaml_path.read_text(encoding="utf-8", errors="replace")
        docs = parse_opt_yaml_documents(text)
        meta, body = split_tool_metadata(docs)
        for doc in body:
            if not isinstance(doc, dict):
                continue
            records.append(
                normalize_document(doc, source_path=yaml_path, tool_version_metadata=meta),
            )
    return records
