"""Demangling: batch, best-effort, never worse than identity."""

from __future__ import annotations

import shutil
import subprocess
from typing import Any

import pytest

from explncc import demangle
from explncc.demangle import demangle_names, find_demangler


@pytest.fixture(autouse=True)
def _reset_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(demangle, "_resolved_tool", False)


def test_identity_when_no_demangler(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    assert find_demangler() is None
    names = ["_Z4scanPfPKfi", "main"]
    assert demangle_names(names) == {n: n for n in names}


def test_identity_when_tool_crashes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/c++filt")

    def boom(*_args: Any, **_kwargs: Any) -> None:
        raise OSError("exec failed")

    monkeypatch.setattr(subprocess, "run", boom)
    assert demangle_names(["_Z4scanPfPKfi"]) == {"_Z4scanPfPKfi": "_Z4scanPfPKfi"}


def test_non_itanium_names_never_hit_the_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/c++filt")

    def boom(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("subprocess should not run for non-mangled names")

    monkeypatch.setattr(subprocess, "run", boom)
    assert demangle_names(["main", "update_book"]) == {
        "main": "main",
        "update_book": "update_book",
    }


def test_batch_mapping_with_mocked_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/c++filt")

    def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        # Two mangled names in, two demangled lines out (sorted input order).
        assert kwargs["input"] == "_Z3dotPKfS0_i\n_Z4scanPfPKfi\n"
        return subprocess.CompletedProcess(
            argv,
            0,
            stdout="dot(float const*, float const*, int)\nscan(float*, float const*, int)\n",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = demangle_names(["_Z4scanPfPKfi", "_Z3dotPKfS0_i", "main"])
    assert result == {
        "_Z4scanPfPKfi": "scan(float*, float const*, int)",
        "_Z3dotPKfS0_i": "dot(float const*, float const*, int)",
        "main": "main",
    }


def test_mismatched_output_lines_fall_back_to_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/c++filt")

    def fake_run(argv: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(argv, 0, stdout="only one line\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    names = ["_Z4scanPfPKfi", "_Z3dotPKfS0_i"]
    assert demangle_names(names) == {n: n for n in names}


@pytest.mark.skipif(
    shutil.which("c++filt") is None and shutil.which("llvm-cxxfilt") is None,
    reason="no system demangler available",
)
def test_real_demangler_handles_itanium_names() -> None:
    result = demangle_names(["_Z4scanPfPKfi"])
    assert result["_Z4scanPfPKfi"].startswith("scan(")
