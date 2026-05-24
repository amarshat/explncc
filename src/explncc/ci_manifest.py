"""CI artifact manifest for uploaded reports."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from explncc.report_types import REPORT_SCHEMA_VERSION


@dataclass
class CiManifest:
    schema_version: str = REPORT_SCHEMA_VERSION
    generated_at: str = ""
    git_sha: str | None = None
    build_id: str | None = None
    ci_provider: str | None = None
    raw_opt_yaml: list[str] = field(default_factory=list)
    markdown_report: str | None = None
    json_report: str | None = None
    github_comment: str | None = None
    diff_report: str | None = None
    policy_report: str | None = None
    manifest_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def write_manifest(path: str, manifest: CiManifest) -> None:
    from pathlib import Path

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if not manifest.generated_at:
        manifest.generated_at = datetime.now(tz=UTC).isoformat()
    p.write_text(json.dumps(manifest.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
