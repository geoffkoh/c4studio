"""Centralised workspace loading from a filesystem path.

This module owns the suffix-based dispatch that turns a ``.dsl``/``.json``/
``.structurizr`` file into a :class:`~c4studio.models.Workspace`. Both the
CLI and the web backend delegate here so the behaviour stays identical.
"""

from __future__ import annotations

from pathlib import Path

from c4studio.models import Workspace
from c4studio.parser.dsl import ParseError, collect_source_files, parse_dsl_file
from c4studio.parser.json_parser import parse_json_file


class WorkspaceLoadError(Exception):
    """Raised when a workspace cannot be loaded or parsed from disk."""


_DSL_SUFFIXES = frozenset({".dsl", ".structurizr", ""})


def load_workspace(path: Path) -> Workspace:
    """Load and parse a workspace from ``path`` based on its suffix.

    Args:
        path: Path to a Structurizr source file. ``.json`` files are parsed
            as the JSON export format; ``.dsl``, ``.structurizr`` and
            suffix-less files are parsed as DSL.

    Returns:
        The parsed :class:`~c4studio.models.Workspace`.

    Raises:
        WorkspaceLoadError: If the suffix is unsupported, the file cannot be
            read, or the parser rejects its contents.
    """
    suffix = path.suffix.lower()
    try:
        if suffix == ".json":
            return parse_json_file(path)
        if suffix in _DSL_SUFFIXES:
            return parse_dsl_file(path)
    except (ParseError, OSError, ValueError) as exc:
        raise WorkspaceLoadError(
            f"Failed to load workspace from {path}: {exc}"
        ) from exc

    raise WorkspaceLoadError(
        f"Unsupported file type: {suffix or '(none)'}. Use .dsl, .structurizr or .json"
    )


def watched_files(path: Path) -> list[Path]:
    """Return the files that make up the workspace source at ``path``.

    For DSL sources this is the file plus every transitive ``!include``
    target; JSON exports are a single file. Used for live-reload change
    detection.
    """
    if path.suffix.lower() == ".json":
        return [path]
    return collect_source_files(path)
