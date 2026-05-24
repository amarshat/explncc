"""Toolchain adapter interface (Clang today; GCC/MSVC future)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from explncc.models import OptimizationRecord


class ToolchainAdapter(ABC):
    """Discover inputs and parse optimization records for a compiler toolchain."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def supported_file_extensions(self) -> tuple[str, ...]: ...

    @abstractmethod
    def discover_inputs(self, path: Path) -> list[Path]: ...

    @abstractmethod
    def parse_records(self, path: Path) -> list[OptimizationRecord]: ...
