"""Backend contract types for optional model explanations."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ExplanationResult:
    backend: str
    model: str | None
    success: bool
    text: str
    fallback_used: bool = False
    warnings: list[str] = field(default_factory=list)
    prompt_hash: str | None = None
    evidence_hash: str | None = None
    latency_ms: int | None = None
    error_type: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "backend": self.backend,
            "model": self.model,
            "success": self.success,
            "text": self.text,
            "fallback_used": self.fallback_used,
            "warnings": self.warnings,
            "prompt_hash": self.prompt_hash,
            "evidence_hash": self.evidence_hash,
            "latency_ms": self.latency_ms,
            "error_type": self.error_type,
        }
