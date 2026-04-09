"""Rich-based terminal rendering."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from rich.console import Console
from rich.table import Table


def print_table(
    console: Console,
    columns: Sequence[str],
    rows: Iterable[Sequence[Any]],
    *,
    title: str | None = None,
) -> None:
    table = Table(show_header=True, header_style="bold", title=title)
    for col in columns:
        table.add_column(col, overflow="fold")
    for row in rows:
        table.add_row(*[str(c) for c in row])
    console.print(table)
