"""Load workspace documentation and ADRs referenced by ``!docs``/``!adrs``.

Structurizr attaches long-form documentation to a workspace via directory
directives in the DSL::

    workspace {
        !docs docs
        !adrs adrs
        ...
    }

``!docs`` reads every markdown file in the directory (sorted by filename)
as a documentation section; ``!adrs`` reads them as architecture decision
records in the common adr-tools format (``# N. Title``, a ``Date:`` line,
and a ``## Status`` section).
"""

from __future__ import annotations

import re
from pathlib import Path

from c4studio.models import Decision, Section


_MARKDOWN_SUFFIXES = frozenset({".md", ".markdown"})

_HEADING_RE = re.compile(r"^#\s+(?P<title>.+?)\s*$", re.MULTILINE)
_ADR_HEADING_RE = re.compile(r"^#\s+(?:(?P<num>\d+)[.:]\s*)?(?P<title>.+?)\s*$")
_DATE_RE = re.compile(r"^date:\s*(?P<date>.+?)\s*$", re.IGNORECASE | re.MULTILINE)
_STATUS_RE = re.compile(
    r"^##\s+status\s*\n+(?P<status>\S[^\n]*)", re.IGNORECASE | re.MULTILINE
)


def markdown_files(directory: Path) -> list[Path]:
    """Markdown files directly inside ``directory``, sorted by filename."""
    if not directory.is_dir():
        return []
    return sorted(
        entry
        for entry in directory.iterdir()
        if entry.is_file() and entry.suffix.lower() in _MARKDOWN_SUFFIXES
    )


def _first_heading(content: str, fallback: str) -> str:
    match = _HEADING_RE.search(content)
    return match.group("title") if match else fallback


def load_sections(directory: Path) -> list[Section]:
    """Read a ``!docs`` directory into ordered documentation sections.

    Section titles come from each file's first ``#`` heading, falling back
    to the filename; order follows the sorted filenames (Structurizr's
    convention of numbering files like ``01-context.md`` therefore works).
    """
    sections: list[Section] = []
    for order, path in enumerate(markdown_files(directory), start=1):
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            continue
        sections.append(
            Section(
                content=content,
                title=_first_heading(content, path.stem),
                filename=path.name,
                order=order,
            )
        )
    return sections


def load_decisions(directory: Path) -> list[Decision]:
    """Read an ``!adrs`` directory into architecture decision records.

    Follows the adr-tools conventions: the first heading provides the id
    (leading number, else the file position) and title; a ``Date:`` line
    and the first line under ``## Status`` fill the metadata when present.
    """
    decisions: list[Decision] = []
    for position, path in enumerate(markdown_files(directory), start=1):
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            continue
        title = path.stem
        decision_id = str(position)
        for line in content.splitlines():
            match = _ADR_HEADING_RE.match(line)
            if match:
                title = match.group("title")
                if match.group("num"):
                    decision_id = match.group("num")
                break
        date_match = _DATE_RE.search(content)
        status_match = _STATUS_RE.search(content)
        decisions.append(
            Decision(
                id=decision_id,
                title=title,
                date=date_match.group("date") if date_match else "",
                status=status_match.group("status").strip() if status_match else "",
                content=content,
            )
        )
    return decisions
