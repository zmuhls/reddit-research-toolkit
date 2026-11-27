"""Terminal output helpers shared by every command.

One Console instance, a handful of message styles, and symbols that fall back
to plain ASCII on terminals that cannot draw Unicode (older Windows consoles).
"""

from __future__ import annotations

import sys
from typing import Iterable, Optional

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.theme import Theme

_THEME = Theme(
    {
        "ok": "green",
        "warn": "yellow",
        "fail": "bold red",
        "hint": "dim",
        "cmd": "bold cyan",
        "path": "cyan",
        "head": "bold",
    }
)

console = Console(theme=_THEME, highlight=False)


def _unicode_ok() -> bool:
    encoding = (getattr(sys.stdout, "encoding", None) or "").lower()
    return "utf" in encoding


UNICODE = _unicode_ok()
MARK_OK = "✓" if UNICODE else "OK"
MARK_WARN = "!" if UNICODE else "!"
MARK_FAIL = "✗" if UNICODE else "X"
BULLET = "•" if UNICODE else "-"
ARROW = "→" if UNICODE else "->"


def e(text: object) -> str:
    """Escape text that came from outside (names, paths, error messages).

    Square brackets mean markup to rich, and Reddit data is full of them
    ([deleted], [removed]), so anything not written in this codebase goes
    through here before printing.
    """
    return escape(str(text))


def heading(text: str) -> None:
    console.print()
    console.print(f"[head]{e(text)}[/head]")


def ok(text: str) -> None:
    console.print(f"[ok]{MARK_OK}[/ok] {text}")


def warn(text: str) -> None:
    console.print(f"[warn]{MARK_WARN}[/warn] {text}")


def fail(text: str) -> None:
    console.print(f"[fail]{MARK_FAIL}[/fail] {text}")


def info(text: str = "") -> None:
    console.print(text)


def hint(text: str) -> None:
    console.print(f"[hint]{text}[/hint]")


def command(text: str) -> None:
    """Print a command the reader can copy, on its own indented line."""
    console.print(f"    [cmd]{e(text)}[/cmd]", soft_wrap=True)


def next_steps(title: str, steps: Iterable[tuple]) -> None:
    """Print 'what to do next' as description + command pairs."""
    heading(title)
    for description, cmd in steps:
        console.print(f"  {BULLET} {description}")
        if cmd:
            command(cmd)


def error_panel(title: str, why: str, fixes: Iterable[str], detail: Optional[str] = None) -> None:
    """The one shape every failure takes: what happened, why, what to try."""
    lines = [e(why)]
    fixes = list(fixes)
    if fixes:
        lines.append("")
        lines.append("[head]Try this[/head]")
        for number, fix in enumerate(fixes, 1):
            lines.append(f"  {number}. {fix}")
    if detail:
        lines.append("")
        lines.append(f"[hint]Technical detail: {e(detail)}[/hint]")
    console.print()
    console.print(Panel("\n".join(lines), title=f"[fail]{e(title)}[/fail]", title_align="left", border_style="red", expand=False))


def note_panel(title: str, body: str, style: str = "yellow") -> None:
    console.print()
    console.print(Panel(body, title=f"[head]{e(title)}[/head]", title_align="left", border_style=style, expand=False))


def table(title: Optional[str], columns: Iterable[str], rows: Iterable[Iterable[object]], *, right: Iterable[str] = ()) -> None:
    """Print a simple table. Cell text is escaped."""
    right = set(right)
    columns = list(columns)
    grid = Table(title=title, title_justify="left", title_style="head", header_style="hint", box=None, pad_edge=False,
                 padding=(0, 2, 0, 0), show_header=any(columns))
    for column in columns:
        grid.add_column(column, justify="right" if column in right else "left", overflow="fold")
    for row in rows:
        grid.add_row(*[e(cell) for cell in row])
    console.print(grid)


def interactive() -> bool:
    """True when a person is at the keyboard and prompts make sense."""
    return sys.stdin.isatty() and sys.stdout.isatty()
