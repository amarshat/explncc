"""Toolchain adapters for optimization record inputs."""

from explncc.toolchains.base import ToolchainAdapter
from explncc.toolchains.clang import ClangOptYamlAdapter, get_adapter
from explncc.toolchains.hls import HlsReportAdapter

__all__ = [
    "ToolchainAdapter",
    "ClangOptYamlAdapter",
    "HlsReportAdapter",
    "get_adapter",
]
