"""Batch C++ symbol demangling via c++filt / llvm-cxxfilt (best-effort, offline).

Optimization records carry mangled names (``_Z4scanPfPKfi``). Every table and
finding is easier to read demangled, so this module shells out to whichever
demangler the toolchain already installed. One subprocess call handles a whole
batch. Absence of a demangler, a crash, or mismatched output all degrade to the
identity mapping: a mangled name is never worse than before, and nothing here
touches the network.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Iterable

_DEMANGLER_CANDIDATES = ("c++filt", "llvm-cxxfilt")

# Resolved once per process; ``False`` means "looked and found nothing".
_resolved_tool: str | None | bool = False


def find_demangler() -> str | None:
    """Return the demangler executable path, or ``None`` when none exists."""

    global _resolved_tool
    if _resolved_tool is False:
        _resolved_tool = None
        for name in _DEMANGLER_CANDIDATES:
            path = shutil.which(name)
            if path:
                _resolved_tool = path
                break
    return _resolved_tool if isinstance(_resolved_tool, str) else None


def demangle_names(names: Iterable[str]) -> dict[str, str]:
    """Map each name to its demangled form (identity on any failure).

    Only Itanium-mangled names (``_Z`` prefix) are sent to the tool; everything
    else maps to itself. The whole batch goes through one subprocess call.
    """

    unique = sorted({n for n in names if n})
    mapping = {n: n for n in unique}
    mangled = [n for n in unique if n.startswith("_Z")]
    if not mangled:
        return mapping
    tool = find_demangler()
    if tool is None:
        return mapping
    # Apple's c++filt assumes the Mach-O leading-underscore form on stdin and
    # leaves raw Itanium names alone; ``-n`` (no-strip-underscore) makes it,
    # GNU binutils, and llvm-cxxfilt all demangle ``_Z...`` directly. Fall back
    # to a flagless run for any demangler that rejects the flag.
    for argv in ([tool, "-n"], [tool]):
        try:
            proc = subprocess.run(  # noqa: S603 (fixed argv, no shell)
                argv,
                input="\n".join(mangled) + "\n",
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return mapping
        if proc.returncode != 0:
            continue
        lines = proc.stdout.splitlines()
        if len(lines) != len(mangled):
            continue
        changed = False
        for name, demangled in zip(mangled, lines, strict=True):
            cleaned = demangled.strip()
            if cleaned and cleaned != name:
                mapping[name] = cleaned
                changed = True
        if changed:
            return mapping
    return mapping
