"""Locate element definitions in DSL source files.

Maps element ids to their definition site — ``(file, line)`` in the
*original* source files, not the ``!include``-flattened text — by
tokenising each file independently with the parser's tokenizer and
matching the same definition patterns ``_Parser`` uses:

- ``alias = keyword ...`` → id is the alias
- ``keyword "Name" ...`` → id is the slugified name
- ``[alias =] containerInstance ref`` → alias or a generated
  ``<ref>_instance[_n]`` id

The scan is best-effort and read-only: it reproduces the parser's id
rules without running the parser, so it never fails on files the parser
would reject, and unmatchable constructs are simply absent from the
result. Used by the web app's source viewer for
double-click-to-definition.
"""

from __future__ import annotations

from pathlib import Path

from c4studio.parser.dsl import (
    ARROW,
    EQUALS,
    IDENT,
    LBRACE,
    RBRACE,
    STRING,
    collect_source_files,
    _tokenize,
)


_DSL_SUFFIXES = frozenset({".dsl", ".structurizr"})

_ELEMENT_KEYWORDS = frozenset(
    {
        "person",
        "softwaresystem",
        "container",
        "component",
        "deploymentnode",
        "infrastructurenode",
        "element",
    }
)
_INSTANCE_KEYWORDS = frozenset({"softwaresysteminstance", "containerinstance"})


def _slug(name: str) -> str:
    """The parser's id for an unaliased element (dsl.py `_parse_element`)."""
    return name.replace(" ", "_").lower()


def element_locations(root: str | Path) -> dict[str, tuple[Path, int]]:
    """Return ``{element_id: (source_file, line)}`` for a workspace source.

    Scans the root file plus every transitive ``!include`` fragment; the
    first definition wins when an id appears more than once.
    """
    locations: dict[str, tuple[Path, int]] = {}
    taken: set[str] = set()

    def unique(base: str) -> str:
        if base not in taken:
            return base
        n = 2
        while f"{base}_{n}" in taken:
            n += 1
        return f"{base}_{n}"

    def record(eid: str, path: Path, line: int) -> None:
        taken.add(eid)
        locations.setdefault(eid, (path, line))

    for path in collect_source_files(root):
        if path.suffix.lower() not in _DSL_SUFFIXES:
            continue
        try:
            tokens = _tokenize(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue

        i = 0
        depth = 0
        # Depth of the current `styles { ... }` block, if inside one; its
        # `element "Tag"` rules must not be indexed as element definitions.
        styles_depth: int | None = None
        while i < len(tokens):
            tok = tokens[i]
            if tok.type == LBRACE:
                depth += 1
                i += 1
                continue
            if tok.type == RBRACE:
                depth -= 1
                if styles_depth is not None and depth < styles_depth:
                    styles_depth = None
                i += 1
                continue
            if tok.type != IDENT:
                i += 1
                continue
            if styles_depth is None and tok.value.lower() == "styles":
                nxt = tokens[i + 1] if i + 1 < len(tokens) else None
                if nxt is not None and nxt.type == LBRACE:
                    styles_depth = depth + 1
                i += 1
                continue
            if styles_depth is not None:
                i += 1
                continue

            # alias = keyword ...
            if (
                i + 2 < len(tokens)
                and tokens[i + 1].type == EQUALS
                and tokens[i + 2].type == IDENT
                and tokens[i + 2].value.lower()
                in _ELEMENT_KEYWORDS | _INSTANCE_KEYWORDS
            ):
                record(tok.value, path, tok.line)
                i += 3
                continue

            # Relationship source: skip `a -> ...` so aliases that shadow
            # keywords never match below.
            if i + 1 < len(tokens) and tokens[i + 1].type == ARROW:
                i += 2
                continue

            keyword = tok.value.lower()
            nxt = tokens[i + 1] if i + 1 < len(tokens) else None
            if keyword in _ELEMENT_KEYWORDS:
                # keyword "Name" ... (view headers like `container s Key`
                # have an IDENT after the keyword, so they never match).
                if nxt is not None and nxt.type == STRING:
                    record(_slug(nxt.value.strip('"')), path, tok.line)
                    i += 2
                    continue
            elif keyword in _INSTANCE_KEYWORDS:
                # containerInstance ref (unaliased): generated unique id.
                ref = None
                if nxt is not None and nxt.type == IDENT:
                    ref = nxt.value
                elif nxt is not None and nxt.type == STRING:
                    ref = nxt.value.strip('"')
                if ref is not None:
                    record(unique(f"{ref}_instance"), path, tok.line)
                    i += 2
                    continue
            i += 1

    return locations
