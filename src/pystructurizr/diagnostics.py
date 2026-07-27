"""Structured parse problems, for editors and CI.

A diagnostic is a machine-readable parse problem: where it happened, how
bad it is, and what to say about it. The parser produces these instead of
formatting positions into message strings, so an editor can place a marker
and a CI job can decide whether to fail.

Positions are 1-based lines, matching how editors and compilers report
them. Columns are optional: the tokeniser tracks lines only, so a
diagnostic without a column marks the whole line.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any


class Severity(str, Enum):
    """How much a problem matters.

    ``ERROR`` means the source could not be understood as written;
    ``WARNING`` means it parsed but something was skipped or ignored, which
    is the usual outcome for DSL features this parser does not implement.
    """

    ERROR = "error"
    WARNING = "warning"


@dataclass
class Diagnostic:
    """One parse problem.

    Attributes:
        message: Human-readable description, without position information.
        severity: :class:`Severity` of the problem.
        path: File the problem is in. ``None`` when parsing a bare string,
            and resolved through the include source map otherwise — a
            problem inside an ``!include``-ed fragment names that fragment,
            not the file that included it.
        line: 1-based line within ``path``.
        column: 1-based start column, when known.
        end_column: Exclusive 1-based end column, when known.
        code: Short stable identifier for the kind of problem, so editors
            and CI can filter without matching on message text.
    """

    message: str
    severity: Severity = Severity.ERROR
    path: Path | None = None
    line: int | None = None
    column: int | None = None
    end_column: int | None = None
    code: str = ""

    def __str__(self) -> str:
        """Render as ``path:line: message``, omitting unknown parts.

        This is the form the CLI prints and the form retained in the legacy
        ``Workspace.parse_warnings`` list of strings.
        """
        where = ""
        if self.path is not None:
            where = f"{self.path}:"
            if self.line is not None:
                where += f"{self.line}:"
        elif self.line is not None:
            where = f"Line {self.line}:"
        return f"{where} {self.message}".strip()

    def to_dict(self) -> dict[str, Any]:
        """Serialise for ``pystructurizr check --json``."""
        return {
            "path": str(self.path) if self.path is not None else None,
            "line": self.line,
            "column": self.column,
            "endColumn": self.end_column,
            "severity": self.severity.value,
            "code": self.code,
            "message": self.message,
        }
