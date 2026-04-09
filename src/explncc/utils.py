"""Filesystem helpers for locating optimization record files."""

from __future__ import annotations

from pathlib import Path


def collect_opt_yaml_paths(path: Path) -> list[Path]:
    """Return sorted paths to `.opt.yaml` files under ``path``.

    If ``path`` is a file, it must end with ``.opt.yaml``. If it is a directory,
    all ``*.opt.yaml`` files are collected recursively.
    """

    if path.is_file():
        if not path.name.endswith(".opt.yaml"):
            msg = f"not an optimization record file: {path}"
            raise ValueError(msg)
        return [path.resolve()]
    if not path.is_dir():
        msg = f"path not found: {path}"
        raise FileNotFoundError(msg)
    found = sorted(path.rglob("*.opt.yaml"))
    if not found:
        msg = f"no .opt.yaml files under {path}"
        raise FileNotFoundError(msg)
    return [p.resolve() for p in found]
