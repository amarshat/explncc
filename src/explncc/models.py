"""Normalized optimization remark records (Pydantic)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class OptimizationRecord(BaseModel):
    """Stable, analysis-friendly view of one Clang optimization remark."""

    kind: str | None = None
    pass_name: str | None = None
    remark_name: str | None = None
    function: str | None = None
    file: str | None = None
    line: int | None = None
    column: int | None = None
    caller: str | None = None
    callee: str | None = None
    reason: str | None = None
    message: str | None = None
    vectorization_factor: int | None = None
    unroll_factor: int | None = None
    cost: str | None = None
    threshold: str | None = None
    hotness: str | None = None
    args_raw: Any = None
    source_path: str | None = Field(
        default=None,
        description="Path to the .opt.yaml file this record was loaded from.",
    )
    tool_version_metadata: dict[str, Any] | None = Field(
        default=None,
        description="Optional toolchain metadata when present as a leading YAML document.",
    )
    record_id: str | None = Field(
        default=None,
        description="Human-readable stable ID (pass/kind/remark/function/location).",
    )
    record_hash: str | None = Field(
        default=None,
        description="SHA-256 of canonical normalized record fields.",
    )
    raw_hash: str | None = Field(
        default=None,
        description="SHA-256 of the raw YAML document dict when available.",
    )
    source_key: str | None = Field(
        default=None,
        description="file:line:column:function location key.",
    )
    semantic_key: str | None = Field(
        default=None,
        description="pass:kind:remark:function:normalized-message key.",
    )

    def fingerprint(self) -> tuple[Any, ...]:
        """Cheap tuple for diffing and deduplication."""

        return (
            self.kind,
            self.pass_name,
            self.remark_name,
            self.function,
            self.file,
            self.line,
            self.column,
            self.reason,
            self.message,
        )
