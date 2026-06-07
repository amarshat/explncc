"""High-level-synthesis (HLS) report adapter (experimental).

Parses the synthesis reports that an HLS tool already emits (Vitis HLS
``csynth.xml`` today) and normalizes per-loop pipelining facts into the same
:class:`~explncc.models.OptimizationRecord` shape used for Clang ``.opt.yaml``.

The book's thesis carries over unchanged: make the compiler write down what it
decided, then read it. On a CPU the hidden decision is vectorization width or an
inline cost; in HLS it is a loop's *initiation interval* (II) and whether the
loop was pipelined. This adapter surfaces those decisions as evidence; it does
**not** run Vitis/Vivado.

Mapping into OptimizationRecord (so every downstream verb works unchanged):

* ``pass_name``  -> ``hls-pipeline`` / ``hls-unroll`` / ``hls-dataflow``
* ``kind``       -> ``passed`` (II achieved) / ``missed`` (target II not met,
                    or loop left un-pipelined) / ``analysis`` (latency only)
* ``remark_name``-> ``Pipelined`` / ``IINotAchieved`` / ``LoopNotPipelined``
* ``cost``       -> achieved II (string), ``threshold`` -> target II (string)
                    so existing fingerprint/diff/hash logic compares II drift
                    for free.
* ``initiation_interval`` / ``target_ii`` / ``loop_latency`` / ``trip_count``
                    -> display-only ints (not part of the record hash payload).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from explncc.models import OptimizationRecord
from explncc.record_identity import apply_record_identity
from explncc.toolchains.base import ToolchainAdapter

_HLS_EXTENSIONS: tuple[str, ...] = (".xml", ".rpt", ".hls.json")


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"n/a", "na", "-", "?", "unknown"}:
        return None
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return None


def _classify_loop(
    achieved_ii: int | None, target_ii: int | None, pipelined: bool
) -> tuple[str, str, str]:
    """Return (pass_name, kind, remark_name) for a loop's pipeline outcome."""

    if not pipelined or achieved_ii is None:
        return "hls-pipeline", "missed", "LoopNotPipelined"
    if target_ii is not None and achieved_ii > target_ii:
        return "hls-pipeline", "missed", "IINotAchieved"
    return "hls-pipeline", "passed", "Pipelined"


def _loop_message(
    name: str,
    achieved_ii: int | None,
    target_ii: int | None,
    latency: int | None,
    trip_count: int | None,
    raw_reason: str | None,
) -> str:
    bits: list[str] = [f"loop '{name}'"]
    if achieved_ii is not None:
        bits.append(f"initiation interval II={achieved_ii}")
    if target_ii is not None:
        bits.append(f"target II={target_ii}")
    if latency is not None:
        bits.append(f"latency={latency} cycles")
    if trip_count is not None:
        bits.append(f"trip count={trip_count}")
    text = ", ".join(bits)
    if raw_reason:
        text = f"{text}; {raw_reason.strip()}"
    return text


def _record_from_loop(
    *,
    loop_name: str,
    function: str | None,
    file_s: str | None,
    line_i: int | None,
    achieved_ii: int | None,
    target_ii: int | None,
    latency: int | None,
    trip_count: int | None,
    raw_reason: str | None,
    source_path: Path | None,
    raw_doc: dict[str, Any],
) -> OptimizationRecord:
    pipelined = achieved_ii is not None and (raw_reason is None or "not" not in raw_reason.lower())
    pass_name, kind, remark_name = _classify_loop(achieved_ii, target_ii, pipelined)
    message = _loop_message(loop_name, achieved_ii, target_ii, latency, trip_count, raw_reason)
    record = OptimizationRecord(
        kind=kind,
        pass_name=pass_name,
        remark_name=remark_name,
        function=function or loop_name,
        file=file_s,
        line=line_i,
        column=None,
        reason=raw_reason or remark_name,
        message=message,
        cost=str(achieved_ii) if achieved_ii is not None else None,
        threshold=str(target_ii) if target_ii is not None else None,
        initiation_interval=achieved_ii,
        target_ii=target_ii,
        loop_latency=latency,
        trip_count=trip_count,
        args_raw=raw_doc,
        source_path=str(source_path) if source_path is not None else None,
    )
    return apply_record_identity(record, raw_doc=raw_doc)


def _findtext(elem: ET.Element, *paths: str) -> str | None:
    for p in paths:
        child = elem.find(p)
        if child is not None and child.text is not None and child.text.strip():
            return child.text.strip()
    return None


def parse_csynth_xml(text: str, *, source_path: Path | None = None) -> list[OptimizationRecord]:
    """Parse a Vitis HLS ``csynth.xml`` report into loop pipeline records."""

    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:  # pragma: no cover - defensive
        msg = f"not a parseable HLS XML report: {exc}"
        raise ValueError(msg) from exc

    top_function = _findtext(root, "./UserAssignments/TopModelName") or _findtext(
        root, "./RTLDesignHierarchy/TopModelName"
    )

    records: list[OptimizationRecord] = []
    # Vitis emits per-loop detail under PerformanceEstimates/SummaryOfLoopLatency.
    loop_summary = root.find("./PerformanceEstimates/SummaryOfLoopLatency")
    if loop_summary is not None:
        for loop in loop_summary:
            name = loop.tag
            achieved_ii = _to_int(_findtext(loop, "PipelineII"))
            target_ii = _to_int(_findtext(loop, "TargetII"))
            latency = _to_int(_findtext(loop, "IterationLatency", "PipelineDepth"))
            trip_count = _to_int(_findtext(loop, "TripCount"))
            raw_reason = _findtext(loop, "PipelineComment", "Comment")
            raw_doc: dict[str, Any] = {
                "Loop": name,
                "PipelineII": achieved_ii,
                "TargetII": target_ii,
                "IterationLatency": latency,
                "TripCount": trip_count,
                "PipelineComment": raw_reason,
                "TopFunction": top_function,
            }
            records.append(
                _record_from_loop(
                    loop_name=name,
                    function=top_function,
                    file_s=None,
                    line_i=None,
                    achieved_ii=achieved_ii,
                    target_ii=target_ii,
                    latency=latency,
                    trip_count=trip_count,
                    raw_reason=raw_reason,
                    source_path=source_path,
                    raw_doc=raw_doc,
                )
            )
    return records


class HlsReportAdapter(ToolchainAdapter):
    """Parse HLS synthesis reports (Vitis ``csynth.xml`` today). Experimental."""

    @property
    def name(self) -> str:
        return "hls"

    def supported_file_extensions(self) -> tuple[str, ...]:
        return _HLS_EXTENSIONS

    def discover_inputs(self, path: Path) -> list[Path]:
        if path.is_file():
            return [path.resolve()]
        if not path.is_dir():
            msg = f"path not found: {path}"
            raise FileNotFoundError(msg)
        found: list[Path] = []
        for ext in _HLS_EXTENSIONS:
            found.extend(path.rglob(f"*{ext}"))
        if not found:
            msg = f"no HLS report files ({', '.join(_HLS_EXTENSIONS)}) under {path}"
            raise FileNotFoundError(msg)
        return sorted({p.resolve() for p in found})

    def parse_records(self, path: Path) -> list[OptimizationRecord]:
        records: list[OptimizationRecord] = []
        for report in self.discover_inputs(path):
            text = report.read_text(encoding="utf-8")
            records.extend(parse_csynth_xml(text, source_path=report))
        return records
