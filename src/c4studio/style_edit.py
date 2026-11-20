"""Edit a workspace's style rules as text (PP-231).

The Studio's details card changes a colour by editing the DSL, never the
per-user layout sidecar: a colour is part of what the model says, and the
DSL is what ``c4 render``, ``c4 publish``, Structurizr and teammates read.

Every function here takes a file's text and returns new text. Nothing is
written: the web app either saves the result through the editor's save
path or, when the file has unsaved edits, puts it into the editor's buffer.
Edits are surgical, so formatting and comments survive. A construct this
module cannot edit safely (a statement continued across lines) raises
:class:`StyleEditError` rather than guessing.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass

from c4studio.models.deployment import DeploymentNode
from c4studio.models.workspace import Workspace
from c4studio.parser.dsl import IDENT, LBRACE, RBRACE, STRING, Token, _tokenize

#: The style properties the card edits, by rule kind. ``style`` is the
#: relationship's dash pattern (Solid, Dashed, Dotted).
EDITABLE: dict[str, frozenset[str]] = {
    "element": frozenset({"background", "color", "stroke", "icon"}),
    "relationship": frozenset({"color", "style"}),
}

_HEX = re.compile(r"#[0-9A-Fa-f]{6}")
_DASH = frozenset({"solid", "dashed", "dotted"})
_INDENT = "    "


class StyleEditError(Exception):
    """The edit cannot be made safely; nothing should be written."""


def check_value(kind: str, prop: str, value: str | None) -> str | None:
    """Validate one property value, returning it as the DSL spells it.

    Raises:
        StyleEditError: for a property the card does not edit, or a value
            it would not write (a colour that is not ``#rrggbb``).
    """
    if prop not in EDITABLE.get(kind, frozenset()):
        raise StyleEditError(f"{kind} style property {prop!r} is not editable")
    if value is None:
        return None
    if prop == "icon":
        # A path relative to the rule's file, or a URL: written quoted, so
        # a quote, a backslash or a line break could not be.
        if not value or any(c in value for c in '"\\\n\r'):
            raise StyleEditError(f"icon must be a path or a URL: {value!r}")
        return f'"{value}"'
    if prop == "style":
        if value.lower() not in _DASH:
            raise StyleEditError(
                f"line style must be solid, dashed or dotted: {value!r}"
            )
        return value.capitalize()
    if not _HEX.fullmatch(value):
        raise StyleEditError(f"colour must be #rrggbb: {value!r}")
    return value.lower()


# -- text plumbing -----------------------------------------------------------


@dataclass
class _Text:
    """A file's text with token positions resolved to character offsets."""

    text: str
    tokens: list[Token]
    starts: list[int]

    @classmethod
    def of(cls, text: str) -> _Text:
        starts = [0, *(match.end() for match in re.finditer("\n", text))]
        return cls(text, _tokenize(text), starts)

    def offset(self, line: int, column: int) -> int:
        return self.starts[line - 1] + column - 1

    def start(self, token: Token) -> int:
        return self.offset(token.line, token.column)

    def end(self, token: Token) -> int:
        return self.offset(token.line, token.end_column)

    def line_start(self, line: int) -> int:
        return self.starts[line - 1]

    def line_end(self, line: int) -> int:
        """Offset just past the line's newline (or the end of the text)."""
        return self.starts[line] if line < len(self.starts) else len(self.text)

    def indent(self, line: int) -> str:
        start = self.line_start(line)
        stripped = self.text[start:].lstrip(" \t")
        return self.text[start : len(self.text) - len(stripped)]

    def only_on_line(self, token: Token) -> bool:
        """Whether nothing but whitespace precedes the token on its line."""
        return not self.text[self.line_start(token.line) : self.start(token)].strip()


def _matching(tokens: list[Token], open_index: int) -> int:
    depth = 0
    for i in range(open_index, len(tokens)):
        if tokens[i].type == LBRACE:
            depth += 1
        elif tokens[i].type == RBRACE:
            depth -= 1
            if depth == 0:
                return i
    raise StyleEditError("unbalanced braces")


def _blocks(doc: _Text, keyword: str) -> Iterator[tuple[int, int]]:
    """``(open, close)`` token indexes of every ``keyword {`` block."""
    tokens = doc.tokens
    for i, tok in enumerate(tokens[:-1]):
        if (
            tok.type == IDENT
            and tok.value.lower() == keyword
            and tokens[i + 1].type == LBRACE
        ):
            yield i + 1, _matching(tokens, i + 1)


def _rules(doc: _Text, kind: str, tag: str) -> list[tuple[int, int]]:
    """``(open, close)`` of each ``kind "tag" { ... }`` rule in a styles block."""
    tokens = doc.tokens
    found: list[tuple[int, int]] = []
    for open_, close in _blocks(doc, "styles"):
        i = open_ + 1
        while i < close:
            tok = tokens[i]
            if tok.type == LBRACE:
                i = _matching(tokens, i) + 1
                continue
            if (
                tok.type == IDENT
                and tok.value.lower() == kind
                and i + 2 < close
                and tokens[i + 1].type in (STRING, IDENT)
                and tokens[i + 1].value.strip('"') == tag
                and tokens[i + 2].type == LBRACE
            ):
                end = _matching(tokens, i + 2)
                found.append((i + 2, end))
                i = end + 1
                continue
            i += 1
    return found


def _insert_lines(doc: _Text, close: int, lines: list[str]) -> str:
    """Insert ``lines`` as the last statements of the block closing at ``close``.

    ``lines`` are relative to the block's body, so they are indented one
    level deeper than the closing brace. A block written on one line
    (``element "X" { background #fff }``) is opened out first, since a DSL
    statement must sit on a line of its own.
    """
    brace = doc.tokens[close]
    text = doc.text
    if doc.only_on_line(brace):
        outer = doc.indent(brace.line)
        body = "".join(f"{outer}{_INDENT}{line}\n" for line in lines)
        at = doc.line_start(brace.line)
        return text[:at] + body + text[at:]
    opener = _opening(doc, close)
    outer = doc.indent(doc.tokens[opener].line)
    inner = text[doc.end(doc.tokens[opener]) : doc.start(brace)].strip()
    statements = [inner] if inner else []
    statements += lines
    middle = "".join(f"{outer}{_INDENT}{line}\n" for line in statements)
    return (
        text[: doc.end(doc.tokens[opener])]
        + "\n"
        + middle
        + outer
        + text[doc.start(brace) :]
    )


def _opening(doc: _Text, close: int) -> int:
    depth = 0
    for i in range(close, -1, -1):
        if doc.tokens[i].type == RBRACE:
            depth += 1
        elif doc.tokens[i].type == LBRACE:
            depth -= 1
            if depth == 0:
                return i
    raise StyleEditError("unbalanced braces")


# -- style rules -------------------------------------------------------------


def _rule_lines(kind: str, tag: str, prop: str, value: str) -> list[str]:
    return [f'{kind} "{tag}" {{', f"{_INDENT}{prop} {value}", "}"]


def set_rule_property(
    text: str, kind: str, tag: str, prop: str, value: str | None
) -> str:
    """Set (or, with ``None``, remove) one property of the last ``kind "tag"`` rule.

    The last rule is the one that wins where two rules for a tag overlap.
    With no rule for the tag, a new one is appended to the last ``styles``
    block, creating ``styles`` (and ``views``) when the file has none, so
    it is declared after every other rule and wins over them.

    Raises:
        StyleEditError: for an invalid value, or when removing from a rule
            that does not exist.
    """
    raw = value
    value = check_value(kind, prop, value)
    doc = _Text.of(text)
    rules = _rules(doc, kind, tag)
    if not rules:
        if value is None:
            return text
        return add_rule(text, kind, tag, prop, raw)
    open_, close = rules[-1]
    tokens = doc.tokens
    # A property statement sits directly in the rule body, first on its line.
    i = open_ + 1
    while i < close:
        tok = tokens[i]
        if tok.type == LBRACE:
            i = _matching(tokens, i) + 1
            continue
        if tok.type == IDENT and tok.value.lower() == prop:
            last = i
            while last + 1 < close and tokens[last + 1].line == tok.line:
                if tokens[last + 1].type in (LBRACE, RBRACE):
                    break
                last += 1
            if value is None:
                if (
                    doc.only_on_line(tok)
                    and not text[doc.end(tokens[last]) : doc.line_end(tok.line)].strip()
                ):
                    return (
                        text[: doc.line_start(tok.line)]
                        + text[doc.line_end(tok.line) :]
                    )
                return text[: doc.start(tok)] + text[doc.end(tokens[last]) :].lstrip(
                    " "
                )
            if last == i:
                return text[: doc.end(tok)] + f" {value}" + text[doc.end(tok) :]
            # Only the value token: a colour or a dash pattern is one, and
            # what follows it on the line may be a comment worth keeping.
            value_token = tokens[i + 1]
            return text[: doc.start(value_token)] + value + text[doc.end(value_token) :]
        i += 1
    if value is None:
        return text
    return _insert_lines(doc, close, [f"{prop} {value}"])


def add_rule(text: str, kind: str, tag: str, prop: str, value: str | None) -> str:
    """Append a new ``kind "tag" { prop value }`` rule after every other rule.

    Raises:
        StyleEditError: for an invalid value, or no value at all.
    """
    checked = check_value(kind, prop, value)
    if checked is None:
        raise StyleEditError("a new style needs a value")
    value = checked
    doc = _Text.of(text)
    lines = _rule_lines(kind, tag, prop, value)
    styles = list(_blocks(doc, "styles"))
    if styles:
        return _insert_lines(doc, styles[-1][1], lines)
    nested = ["styles {", *(_INDENT + line for line in lines), "}"]
    views = list(_blocks(doc, "views"))
    if views:
        return _insert_lines(doc, views[-1][1], nested)
    workspaces = list(_blocks(doc, "workspace"))
    if not workspaces:
        # `workspace "Name" {`: the keyword is followed by arguments, so
        # find the block as the file's outermost one.
        outer = [i for i, tok in enumerate(doc.tokens) if tok.type == LBRACE][:1]
        if not outer:
            raise StyleEditError("no workspace block to add styles to")
        close = _matching(doc.tokens, outer[0])
    else:
        close = workspaces[-1][1]
    return _insert_lines(
        doc, close, ["views {", *(_INDENT + line for line in nested), "}"]
    )


# -- element tags ------------------------------------------------------------


def add_element_tag(text: str, line: int, tag: str) -> str:
    """Give the element defined on ``line`` one more tag, in its body.

    A ``tags "..."`` statement in the element's body adds to the tags its
    definition line carries, so this never touches the positional
    arguments. A definition without a body gets one.

    Raises:
        StyleEditError: when the definition is continued across lines.
    """
    doc = _Text.of(text)
    on_line = [tok for tok in doc.tokens if tok.line == line]
    if not on_line:
        raise StyleEditError(f"no element definition on line {line}")
    raw = doc.text[doc.line_start(line) : doc.line_end(line)].rstrip("\r\n")
    if raw.rstrip().endswith("\\") or '"""' in raw:
        raise StyleEditError("the element's definition continues across lines")
    statement = f'tags "{tag}"'
    last = on_line[-1]
    if last.type == LBRACE:
        close = _matching(doc.tokens, doc.tokens.index(last))
        indent = doc.indent(line) + _INDENT
        at = doc.line_end(line)
        if doc.tokens[close].line == line:
            return _insert_lines(doc, close, [statement])
        return text[:at] + f"{indent}{statement}\n" + text[at:]
    indent = doc.indent(line)
    at = doc.end(last)
    return text[:at] + f" {{\n{indent}{_INDENT}{statement}\n{indent}}}" + text[at:]


# -- the model's tags --------------------------------------------------------


def _deployment_tags(node: DeploymentNode) -> Iterator[set[str]]:
    yield {"Element", "Deployment Node", *node.tags}
    for infra in node.infrastructure_nodes:
        yield {"Element", "Infrastructure Node", *infra.tags}
    for system in node.software_system_instances:
        yield {"Element", "Software System Instance", *system.tags}
    for container in node.container_instances:
        yield {"Element", "Container Instance", *container.tags}
    for child in node.children:
        yield from _deployment_tags(child)


def element_tag_counts(workspace: Workspace) -> Counter[str]:
    """How many model elements carry each tag, the implicit ones included.

    ``Element`` and the kind's own tag (``Container``…) are implicit, as
    style resolution treats them, so a count says how many boxes a rule
    for that tag would paint across the whole model.
    """
    counts: Counter[str] = Counter()
    model = workspace.model
    for person in model.people:
        counts.update({"Element", "Person", *person.tags})
    for custom in model.custom_elements:
        counts.update({"Element", *custom.tags})
    for system in model.software_systems:
        counts.update({"Element", "Software System", *system.tags})
        for container in system.containers:
            counts.update({"Element", "Container", *container.tags})
            for component in container.components:
                counts.update({"Element", "Component", *component.tags})
    for node in model.deployment_nodes:
        for tags in _deployment_tags(node):
            counts.update(tags)
    return counts


def relationship_tag_counts(workspace: Workspace) -> Counter[str]:
    """How many relationships carry each tag, ``Relationship`` included."""
    counts: Counter[str] = Counter()
    for rel in workspace.model.relationships:
        counts.update({"Relationship", *rel.tags})
    return counts


def is_own_tag(tag: str, name: str) -> bool:
    """Whether ``tag`` is one :func:`own_tag_name` would make for ``name``."""
    return tag == name or re.fullmatch(re.escape(name) + r" \d+", tag) is not None


def own_tag_name(name: str, taken: set[str]) -> str:
    """A new tag for one element: its own name, made unique if need be."""
    tag, n = name, 2
    while tag in taken:
        tag, n = f"{name} {n}", n + 1
    return tag
