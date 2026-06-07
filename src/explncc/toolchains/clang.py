"""Clang/LLVM ``.opt.yaml`` optimization record adapter (default)."""

from __future__ import annotations

from pathlib import Path

from explncc.models import OptimizationRecord
from explncc.normalizer import load_records_from_path
from explncc.toolchains.base import ToolchainAdapter
from explncc.toolchains.hls import HlsReportAdapter
from explncc.utils import collect_opt_yaml_paths


class ClangOptYamlAdapter(ToolchainAdapter):
    """Parse ``-fsave-optimization-record`` YAML streams."""

    @property
    def name(self) -> str:
        return "clang"

    def supported_file_extensions(self) -> tuple[str, ...]:
        return (".opt.yaml",)

    def discover_inputs(self, path: Path) -> list[Path]:
        return collect_opt_yaml_paths(path)

    def parse_records(self, path: Path) -> list[OptimizationRecord]:
        return load_records_from_path(path)


_ADAPTERS: dict[str, ToolchainAdapter] = {
    "clang": ClangOptYamlAdapter(),
    "hls": HlsReportAdapter(),
}


def get_adapter(toolchain: str = "clang") -> ToolchainAdapter:
    key = toolchain.strip().lower()
    if key not in _ADAPTERS:
        msg = f"unsupported toolchain: {toolchain!r} (supported: {', '.join(_ADAPTERS)})"
        raise ValueError(msg)
    return _ADAPTERS[key]
