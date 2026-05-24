"""Shared types for Chapter 12 CI reports."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

REPORT_SCHEMA_VERSION = "1.0"


@dataclass
class ReportMetadata:
    git_sha: str | None = None
    branch: str | None = None
    pr_number: str | None = None
    build_id: str | None = None
    ci_provider: str | None = None
    repo: str | None = None
    target_name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "git_sha": self.git_sha,
            "branch": self.branch,
            "pr_number": self.pr_number,
            "build_id": self.build_id,
            "ci_provider": self.ci_provider,
            "repo": self.repo,
            "target_name": self.target_name,
        }


@dataclass
class ReportSourceInfo:
    input_path: str
    file_count: int
    remark_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_path": self.input_path,
            "file_count": self.file_count,
            "remark_count": self.remark_count,
        }


@dataclass
class ExplanationInfo:
    enabled: bool
    backend: str | None = None
    label: str | None = None
    warning: str | None = None
    items: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "backend": self.backend,
            "label": self.label,
            "warning": self.warning,
            "items": self.items,
        }


@dataclass
class ReportBuildOptions:
    title: str = "Compiler Optimization Report"
    top_missed: int = 12
    top_analysis: int = 8
    include_passed: bool = False
    top_passed: int = 8
    message_max_chars: int = 4000
    github_collapsible: bool = True
    explain_backend: str | None = None
    explain_label: str | None = None
