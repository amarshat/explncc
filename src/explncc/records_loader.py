"""Load optimization records via toolchain adapters."""

from __future__ import annotations

from pathlib import Path

from explncc.models import OptimizationRecord
from explncc.toolchains import get_adapter


def load_records(path: Path, *, toolchain: str = "clang") -> list[OptimizationRecord]:
    return get_adapter(toolchain).parse_records(path)
