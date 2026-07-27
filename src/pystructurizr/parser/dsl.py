"""
Structurizr DSL parser.

Supports a subset of the Structurizr DSL spec:
  workspace / model / views blocks, person, softwareSystem, container,
  component elements, -> relationships, and systemContext/container/component views.
"""

from __future__ import annotations

import re
import warnings
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Callable
from typing import Any

from pystructurizr.parser.docs import load_decisions, load_sections, markdown_files
from pystructurizr.parser.expressions import (
    evaluate as evaluate_expression,
    is_expression_term,
    parse_terms,
)
from pystructurizr.diagnostics import Diagnostic, Severity
from pystructurizr.parser.implied import apply_implied_relationships
from pystructurizr.parser.sourcemap import SourceMap
from pystructurizr.models import (
    Animation,
    AutomaticLayout,
    Border,
    Branding,
    ColorScheme,
    Component,
    Container,
    ContainerInstance,
    CustomElement,
    DeploymentNode,
    ElementStyle,
    Enterprise,
    FilterMode,
    HttpHealthCheck,
    IconPosition,
    InfrastructureNode,
    LineStyle,
    Location,
    Person,
    Perspective,
    RankDirection,
    Relationship,
    RelationshipStyle,
    RelationshipView,
    Routing,
    Shape,
    SoftwareSystem,
    SoftwareSystemInstance,
    User,
    View,
    ViewType,
    Workspace,
)


# ---------------------------------------------------------------------------
# Tokeniser
# ---------------------------------------------------------------------------


class TokenType(str):
    pass


_TT = TokenType

IDENT = _TT("IDENT")
STRING = _TT("STRING")
LBRACE = _TT("LBRACE")
RBRACE = _TT("RBRACE")
ARROW = _TT("ARROW")
EQUALS = _TT("EQUALS")
EQEQ = _TT("EQEQ")
NEQ = _TT("NEQ")
DOT = _TT("DOT")
COMMA = _TT("COMMA")
BANG = _TT("BANG")
WILDCARD = _TT("WILDCARD")
COLOR = _TT("COLOR")
NUMBER = _TT("NUMBER")
EOF = _TT("EOF")


@dataclass
class Token:
    """A lexical token and where it sits in the source.

    ``line``/``column`` are 1-based and point at the token's first
    character; ``end_column`` is exclusive, so a diagnostic can underline
    exactly the offending text rather than the whole line.
    """

    type: str
    value: str
    line: int
    column: int = 1
    end_column: int = 1


_TOKEN_RE = re.compile(
    r"(?P<COMMENT>//[^\n]*)|"
    r"(?P<BLOCK_COMMENT>/\*.*?\*/)|"
    r'(?P<STRING>"(?:[^"\\]|\\.)*")|'
    r"(?P<ARROW>->)|"
    r"(?P<EQEQ>==)|"
    r"(?P<NEQ>!=)|"
    r"(?P<EQUALS>=)|"
    r"(?P<DOT>\.)|"
    r"(?P<COMMA>,)|"
    r"(?P<LBRACE>\{)|"
    r"(?P<RBRACE>\})|"
    r"(?P<BANG>!)|"
    r"(?P<WILDCARD>\*)|"
    r"(?P<NEWLINE>\n)|"
    r"(?P<COLOR>#[0-9A-Fa-f]{3,8})|"
    r"(?P<IDENT>[A-Za-z_][A-Za-z0-9_]*)|"
    r"(?P<NUMBER>[0-9]+)|"
    r"(?P<SKIP>[ \t\r]+)",
    re.DOTALL,
)


def _tokenize(text: str) -> list[Token]:
    tokens: list[Token] = []
    line = 1
    # Offset of the first character of `line`, so columns are a subtraction.
    line_start = 0
    for m in _TOKEN_RE.finditer(text):
        kind = m.lastgroup
        value = m.group()
        if kind not in ("COMMENT", "BLOCK_COMMENT", "NEWLINE", "SKIP"):
            column = m.start() - line_start + 1
            tokens.append(
                Token(kind, value, line, column, column + len(value))  # type: ignore[arg-type]
            )
        # Any token may span lines — a block comment, or a string with an
        # escaped newline — so the position is advanced for all of them, not
        # just the ones that are skipped.
        if "\n" in value:
            line += value.count("\n")
            line_start = m.start() + value.rindex("\n") + 1
    column = len(text) - line_start + 1
    tokens.append(Token(EOF, "", line, column, column))
    return tokens


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


_SHAPE_MAP = {shape.value.lower(): shape for shape in Shape}
_BORDER_MAP = {border.value.lower(): border for border in Border}

_LINE_STYLE_MAP = {line_style.value.lower(): line_style for line_style in LineStyle}
_ROUTING_MAP = {routing.value.lower(): routing for routing in Routing}
_ICON_POSITION_MAP = {pos.value.lower(): pos for pos in IconPosition}

# terminology keyword → Terminology attribute
_TERMINOLOGY_FIELDS = {
    "enterprise": "enterprise",
    "person": "person",
    "softwaresystem": "software_system",
    "container": "container",
    "component": "component",
    "code": "code",
    "deploymentnode": "deployment_node",
    "infrastructurenode": "infrastructure_node",
    "relationship": "relationship",
}

_RANK_DIRECTION_MAP = {
    "tb": RankDirection.TOP_BOTTOM,
    "bt": RankDirection.BOTTOM_TOP,
    "lr": RankDirection.LEFT_RIGHT,
    "rl": RankDirection.RIGHT_LEFT,
    "topbottom": RankDirection.TOP_BOTTOM,
    "bottomtop": RankDirection.BOTTOM_TOP,
    "leftright": RankDirection.LEFT_RIGHT,
    "rightleft": RankDirection.RIGHT_LEFT,
}

# Child-element keywords allowed inside each element kind's body.
_CHILD_KEYWORDS: dict[str, tuple[str, ...]] = {
    "softwaresystem": ("container",),
    "container": ("component",),
    "deploymentnode": (
        "deploymentnode",
        "infrastructurenode",
        "softwaresysteminstance",
        "containerinstance",
    ),
}


class ParseError(Exception):
    """A problem that stopped parsing.

    Carries its position as data rather than only inside the message, so
    editors and CI can place it. ``path`` and ``line`` refer to the file
    the problem is actually in — resolved through the include source map,
    so a problem inside an ``!include``-ed fragment names that fragment.
    """

    def __init__(
        self,
        message: str,
        *,
        line: int | None = None,
        column: int | None = None,
        end_column: int | None = None,
        path: Path | None = None,
        code: str = "parse-error",
        diagnostics: list[Diagnostic] | None = None,
    ) -> None:
        super().__init__(message)
        self._diagnostics = diagnostics
        self.message = message
        self.line = line
        self.column = column
        self.end_column = end_column
        self.path = path
        self.code = code

    @property
    def diagnostics(self) -> list[Diagnostic]:
        """Every problem found, in source order.

        Parsing recovers from a bad statement and keeps going, so a file
        with several mistakes reports all of them at once instead of one
        per run. Errors raised before recovery is possible — a circular
        ``!include``, a missing include target — carry just themselves.
        """
        return self._diagnostics or [self.as_diagnostic()]

    def as_diagnostic(self) -> Diagnostic:
        """Return this error as a :class:`Diagnostic`."""
        return Diagnostic(
            message=self.message,
            severity=Severity.ERROR,
            path=self.path,
            line=self.line,
            column=self.column,
            end_column=self.end_column,
            code=self.code,
        )


class UnsupportedFeatureWarning(UserWarning):
    """Warning issued when the DSL uses a feature the parser ignores."""


class _Parser:
    def __init__(
        self, tokens: list[Token], source_map: SourceMap | None = None
    ) -> None:
        self._tokens = tokens
        self._source_map = source_map or SourceMap()
        self._diagnostics: list[Diagnostic] = []
        self._errors: list[Diagnostic] = []
        self._pos = 0
        # maps DSL identifier → element id used in Workspace
        self._id_map: dict[str, str] = {}
        # relationships whose source/destination hold raw DSL identifiers
        # until the whole model has been parsed
        self._rel_buffer: list[Relationship] = []
        self._warnings: list[str] = []
        # active deploymentEnvironment name while parsing its block
        self._current_environment: str = ""
        # active group names while parsing nested group blocks
        self._group_stack: list[str] = []
        # deploymentGroup declarations: alias/name → group name
        self._deployment_groups: dict[str, str] = {}
        # key of the view marked `default`, applied to the configuration
        self._default_view_key: str = ""
        # workspace under construction, for directives that mutate it
        self._ws: Workspace | None = None
        # relationship aliases (`rel = a -> b ...`) for !relationship
        self._rel_aliases: dict[str, Relationship] = {}
        self._implied_relationships = False
        # include/exclude expression lines, resolved once the model is built
        self._pending_expressions: list[tuple[View, str, list[tuple[str, str]]]] = []

    @property
    def _current_group(self) -> str:
        return "/".join(g for g in self._group_stack if g)

    def _peek(self) -> Token:
        # Clamped to the trailing EOF token: recovery can be entered with the
        # position already past the end, and every loop terminates on EOF.
        if self._pos >= len(self._tokens):
            return self._tokens[-1]
        return self._tokens[self._pos]

    def _advance(self) -> Token:
        tok = self._peek()
        if self._pos < len(self._tokens):
            self._pos += 1
        return tok

    def _expect(self, type_: str) -> Token:
        tok = self._advance()
        if tok.type != type_:
            raise ParseError(
                f"expected {type_}, got {tok.type!r} ({tok.value!r})",
                line=tok.line,
                column=tok.column,
                end_column=tok.end_column,
                code="unexpected-token",
            )
        return tok

    def _match(self, *types: str) -> bool:
        return self._peek().type in types

    def _peek_value(self) -> str:
        return self._peek().value

    def _optional_string(self) -> str:
        if self._match(STRING):
            return self._advance().value.strip('"')
        return ""

    def _parse_string(self) -> str:
        return self._expect(STRING).value.strip('"')

    def parse(self) -> Workspace:
        ws = self._parse_workspace()
        # resolve buffered relationships
        for rel in self._rel_buffer:
            rel.source_id = self._id_map.get(rel.source_id, rel.source_id)
            rel.destination_id = self._id_map.get(
                rel.destination_id, rel.destination_id
            )
            ws.relationships.append(rel)
        if self._implied_relationships:
            apply_implied_relationships(ws)
        self._resolve_pending_expressions(ws)
        if self._default_view_key:
            ws.views.configuration.default_view = self._default_view_key
        ws.parse_warnings = self._warnings
        ws.diagnostics = self._diagnostics
        if self._errors:
            # Recovery let parsing continue past each bad statement so every
            # problem could be found; the contract that a broken file raises
            # is kept, with all of them attached.
            first = self._errors[0]
            raise ParseError(
                first.message,
                line=first.line,
                column=first.column,
                end_column=first.end_column,
                path=first.path,
                code=first.code,
                diagnostics=[*self._errors, *self._diagnostics],
            )
        return ws

    def _parse_workspace(self) -> Workspace:
        self._expect_keyword("workspace")
        name = self._optional_string()
        description = self._optional_string()
        self._expect(LBRACE)

        ws = Workspace(name=name, description=description)
        self._ws = ws

        while not self._match(RBRACE, EOF):
            before = self._pos
            self._guard(lambda: self._parse_workspace_item(ws))
            if self._pos == before:
                self._advance()

        if self._match(RBRACE):
            self._advance()
        return ws

    def _parse_workspace_item(self, ws: Workspace) -> None:
        """Parse one statement of the workspace block."""
        if self._match(BANG):
            self._parse_directive("workspace")
            return
        kw = self._peek_value().lower()
        if kw == "model":
            self._parse_model(ws)
        elif kw == "views":
            self._parse_views(ws)
        elif kw == "configuration":
            self._advance()
            self._parse_workspace_configuration(ws)
        elif kw == "name":
            self._advance()
            value = self._optional_string()
            if value:
                ws.name = value
        elif kw == "description":
            self._advance()
            value = self._optional_string()
            if value:
                ws.description = value
        elif kw == "properties":
            self._advance()
            # structurizr-java stores workspace properties on the views
            # configuration.
            ws.views.configuration.properties.update(self._parse_properties_block())
        else:
            self._skip_unknown("workspace")

    def _parse_workspace_configuration(self, ws: Workspace) -> None:
        """Parse ``configuration { scope, visibility, users { ... } }``."""
        if not self._match(LBRACE):
            return
        self._expect(LBRACE)
        config = ws.workspace_configuration
        while not self._match(RBRACE, EOF):
            if not self._match(IDENT):
                self._advance()
                continue
            kw = self._advance().value.lower()
            if kw == "scope":
                config.scope = self._optional_ident() or self._optional_string()
            elif kw == "visibility":
                config.visibility = self._optional_ident() or self._optional_string()
            elif kw == "users" and self._match(LBRACE):
                self._expect(LBRACE)
                while not self._match(RBRACE, EOF):
                    if self._match(IDENT, STRING):
                        username = self._advance().value.strip('"')
                        role = self._optional_ident() or self._optional_string()
                        config.users.append(User(username=username, role=role))
                    else:
                        self._advance()
                self._expect(RBRACE)
            elif self._match(LBRACE):
                self._skip_block()
        self._expect(RBRACE)

    def _optional_ident(self) -> str:
        if self._match(IDENT):
            return self._advance().value
        return ""

    def _resolve_id(self, ref: str) -> str:
        return self._id_map.get(ref, ref)

    def _ensure_rel_id(self, ws: Workspace, rel: Relationship) -> str:
        """Return the relationship's id, assigning the next free one if unset."""
        if not rel.id:
            taken = {r.id for r in ws.relationships if r.id}
            n = 1
            while str(n) in taken:
                n += 1
            rel.id = str(n)
        return rel.id

    def _resolve_pending_expressions(self, ws: Workspace) -> None:
        """Resolve deferred include/exclude expression lines against the model."""
        for view, mode, tokens in self._pending_expressions:
            outcome = evaluate_expression(
                parse_terms(tokens), ws, ws.relationships, self._resolve_id
            )
            if mode == "include":
                for eid in sorted(outcome.element_ids):
                    if eid not in view.included_ids:
                        view.included_ids.append(eid)
            else:
                for eid in sorted(outcome.element_ids):
                    if eid not in view.excluded_ids:
                        view.excluded_ids.append(eid)
                for rel in outcome.relationships:
                    rel_id = self._ensure_rel_id(ws, rel)
                    if rel_id not in view.excluded_relationship_ids:
                        view.excluded_relationship_ids.append(rel_id)

    def _capture_expression_line(self, view: View, mode: str, line: int) -> bool:
        """Defer an include/exclude line to the expression engine if needed.

        Returns True (and consumes the line) when it contains expression
        syntax; plain identifier lists return False and take the fast path.
        """
        i = self._pos
        collected: list[tuple[str, str]] = []
        while i < len(self._tokens):
            tok = self._tokens[i]
            if tok.line != line or tok.type in (LBRACE, RBRACE, EOF):
                break
            collected.append((tok.type, tok.value))
            i += 1
        if not collected or not is_expression_term(collected):
            return False
        self._pos = i
        text = " ".join(value for _, value in collected)
        if mode == "include":
            view.include_expressions.append(text)
        else:
            view.exclude_expressions.append(text)
        self._pending_expressions.append((view, mode, collected))
        return True

    def _collect_expression_tokens(self, line: int) -> list[tuple[str, str]]:
        """Consume and return the raw expression tokens remaining on ``line``."""
        collected: list[tuple[str, str]] = []
        while not self._match(LBRACE, RBRACE, EOF) and self._peek().line == line:
            tok = self._advance()
            collected.append((tok.type, tok.value))
        return collected

    def _idents_on_line(self, line: int) -> list[str]:
        """Consume identifiers that remain on ``line``, resolved to element ids.

        Used for view ``include``/``exclude`` statements, which may name
        several elements on one line; identifiers on later lines belong to
        the next view statement.
        """
        resolved: list[str] = []
        while self._match(IDENT) and self._peek().line == line:
            raw = self._advance().value
            resolved.append(self._id_map.get(raw, raw))
        return resolved

    def _expect_keyword(self, kw: str) -> None:
        tok = self._advance()
        if tok.type != IDENT or tok.value.lower() != kw:
            raise ParseError(
                f"expected keyword {kw!r}, got {tok.value!r}",
                line=tok.line,
                column=tok.column,
                end_column=tok.end_column,
                code="unexpected-keyword",
            )

    def _parse_directive(self, scope: str) -> None:
        """Parse a ``!directive`` encountered at the given scope.

        Known directives dispatch to a ``_directive_<name>`` method; unknown
        ones are skipped (their same-line arguments plus any ``{...}`` block)
        and recorded as an unsupported-feature warning.
        """
        self._expect(BANG)
        if not self._match(IDENT):
            return
        name_tok = self._advance()
        handler = getattr(self, f"_directive_{name_tok.value.lower()}", None)
        if handler is not None:
            handler(scope, name_tok.line)
            return
        while (
            self._match(IDENT, STRING, NUMBER, COLOR, WILDCARD, EQUALS, DOT, COMMA)
            and self._peek().line == name_tok.line
        ):
            self._advance()
        if self._match(LBRACE):
            self._skip_block()
        self._warn(
            f"Line {name_tok.line}: unsupported directive '!{name_tok.value}' ignored"
        )

    def _directive_identifiers(self, scope: str, line: int) -> None:
        # hierarchical|flat — identifier scoping is not yet implemented;
        # flat resolution applies regardless of the requested mode.
        if self._match(IDENT) and self._peek().line == line:
            self._advance()

    def _directive_impliedrelationships(self, scope: str, line: int) -> None:
        value = ""
        if self._match(IDENT) and self._peek().line == line:
            value = self._advance().value.lower()
        self._implied_relationships = value == "true"

    def _directive_element(self, scope: str, line: int) -> None:
        """``!element <identifier> { ... }`` — extend an existing element."""
        ref = self._optional_ident() or self._optional_string()
        element = None
        if self._ws is not None and ref:
            element = self._ws.find_element(self._id_map.get(ref, ref))
        if element is None or self._ws is None:
            if self._match(LBRACE):
                self._skip_block()
            return
        if self._match(LBRACE):
            kind = type(element).__name__.lower()
            if kind == "customelement":
                kind = "element"
            self._parse_element_body(self._ws, element, kind)

    def _directive_relationship(self, scope: str, line: int) -> None:
        """``!relationship <alias> { ... }`` — extend an aliased relationship."""
        ref = self._optional_ident() or self._optional_string()
        rel = self._rel_aliases.get(ref)
        if rel is not None and self._match(LBRACE):
            self._parse_relationship_body(rel)
        elif self._match(LBRACE):
            self._skip_block()

    def _directive_elements(self, scope: str, line: int) -> None:
        """``!elements <expression> { ... }`` — bulk-modify matching elements."""
        tokens = self._collect_expression_tokens(line)
        if not self._match(LBRACE):
            return
        targets: list[Any] = []
        if self._ws is not None and tokens:
            outcome = evaluate_expression(
                parse_terms(tokens), self._ws, self._rel_buffer, self._resolve_id
            )
            for eid in sorted(outcome.element_ids):
                element = self._ws.find_element(eid)
                if element is not None:
                    targets.append(element)
        if not targets or self._ws is None:
            self._skip_block()
            return
        # the body applies to every matched element: re-parse it per target
        start = self._pos
        for element in targets:
            self._pos = start
            kind = type(element).__name__.lower()
            if kind == "customelement":
                kind = "element"
            self._parse_element_body(self._ws, element, kind)

    def _directive_relationships(self, scope: str, line: int) -> None:
        """``!relationships <expression> { ... }`` — bulk-modify relationships."""
        tokens = self._collect_expression_tokens(line)
        if not self._match(LBRACE):
            return
        matched: list[Relationship] = []
        if self._ws is not None and tokens:
            outcome = evaluate_expression(
                parse_terms(tokens), self._ws, self._rel_buffer, self._resolve_id
            )
            matched = outcome.relationships
        if not matched:
            self._skip_block()
            return
        start = self._pos
        for rel in matched:
            self._pos = start
            self._parse_relationship_body(rel)

    # A file broken enough to produce this many problems is not being
    # helped by more of them, and an editor should not render hundreds.
    _MAX_ERRORS = 50

    def _record_error(self, error: ParseError) -> None:
        """Store a recovered error, resolved to its originating file."""
        path, line = error.path, error.line
        if path is None and line is not None:
            path, line = self._source_map.resolve(line)
        diagnostic = Diagnostic(
            message=error.message,
            severity=Severity.ERROR,
            path=path,
            line=line,
            column=error.column,
            end_column=error.end_column,
            code=error.code,
        )
        # Recovery can re-report the same spot from a different rule; the
        # user only needs to be told once.
        key = (diagnostic.path, diagnostic.line, diagnostic.column, diagnostic.message)
        if any(
            (d.path, d.line, d.column, d.message) == key for d in self._errors
        ):
            return
        if len(self._errors) < self._MAX_ERRORS:
            self._errors.append(diagnostic)

    def _recover(self, failed_line: int) -> None:
        """Skip the rest of a failed statement, no more than that.

        The DSL is line-oriented, so the remainder of the statement is what
        shares its starting line; the next token on a later line resumes
        parsing. Anchoring to the *failed* statement's line matters: by the
        time the error surfaces the position is often already on the next
        statement, and skipping from there would swallow a statement that
        was never given a chance — hiding the very errors this exists to
        find. Blocks opened while skipping are consumed whole so their
        contents are not reparsed as statements of the enclosing scope.
        """
        depth = 0
        while not self._match(EOF):
            tok = self._peek()
            if depth == 0:
                if tok.type == RBRACE:
                    return  # let the enclosing loop close its block
                if tok.line != failed_line:
                    return  # next statement
            self._advance()
            if tok.type == LBRACE:
                depth += 1
            elif tok.type == RBRACE:
                depth -= 1
                if depth <= 0:
                    return

    def _guard(self, parse: Callable[[], None]) -> None:
        """Run one statement, recovering from a parse error within it."""
        start_line = self._peek().line
        start_pos = self._pos
        try:
            parse()
        except ParseError as error:
            self._record_error(error)
            self._recover(start_line)
            # Guarantee progress, or the enclosing loop spins on the token
            # that failed.
            if self._pos == start_pos:
                self._advance()

    def _warn(
        self,
        message: str,
        line: int | None = None,
        code: str = "",
        column: int | None = None,
        end_column: int | None = None,
    ) -> None:
        """Record a skipped or ignored construct.

        ``line`` is a line of the flattened source and is resolved back to
        the file it came from, so a problem inside an ``!include``-ed
        fragment names that fragment rather than the file that included it.
        """
        path, origin_line = (
            self._source_map.resolve(line) if line is not None else (None, None)
        )
        self._diagnostics.append(
            Diagnostic(
                message=message,
                severity=Severity.WARNING,
                path=path,
                line=origin_line,
                column=column,
                end_column=end_column,
                code=code,
            )
        )
        self._warnings.append(message)
        warnings.warn(message, UnsupportedFeatureWarning, stacklevel=2)

    def _parse_model(self, ws: Workspace) -> None:
        self._advance()  # consume 'model'
        self._expect(LBRACE)
        while not self._match(RBRACE, EOF):
            self._guard(lambda: self._parse_model_item(ws, parent_id=None))
        self._expect(RBRACE)

    def _parse_model_item(self, ws: Workspace, parent_id: str | None) -> None:
        tok = self._peek()

        if tok.type == BANG:
            self._parse_directive("model")
            return

        # relationship: source -> dest ...
        if tok.type == IDENT and self._lookahead_is_arrow():
            self._parse_relationship()
            return

        # assignment: identifier = element_type ... or identifier = a -> b
        if tok.type == IDENT and self._lookahead_is_equals():
            alias = self._advance().value
            self._expect(EQUALS)
            if self._peek().type == IDENT and self._lookahead_is_arrow():
                self._parse_relationship()
                self._rel_aliases[alias] = self._rel_buffer[-1]
                return
            self._parse_element(ws, alias, parent_id)
            return

        # keyword elements without alias
        if tok.type == IDENT:
            kw = tok.value.lower()
            if kw in (
                "person",
                "softwaresystem",
                "container",
                "component",
                "deploymentnode",
                "infrastructurenode",
                "softwaresysteminstance",
                "containerinstance",
                "deploymentgroup",
                "element",
            ):
                self._parse_element(ws, alias=None, parent_id=parent_id)
                return
            if kw == "enterprise":
                self._parse_enterprise(ws)
                return
            if kw == "group":
                self._parse_group(ws, parent_id)
                return
            if kw == "deploymentenvironment":
                self._parse_deployment_environment(ws)
                return
            if kw == "properties":
                self._advance()
                ws.model.properties.update(self._parse_properties_block())
                return

        self._skip_unknown("model")

    def _lookahead_is_arrow(self) -> bool:
        # Relationships are single-line statements; scanning past the line
        # would match an unrelated `->` on a following line.
        line = self._peek().line
        i = self._pos + 1
        while (
            i < len(self._tokens)
            and self._tokens[i].type in (IDENT, STRING)
            and self._tokens[i].line == line
        ):
            i += 1
        return (
            i < len(self._tokens)
            and self._tokens[i].type == ARROW
            and self._tokens[i].line == line
        )

    def _lookahead_is_equals(self) -> bool:
        return (
            self._pos + 1 < len(self._tokens)
            and self._tokens[self._pos + 1].type == EQUALS
        )

    def _parse_element(
        self, ws: Workspace, alias: str | None, parent_id: str | None
    ) -> None:
        kw_tok = self._advance()
        kw = kw_tok.value.lower()
        if kw in ("softwaresysteminstance", "containerinstance"):
            self._parse_instance(ws, kw, alias, parent_id, kw_tok.line)
            return
        name = self._optional_string()
        # element <name> [metadata] [description] [tags] — custom elements
        # take a metadata string before the description.
        metadata = self._optional_string() if kw == "element" else ""
        description = self._optional_string()
        technology = (
            self._optional_string()
            if kw in ("container", "component", "deploymentnode", "infrastructurenode")
            else ""
        )
        tags_str = self._optional_string()
        tags = [t.strip() for t in tags_str.split(",")] if tags_str else []

        # deploymentNode <name> [description] [technology] [tags] [instances]
        instances = 1
        if kw == "deploymentnode":
            if self._match(NUMBER):
                instances = int(self._advance().value)
            elif self._match(STRING):
                raw = self._advance().value.strip('"')
                if raw.isdigit():
                    instances = int(raw)  # ranges like "0..N" keep the default

        elem_id = alias or name.replace(" ", "_").lower()

        if kw == "person":
            location = Location.EXTERNAL if "External" in tags else Location.UNSPECIFIED
            elem = Person(
                id=elem_id,
                name=name,
                description=description,
                tags=tags,
                location=location,
                group=self._current_group,
            )
            ws.people.append(elem)
            if alias:
                self._id_map[alias] = elem_id
            if self._match(LBRACE):
                self._parse_element_body(ws, elem, "person")
        elif kw == "softwaresystem":
            location = Location.EXTERNAL if "External" in tags else Location.UNSPECIFIED
            sys_elem = SoftwareSystem(
                id=elem_id,
                name=name,
                description=description,
                tags=tags,
                location=location,
                group=self._current_group,
            )
            ws.software_systems.append(sys_elem)
            if alias:
                self._id_map[alias] = elem_id
            if self._match(LBRACE):
                self._parse_element_body(ws, sys_elem, "softwaresystem")
        elif kw == "container":
            system = self._find_system(ws, parent_id)
            if system is not None:
                c = Container(
                    id=elem_id,
                    name=name,
                    description=description,
                    technology=technology,
                    tags=tags,
                    parent_id=system.id,
                    group=self._current_group,
                )
                system.containers.append(c)
                if alias:
                    self._id_map[alias] = elem_id
                if self._match(LBRACE):
                    self._parse_element_body(ws, c, "container")
        elif kw == "component":
            container = self._find_container(ws, parent_id)
            if container is not None:
                comp = Component(
                    id=elem_id,
                    name=name,
                    description=description,
                    technology=technology,
                    tags=tags,
                    parent_id=container.id,
                    group=self._current_group,
                )
                container.components.append(comp)
                if alias:
                    self._id_map[alias] = elem_id
                if self._match(LBRACE):
                    self._parse_element_body(ws, comp, "component")
        elif kw == "deploymentnode":
            parent_node = self._find_deployment_node(ws, parent_id)
            node = DeploymentNode(
                id=elem_id,
                name=name,
                description=description,
                technology=technology,
                instances=instances,
                tags=tags,
                environment=self._current_environment,
                parent_id=parent_node.id if parent_node is not None else "",
                group=self._current_group,
            )
            if parent_node is not None:
                parent_node.children.append(node)
            else:
                ws.deployment_nodes.append(node)
            if alias:
                self._id_map[alias] = elem_id
            if self._match(LBRACE):
                self._parse_element_body(ws, node, "deploymentnode")
        elif kw == "infrastructurenode":
            parent_node = self._find_deployment_node(ws, parent_id)
            infra = InfrastructureNode(
                id=elem_id,
                name=name,
                description=description,
                technology=technology,
                tags=tags,
                parent_id=parent_node.id if parent_node is not None else "",
                group=self._current_group,
            )
            if parent_node is not None:
                parent_node.infrastructure_nodes.append(infra)
            if alias:
                self._id_map[alias] = elem_id
            if self._match(LBRACE):
                self._parse_element_body(ws, infra, "infrastructurenode")
        elif kw == "deploymentgroup":
            # deploymentGroup declarations only feed the parser registry;
            # membership is recorded on instances, not the workspace.
            if name:
                self._deployment_groups[name] = name
                if alias:
                    self._deployment_groups[alias] = name
        elif kw == "element":
            custom = CustomElement(
                id=elem_id,
                name=name,
                metadata=metadata,
                description=description,
                tags=tags,
                group=self._current_group,
            )
            ws.model.custom_elements.append(custom)
            if alias:
                self._id_map[alias] = elem_id
            if self._match(LBRACE):
                self._parse_element_body(ws, custom, "element")

    def _parse_instance(
        self,
        ws: Workspace,
        kw: str,
        alias: str | None,
        parent_id: str | None,
        line: int,
    ) -> None:
        """Parse ``softwareSystemInstance``/``containerInstance``.

        Syntax: ``<keyword> <identifier> [deploymentGroups] [tags]`` — a
        positional argument whose comma-separated items all name declared
        deployment groups is the group list; anything else is tags.
        """
        ref = ""
        if self._match(IDENT) and self._peek().line == line:
            ref = self._advance().value
        elif self._match(STRING) and self._peek().line == line:
            ref = self._advance().value.strip('"')

        deployment_groups: list[str] = []
        tags: list[str] = []
        while self._match(STRING, IDENT) and self._peek().line == line:
            raw = self._advance().value.strip('"')
            items = [t.strip() for t in raw.split(",") if t.strip()]
            if items and all(item in self._deployment_groups for item in items):
                deployment_groups.extend(self._deployment_groups[i] for i in items)
            else:
                tags.extend(items)

        target_id = self._id_map.get(ref, ref)
        inst_id = alias or self._unique_id(f"{target_id}_instance")
        parent_node = self._find_deployment_node(ws, parent_id)
        if kw == "softwaresysteminstance":
            inst = SoftwareSystemInstance(
                id=inst_id,
                software_system_id=target_id,
                environment=self._current_environment,
                deployment_groups=deployment_groups,
                tags=tags,
            )
            if parent_node is not None:
                parent_node.software_system_instances.append(inst)
            self._id_map[alias or inst_id] = inst_id
            if self._match(LBRACE):
                self._parse_element_body(ws, inst, kw)
        else:
            cont_inst = ContainerInstance(
                id=inst_id,
                container_id=target_id,
                environment=self._current_environment,
                deployment_groups=deployment_groups,
                tags=tags,
            )
            if parent_node is not None:
                parent_node.container_instances.append(cont_inst)
            self._id_map[alias or inst_id] = inst_id
            if self._match(LBRACE):
                self._parse_element_body(ws, cont_inst, kw)

    def _parse_element_body(self, ws: Workspace, element: Any, kind: str) -> None:
        """Parse the ``{ ... }`` body shared by every element kind.

        Handles the metadata keywords common to all elements, relationships,
        directives, ``group`` blocks, and the child-element keywords valid
        for ``kind``; anything else is skipped.
        """
        self._expect(LBRACE)
        children = _CHILD_KEYWORDS.get(kind, ())
        # Group context does not cross parent boundaries: a container of a
        # grouped system is not itself in the group (structurizr-java).
        saved_groups = self._group_stack
        self._group_stack = []
        while not self._match(RBRACE, EOF):
            before = self._pos
            self._guard(
                lambda: self._parse_element_body_item(ws, element, kind, children)
            )
            # A guard that recovered without consuming anything would spin.
            if self._pos == before:
                self._advance()
        self._expect(RBRACE)
        self._group_stack = saved_groups

    def _parse_element_body_item(
        self, ws: Workspace, element: Any, kind: str, children: tuple[str, ...]
    ) -> None:
        """Parse one statement of an element body."""
        tok = self._peek()
        if tok.type == BANG:
            self._parse_directive("element")
            return
        if tok.type == ARROW or (tok.type == IDENT and self._lookahead_is_arrow()):
            self._parse_relationship(this_id=element.id)
            return
        if tok.type == IDENT and self._lookahead_is_equals():
            alias = self._advance().value
            self._expect(EQUALS)
            if self._peek().value.lower() in children:
                self._parse_element(ws, alias=alias, parent_id=element.id)
            else:
                self._advance()
            return
        if tok.type == IDENT:
            kw = tok.value.lower()
            if kw in children:
                self._parse_element(ws, alias=None, parent_id=element.id)
                return
            if kw == "group":
                self._parse_group(ws, element.id)
                return
            if self._parse_common_element_keyword(element, kw):
                return
        self._skip_unknown(kind)

    def _parse_common_element_keyword(self, element: Any, kw: str) -> bool:
        """Handle a metadata keyword valid on any element; True if handled."""
        if kw == "description" and hasattr(element, "description"):
            self._advance()
            element.description = self._optional_string()
            return True
        if kw == "technology" and hasattr(element, "technology"):
            self._advance()
            element.technology = self._optional_string()
            return True
        if kw == "url" and hasattr(element, "url"):
            self._advance()
            # URLs must be quoted (the tokenizer has no unquoted-URL token)
            element.url = self._optional_string()
            return True
        if kw in ("tag", "tags") and hasattr(element, "tags"):
            line = self._advance().line
            while self._match(STRING) and self._peek().line == line:
                raw = self._advance().value.strip('"')
                element.tags.extend(t.strip() for t in raw.split(",") if t.strip())
            return True
        if kw == "properties" and hasattr(element, "properties"):
            self._advance()
            element.properties.update(self._parse_properties_block())
            return True
        if kw == "perspectives" and hasattr(element, "perspectives"):
            self._advance()
            element.perspectives.extend(self._parse_perspectives_block())
            return True
        if kw == "healthcheck" and hasattr(element, "health_checks"):
            # healthCheck <name> <url> [interval] [timeout]
            self._advance()
            check = HttpHealthCheck(
                name=self._optional_string(), url=self._optional_string()
            )
            if self._match(NUMBER):
                check.interval = int(self._advance().value)
            if self._match(NUMBER):
                check.timeout = int(self._advance().value)
            element.health_checks.append(check)
            return True
        return False

    def _dotted_token(self, line: int) -> str:
        """Consume one value token, joining ``a.b.c`` dotted runs on ``line``."""
        parts = [self._advance().value.strip('"')]
        while (
            self._match(DOT)
            and self._peek().line == line
            and self._pos + 1 < len(self._tokens)
            and self._tokens[self._pos + 1].type in (IDENT, NUMBER)
            and self._tokens[self._pos + 1].line == line
        ):
            self._advance()  # consume '.'
            parts.append(self._advance().value)
        return ".".join(parts)

    def _parse_properties_block(self) -> dict[str, str]:
        """Parse ``{ <name> <value> ... }`` name/value pairs, one per line."""
        props: dict[str, str] = {}
        if not self._match(LBRACE):
            return props
        self._expect(LBRACE)
        while not self._match(RBRACE, EOF):
            if not self._match(STRING, IDENT, NUMBER, COLOR):
                self._advance()
                continue
            line = self._peek().line
            name = self._dotted_token(line)
            value = ""
            if self._match(STRING, IDENT, NUMBER, COLOR) and self._peek().line == line:
                value = self._dotted_token(line)
            # extra tokens on the same line are ignored
            while (
                self._match(STRING, IDENT, NUMBER, COLOR, DOT, COMMA)
                and self._peek().line == line
            ):
                self._advance()
            props[name] = value
        self._expect(RBRACE)
        return props

    def _parse_perspectives_block(self) -> list[Perspective]:
        """Parse ``{ <name> <description> [value] ... }`` lines."""
        perspectives: list[Perspective] = []
        if not self._match(LBRACE):
            return perspectives
        self._expect(LBRACE)
        while not self._match(RBRACE, EOF):
            if not self._match(STRING, IDENT):
                self._advance()
                continue
            tok = self._advance()
            values = [tok.value.strip('"')]
            while self._match(STRING, IDENT) and self._peek().line == tok.line:
                values.append(self._advance().value.strip('"'))
            perspectives.append(
                Perspective(
                    name=values[0],
                    description=values[1] if len(values) > 1 else "",
                    value=values[2] if len(values) > 2 else "",
                )
            )
        self._expect(RBRACE)
        return perspectives

    def _parse_enterprise(self, ws: Workspace) -> None:
        self._advance()  # consume 'enterprise'
        name = self._optional_string()
        ws.enterprise = Enterprise(name=name)
        if self._match(LBRACE):
            self._expect(LBRACE)
            while not self._match(RBRACE, EOF):
                self._parse_model_item(ws, parent_id=None)
            self._expect(RBRACE)

    def _parse_group(self, ws: Workspace, parent_id: str | None) -> None:
        """Parse ``group "Name" { ... }``; members record the group path.

        Nested group paths join with ``/`` and set the
        ``structurizr.groupSeparator`` model property, matching
        structurizr-java.
        """
        self._advance()  # consume 'group'
        name = self._optional_string()
        self._group_stack.append(name)
        if len(self._group_stack) > 1:
            ws.model.properties.setdefault("structurizr.groupSeparator", "/")
        if self._match(LBRACE):
            self._expect(LBRACE)
            while not self._match(RBRACE, EOF):
                self._parse_model_item(ws, parent_id)
            self._expect(RBRACE)
        self._group_stack.pop()

    def _parse_deployment_environment(self, ws: Workspace) -> None:
        """Parse ``deploymentEnvironment "Name" { ... }``.

        Deployment nodes and instances created inside the block are stamped
        with the environment name so deployment views can filter on it.
        """
        self._advance()  # consume keyword
        env_name = self._optional_string() or self._optional_ident()
        if env_name and env_name not in ws.model.deployment_environments:
            ws.model.deployment_environments.append(env_name)
        previous = self._current_environment
        self._current_environment = env_name
        if self._match(LBRACE):
            self._expect(LBRACE)
            while not self._match(RBRACE, EOF):
                self._parse_model_item(ws, parent_id=None)
            self._expect(RBRACE)
        self._current_environment = previous

    def _unique_id(self, base: str) -> str:
        """Return ``base`` or a numbered variant not yet used as an id."""
        taken = set(self._id_map.values())
        if base not in taken:
            return base
        n = 2
        while f"{base}_{n}" in taken:
            n += 1
        return f"{base}_{n}"

    def _parse_relationship(self, this_id: str | None = None) -> None:
        if self._match(ARROW):
            # implicit source: `-> dst ...` inside an element body
            self._advance()
            src = this_id or ""
        else:
            src = self._advance().value
            self._expect(ARROW)
        dst = self._advance().value
        if this_id is not None:
            if src.lower() == "this":
                src = this_id
            if dst.lower() == "this":
                dst = this_id
        description = self._optional_string()
        technology = self._optional_string()
        # source/destination hold raw DSL identifiers; parse() resolves them
        # once the whole model is known.
        rel = Relationship(
            source_id=src,
            destination_id=dst,
            description=description,
            technology=technology,
        )
        tags_str = self._optional_string()
        if tags_str:
            rel.tags.extend(t.strip() for t in tags_str.split(",") if t.strip())
        if self._match(LBRACE):
            self._parse_relationship_body(rel)
        self._rel_buffer.append(rel)

    def _parse_relationship_body(self, rel: Relationship) -> None:
        """Parse a relationship's nested block: tags, url, properties, perspectives."""
        self._expect(LBRACE)
        while not self._match(RBRACE, EOF):
            if not self._match(IDENT):
                self._advance()
                continue
            kw = self._peek_value().lower()
            if kw in ("tag", "tags"):
                line = self._advance().line
                while self._match(STRING) and self._peek().line == line:
                    raw = self._advance().value.strip('"')
                    rel.tags.extend(t.strip() for t in raw.split(",") if t.strip())
            elif kw == "url":
                self._advance()
                rel.url = self._optional_string()
            elif kw == "properties":
                self._advance()
                rel.properties.update(self._parse_properties_block())
            elif kw == "perspectives":
                self._advance()
                rel.perspectives.extend(self._parse_perspectives_block())
            else:
                self._advance()
        self._expect(RBRACE)

    def _parse_views(self, ws: Workspace) -> None:
        self._advance()  # consume 'views'
        self._expect(LBRACE)
        while not self._match(RBRACE, EOF):
            tok = self._peek()
            if tok.type == BANG:
                self._parse_directive("views")
                continue
            if tok.type != IDENT:
                self._advance()
                continue
            kw = tok.value.lower()
            if kw == "systemlandscape":
                ws.views.append(self._parse_view(ViewType.SYSTEM_LANDSCAPE))
            elif kw == "systemcontext":
                ws.views.append(self._parse_view(ViewType.SYSTEM_CONTEXT))
            elif kw == "container":
                ws.views.append(self._parse_view(ViewType.CONTAINER))
            elif kw == "component":
                ws.views.append(self._parse_view(ViewType.COMPONENT))
            elif kw == "dynamic":
                ws.views.append(self._parse_view(ViewType.DYNAMIC))
            elif kw == "deployment":
                ws.views.append(self._parse_view(ViewType.DEPLOYMENT))
            elif kw == "custom":
                ws.views.append(self._parse_view(ViewType.CUSTOM))
            elif kw == "image":
                ws.views.append(self._parse_image_view())
            elif kw == "styles":
                self._parse_styles(ws)
            elif kw in ("theme", "themes"):
                # theme "url" / themes "url" "url" ... — URLs must be quoted
                # (the tokenizer has no token for unquoted ://... runs).
                self._advance()
                while self._match(STRING):
                    url = self._advance().value.strip('"')
                    if url:
                        ws.views.configuration.themes.append(url)
            elif kw == "filtered":
                ws.views.append(self._parse_filtered_view())
            elif kw == "branding":
                self._advance()
                self._parse_branding(ws)
            elif kw == "terminology":
                self._advance()
                self._parse_terminology(ws)
            else:
                self._skip_unknown("views")
        self._expect(RBRACE)

    def _parse_branding(self, ws: Workspace) -> None:
        """Parse ``branding { logo <url> font <name> [url] }``."""
        if not self._match(LBRACE):
            return
        self._expect(LBRACE)
        branding = ws.views.configuration.branding or Branding()
        while not self._match(RBRACE, EOF):
            if not self._match(IDENT):
                self._advance()
                continue
            kw = self._advance().value.lower()
            if kw == "logo":
                branding.logo = self._optional_string()
            elif kw == "font":
                branding.font = self._optional_string()
                self._optional_string()  # optional web font url, not stored
        self._expect(RBRACE)
        ws.views.configuration.branding = branding

    def _parse_terminology(self, ws: Workspace) -> None:
        """Parse ``terminology { <element kind> <label> ... }``."""
        if not self._match(LBRACE):
            return
        self._expect(LBRACE)
        terminology = ws.views.configuration.terminology
        while not self._match(RBRACE, EOF):
            if not self._match(IDENT):
                self._advance()
                continue
            kw = self._advance().value.lower()
            attr = _TERMINOLOGY_FIELDS.get(kw)
            value = self._optional_string()
            if attr and value:
                setattr(terminology, attr, value)
        self._expect(RBRACE)

    def _parse_styles(self, ws: Workspace) -> None:
        """Parse a views-level ``styles`` block into the view configuration.

        Supports ``element "Tag" { ... }`` and ``relationship "Tag" { ... }``
        rules; unknown rule kinds and properties are skipped.
        """
        self._advance()  # consume 'styles'
        if not self._match(LBRACE):
            return
        self._expect(LBRACE)
        styles = ws.views.configuration.styles
        while not self._match(RBRACE, EOF):
            kw = self._peek_value().lower() if self._match(IDENT) else ""
            if kw == "element":
                self._advance()
                style = ElementStyle(tag=self._optional_string())
                variants = self._parse_element_style_body(style)
                styles.element_styles.append(style)
                styles.element_styles.extend(variants)
            elif kw == "relationship":
                self._advance()
                rel_style = RelationshipStyle(tag=self._optional_string())
                rel_variants = self._parse_relationship_style_body(rel_style)
                styles.relationship_styles.append(rel_style)
                styles.relationship_styles.extend(rel_variants)
            else:
                self._advance()
        self._expect(RBRACE)

    def _style_value(self) -> str:
        """Consume and return one style property value token, if present."""
        if self._match(COLOR, STRING):
            return self._advance().value.strip('"')
        if self._match(IDENT, NUMBER):
            return self._advance().value
        return ""

    def _parse_element_style_body(self, style: ElementStyle) -> list[ElementStyle]:
        """Parse an element style block; returns light/dark variant styles."""
        variants: list[ElementStyle] = []
        if not self._match(LBRACE):
            return variants
        self._expect(LBRACE)
        while not self._match(RBRACE, EOF):
            if not self._match(IDENT):
                self._advance()
                continue
            prop = self._advance().value.lower()
            if prop in ("light", "dark") and self._match(LBRACE):
                variant = ElementStyle(
                    tag=style.tag,
                    color_scheme=(
                        ColorScheme.LIGHT if prop == "light" else ColorScheme.DARK
                    ),
                )
                variants.append(variant)
                variants.extend(self._parse_element_style_body(variant))
                continue
            value = self._style_value()
            if prop == "background":
                style.background = value
            elif prop in ("color", "colour"):
                style.color = value
            elif prop == "stroke":
                style.stroke = value
            elif prop == "strokewidth" and value.isdigit():
                style.stroke_width = int(value)
            elif prop == "shape":
                style.shape = _SHAPE_MAP.get(value.lower())
            elif prop == "border":
                style.border = _BORDER_MAP.get(value.lower())
            elif prop == "icon":
                style.icon = value
            elif prop == "iconposition":
                style.icon_position = _ICON_POSITION_MAP.get(value.lower())
            elif prop == "fontsize" and value.isdigit():
                style.font_size = int(value)
            elif prop == "opacity" and value.isdigit():
                style.opacity = int(value)
            elif prop == "width" and value.isdigit():
                style.width = int(value)
            elif prop == "height" and value.isdigit():
                style.height = int(value)
            elif prop == "metadata":
                style.metadata = value.lower() == "true"
            elif prop == "description":
                style.description = value.lower() == "true"
            # Unknown properties: the value token is consumed; ignore.
        self._expect(RBRACE)
        return variants

    def _parse_relationship_style_body(
        self, style: RelationshipStyle
    ) -> list[RelationshipStyle]:
        """Parse a relationship style block; returns light/dark variants."""
        variants: list[RelationshipStyle] = []
        if not self._match(LBRACE):
            return variants
        self._expect(LBRACE)
        while not self._match(RBRACE, EOF):
            if not self._match(IDENT):
                self._advance()
                continue
            prop = self._advance().value.lower()
            if prop in ("light", "dark") and self._match(LBRACE):
                variant = RelationshipStyle(
                    tag=style.tag,
                    color_scheme=(
                        ColorScheme.LIGHT if prop == "light" else ColorScheme.DARK
                    ),
                )
                variants.append(variant)
                variants.extend(self._parse_relationship_style_body(variant))
                continue
            value = self._style_value()
            if prop in ("color", "colour"):
                style.color = value
            elif prop == "thickness" and value.isdigit():
                style.thickness = int(value)
            elif prop == "width" and value.isdigit():
                style.width = int(value)
            elif prop == "fontsize" and value.isdigit():
                style.font_size = int(value)
            elif prop == "dashed":
                style.dashed = value.lower() == "true"
            elif prop == "style":
                style.style = _LINE_STYLE_MAP.get(value.lower())
            elif prop == "routing":
                style.routing = _ROUTING_MAP.get(value.lower())
            elif prop == "jump":
                style.jump = value.lower() == "true"
            elif prop == "position" and value.isdigit():
                style.position = int(value)
            elif prop == "opacity" and value.isdigit():
                style.opacity = int(value)
            elif prop == "metadata":
                style.metadata = value.lower() == "true"
            elif prop == "description":
                style.description = value.lower() == "true"
        self._expect(RBRACE)
        return variants

    def _parse_view(self, view_type: ViewType) -> View:
        self._advance()  # consume keyword
        element_id = ""
        if view_type in (ViewType.SYSTEM_LANDSCAPE, ViewType.CUSTOM):
            pass  # unscoped views; the first token is the key
        elif self._match(WILDCARD):
            self._advance()  # deployment scope "*" means unscoped
        elif self._match(IDENT):
            raw_id = self._advance().value
            element_id = self._id_map.get(raw_id, raw_id)
        environment = ""
        if view_type == ViewType.DEPLOYMENT:
            # deployment <scope> <environment> [key] [title] [description]
            if self._match(STRING):
                environment = self._advance().value.strip('"')
            elif self._match(IDENT):
                environment = self._advance().value
        key = ""
        if self._match(IDENT):
            key = self._advance().value
        elif self._match(STRING):
            key = self._advance().value.strip('"')
        title = self._optional_string()
        description = self._optional_string()
        view = View(
            type=view_type,
            key=key or element_id or environment,
            element_id=element_id,
            title=title,
            description=description,
            environment=environment,
        )
        if self._match(LBRACE):
            self._expect(LBRACE)
            while not self._match(RBRACE, EOF):
                self._parse_view_item(view)
            self._expect(RBRACE)
        return view

    def _parse_image_view(self) -> View:
        """Parse ``image <*|element> [key] { <source keywords> }``.

        Body keywords: ``plantuml``/``mermaid``/``image`` with a quoted
        source, ``kroki <format> <source>``, and ``title``. Sources must be
        quoted (the tokenizer has no token for unquoted URLs).
        """
        self._advance()  # consume 'image'
        element_id = ""
        if self._match(WILDCARD):
            self._advance()
        elif self._match(IDENT):
            raw_id = self._advance().value
            element_id = self._id_map.get(raw_id, raw_id)
        key = ""
        if self._match(IDENT):
            key = self._advance().value
        elif self._match(STRING):
            key = self._advance().value.strip('"')
        view = View(
            type=ViewType.IMAGE,
            key=key or element_id or "image",
            element_id=element_id,
        )
        if self._match(LBRACE):
            self._expect(LBRACE)
            while not self._match(RBRACE, EOF):
                if not self._match(IDENT):
                    self._advance()
                    continue
                kw = self._advance().value.lower()
                if kw in ("plantuml", "mermaid", "image"):
                    view.content = self._optional_string()
                    view.content_type = kw
                elif kw == "kroki":
                    fmt = self._optional_ident()
                    view.content = self._optional_string()
                    view.content_type = f"kroki/{fmt}" if fmt else "kroki"
                elif kw == "title":
                    view.title = self._optional_string()
            self._expect(RBRACE)
        return view

    def _parse_filtered_view(self) -> View:
        """Parse ``filtered <baseKey> <include|exclude> <tags> [key] [title]``.

        Tags may be a single identifier or a quoted comma-separated list.
        """
        self._advance()  # consume 'filtered'
        base_key = ""
        if self._match(IDENT):
            base_key = self._advance().value
        elif self._match(STRING):
            base_key = self._advance().value.strip('"')

        mode = FilterMode.INCLUDE
        if self._match(IDENT):
            raw_mode = self._advance().value.lower()
            if raw_mode == "exclude":
                mode = FilterMode.EXCLUDE

        tags: list[str] = []
        if self._match(STRING):
            raw_tags = self._advance().value.strip('"')
            tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
        elif self._match(IDENT):
            tags = [self._advance().value]

        key = ""
        if self._match(IDENT):
            key = self._advance().value
        elif self._match(STRING):
            key = self._advance().value.strip('"')
        title = self._optional_string()
        description = self._optional_string()
        if self._match(LBRACE):
            self._skip_block()

        return View(
            type=ViewType.FILTERED,
            key=key or f"{base_key}_{mode.value.lower()}",
            title=title,
            description=description,
            base_view_key=base_key,
            filter_mode=mode,
            filter_tags=tags,
        )

    def _parse_view_item(self, view: View) -> None:
        tok = self._peek()
        if tok.type == BANG:
            self._parse_directive("view")
            return
        # Dynamic views list ordered interaction steps: `a -> b "description"`.
        # Steps are stored as RelationshipViews whose id encodes the
        # endpoints (`src__dst`) and whose order is the 1-based step number.
        if (
            view.type == ViewType.DYNAMIC
            and tok.type == IDENT
            and self._lookahead_is_arrow()
        ):
            raw_src = self._advance().value
            self._expect(ARROW)
            raw_dst = self._expect(IDENT).value
            description = self._optional_string()
            self._optional_string()  # optional technology, not stored
            if self._match(LBRACE):
                self._skip_block()  # step metadata block, not stored
            src = self._id_map.get(raw_src, raw_src)
            dst = self._id_map.get(raw_dst, raw_dst)
            view.relationship_views.append(
                RelationshipView(
                    id=f"{src}__{dst}",
                    description=description,
                    order=str(len(view.relationship_views) + 1),
                )
            )
            return
        if tok.type == IDENT:
            kw = tok.value.lower()
            if kw == "include":
                line = self._advance().line
                if self._capture_expression_line(view, "include", line):
                    return
                if self._match(WILDCARD):
                    self._advance()
                    view.include_all = True
                else:
                    view.included_ids.extend(self._idents_on_line(line))
                return
            if kw == "exclude":
                line = self._advance().line
                if self._capture_expression_line(view, "exclude", line):
                    return
                view.excluded_ids.extend(self._idents_on_line(line))
                return
            if kw == "autolayout":
                # autoLayout [direction] [rankSeparation] [nodeSeparation]
                line = self._advance().line
                direction_str = ""
                if self._match(IDENT) and self._peek().line == line:
                    direction_str = self._advance().value.lower()
                rank_dir = _RANK_DIRECTION_MAP.get(
                    direction_str, RankDirection.TOP_BOTTOM
                )
                layout = AutomaticLayout(rank_direction=rank_dir)
                if self._match(NUMBER) and self._peek().line == line:
                    layout.rank_separation = int(self._advance().value)
                if self._match(NUMBER) and self._peek().line == line:
                    layout.node_separation = int(self._advance().value)
                view.auto_layout = layout
                return
            if kw == "title":
                self._advance()
                view.title = self._optional_string()
                return
            if kw == "description":
                self._advance()
                view.description = self._optional_string()
                return
            if kw == "default":
                self._advance()
                self._default_view_key = view.key
                return
            if kw == "properties":
                self._advance()
                view.properties.update(self._parse_properties_block())
                return
            if kw == "animation":
                self._advance()
                if self._match(LBRACE):
                    self._parse_animation(view)
                return
        self._advance()

    def _parse_animation(self, view: View) -> None:
        """Parse ``animation { <ids...> ... }`` — one step per line."""
        self._expect(LBRACE)
        while not self._match(RBRACE, EOF):
            if self._match(IDENT):
                ids = self._idents_on_line(self._peek().line)
                if ids:
                    view.animations.append(
                        Animation(order=len(view.animations) + 1, element_ids=ids)
                    )
            else:
                self._advance()
        self._expect(RBRACE)

    def _skip_unknown(self, scope: str) -> None:
        """Skip an unrecognised construct without consuming its scope.

        A bare ``advance()`` is not enough when the construct opens a block:
        its tokens are dropped one at a time until its closing brace, which
        the enclosing loop then reads as the end of *its* block, silently
        discarding everything after it. Unknown blocks are therefore skipped
        whole, brace-balanced, and reported — the same contract the parser
        applies to unsupported directives.

        Args:
            scope: Enclosing construct, named in the warning for context.
        """
        tok = self._advance()
        if self._match(LBRACE):
            self._skip_block()
            self._warn(
                f"skipped unsupported block {tok.value!r} in {scope}",
                line=tok.line,
                column=tok.column,
                end_column=tok.end_column,
                code="unsupported-block",
            )
            return
        self._warn(
            f"skipped unexpected {tok.value!r} in {scope}",
            line=tok.line,
            column=tok.column,
            end_column=tok.end_column,
            code="unexpected-token",
        )

    def _skip_block(self) -> None:
        self._expect(LBRACE)
        depth = 1
        while depth > 0 and not self._match(EOF):
            tok = self._advance()
            if tok.type == LBRACE:
                depth += 1
            elif tok.type == RBRACE:
                depth -= 1

    def _find_deployment_node(
        self, ws: Workspace, parent_id: str | None
    ) -> DeploymentNode | None:
        if parent_id is None:
            return None
        return _search_deployment_nodes(ws.deployment_nodes, parent_id)

    def _find_system(
        self, ws: Workspace, parent_id: str | None
    ) -> SoftwareSystem | None:
        if parent_id is None:
            return None
        for s in ws.software_systems:
            if s.id == parent_id:
                return s
        return None

    def _find_container(self, ws: Workspace, parent_id: str | None) -> Container | None:
        if parent_id is None:
            return None
        for s in ws.software_systems:
            for c in s.containers:
                if c.id == parent_id:
                    return c
        return None


def _search_deployment_nodes(
    nodes: list[DeploymentNode], target_id: str
) -> DeploymentNode | None:
    for node in nodes:
        if node.id == target_id:
            return node
        found = _search_deployment_nodes(node.children, target_id)
        if found is not None:
            return found
    return None


# ---------------------------------------------------------------------------
# !include preprocessing
# ---------------------------------------------------------------------------

_INCLUDE_RE = re.compile(
    r'^[ \t]*!include[ \t]+(?P<target>"[^"]+"|\S+)[ \t]*$', re.MULTILINE
)

_DOCS_RE = re.compile(
    r'^[ \t]*!(?P<kind>docs|adrs)[ \t]+(?P<target>"[^"]+"|\S+)[ \t]*$',
    re.MULTILINE,
)


def _expand_includes(
    source: str,
    base_dir: Path | None,
    stack: tuple[Path, ...],
    origin: Path | None = None,
    source_map: SourceMap | None = None,
    flat_line: int = 1,
) -> tuple[str, int]:
    """Replace ``!include <path>`` lines with the referenced file contents.

    Paths are resolved relative to the including file's directory and may
    themselves contain further includes. Used before tokenising so the
    parser only ever sees a single flattened source.

    Expansion is line-based so ``source_map`` can record which file each
    flattened line came from: without that, a problem inside an included
    fragment is reported against a line of the including file.

    Args:
        source: DSL text possibly containing ``!include`` lines.
        base_dir: Directory relative paths resolve against; ``None`` when
            parsing a bare string, in which case any ``!include`` is an
            error.
        stack: Chain of files already being expanded, for cycle detection.
        origin: File ``source`` was read from, recorded in the map.
        source_map: Collects the flattened-line to origin-line runs.
        flat_line: 1-based line the expanded output starts at.

    Returns:
        The flattened text and the next free flattened line number.

    Raises:
        ParseError: If there is no file context, the target does not exist,
            or the includes form a cycle.
    """
    out: list[str] = []
    lines = source.split("\n")
    run_open = False

    for index, line in enumerate(lines):
        match = _INCLUDE_RE.match(line)
        if match is None:
            if source_map is not None and not run_open:
                source_map.add(flat_line + len(out), origin, index + 1)
                run_open = True
            out.append(line)
            continue

        # An include splices another file in place of this line, so the
        # current run ends here and a fresh one starts after the splice.
        run_open = False
        target = match.group("target").strip('"')
        if base_dir is None:
            raise ParseError(
                f"!include {target!r} requires a file context; "
                "parse from a file instead of a string",
                line=index + 1,
                path=origin,
            )
        included = (base_dir / target).resolve()
        if included in stack:
            chain = " -> ".join(str(p) for p in (*stack, included))
            raise ParseError(
                f"Circular !include: {chain}", line=index + 1, path=origin
            )
        if not included.is_file():
            raise ParseError(
                f"!include target not found: {included}",
                line=index + 1,
                path=origin,
            )
        text = included.read_text(encoding="utf-8")
        expanded, _ = _expand_includes(
            text,
            included.parent,
            (*stack, included),
            origin=included,
            source_map=source_map,
            flat_line=flat_line + len(out),
        )
        out.extend(expanded.split("\n"))

    return "\n".join(out), flat_line + len(out)


# ---------------------------------------------------------------------------
# !script stripping and !const/!var substitution (preprocessing)
# ---------------------------------------------------------------------------

_SCRIPT_RE = re.compile(r"^[ \t]*!script\b[^\n{]*\{", re.MULTILINE)

_CONST_RE = re.compile(
    r"^[ \t]*!(?P<kind>const|constant|var)[ \t]+"
    r'(?P<name>"[^"]+"|\S+)[ \t]+'
    r'(?P<value>"(?:[^"\\]|\\.)*"|\S+)[ \t]*$',
    re.MULTILINE,
)

_PLACEHOLDER_RE = re.compile(r"\$\{([A-Za-z0-9_.\-]+)\}")


def _strip_scripts(source: str, warnings_out: list[tuple[int, str]]) -> str:
    """Remove ``!script <lang> { ... }`` blocks, recording a warning each.

    Script bodies are foreign syntax (Groovy/Kotlin/JS) whose strings may
    contain unbalanced braces, so they are removed textually with a
    quote-aware brace counter before tokenising.
    """
    result = source
    while True:
        match = _SCRIPT_RE.search(result)
        if match is None:
            return result
        depth = 1
        pos = match.end()
        quote: str | None = None
        while pos < len(result) and depth > 0:
            char = result[pos]
            if quote is not None:
                if char == "\\":
                    pos += 1  # skip the escaped character
                elif char == quote:
                    quote = None
            elif char in ('"', "'"):
                quote = char
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
            pos += 1
        line = result.count("\n", 0, match.start()) + 1
        warnings_out.append(
            (line, "unsupported directive '!script' ignored (body skipped)")
        )
        # Replace the block with as many blank lines as it occupied: every
        # later line number (and the include source map) depends on the
        # preprocessing passes not shifting anything.
        removed = result[match.start() : pos]
        result = (
            result[: match.start()] + "\n" * removed.count("\n") + result[pos:]
        )


def _apply_constants(source: str) -> str:
    """Collect ``!const``/``!var`` definitions and substitute ``${NAME}``.

    Constants cannot be redefined (and variables cannot shadow them);
    variables may be redefined, last value winning. Unknown ``${...}``
    placeholders are left intact, matching structurizr-java.
    """
    values: dict[str, str] = {}
    constants: set[str] = set()

    def collect(match: re.Match[str]) -> str:
        kind = match.group("kind")
        name = match.group("name").strip('"')
        value = match.group("value").strip('"')
        is_const = kind in ("const", "constant")
        if name in constants:
            raise ParseError(f"Cannot redefine constant {name!r} (!{kind})")
        if is_const and name in values:
            raise ParseError(
                f"Cannot define constant {name!r}: a variable with that name exists"
            )
        values[name] = value
        if is_const:
            constants.add(name)
        return ""

    stripped = _CONST_RE.sub(collect, source)
    if not values:
        return stripped
    return _PLACEHOLDER_RE.sub(lambda m: values.get(m.group(1), m.group(0)), stripped)


def parse_dsl(
    source: str,
    base_dir: str | Path | None = None,
    path: str | Path | None = None,
) -> Workspace:
    """Parse a Structurizr DSL string and return a Workspace.

    Args:
        source: The DSL text.
        base_dir: Directory that ``!include``, ``!docs`` and ``!adrs``
            paths resolve against (directives in included fragments resolve
            against the root file's directory). When ``None`` (parsing a
            bare string), any of these directives raises
            :class:`ParseError`.
        path: File ``source`` was read from, so diagnostics can name it.
            ``None`` when parsing a bare string.

    Raises:
        ParseError: Carrying the path and line of the problem.
    """
    resolved = Path(base_dir).resolve() if base_dir is not None else None
    root = Path(path).resolve() if path is not None else None
    source_map = SourceMap()
    flattened, _ = _expand_includes(
        source, resolved, (), origin=root, source_map=source_map
    )
    preprocess_warnings: list[tuple[int, str]] = []
    flattened = _strip_scripts(flattened, preprocess_warnings)
    flattened = _apply_constants(flattened)

    doc_dirs: list[tuple[str, Path]] = []

    def extract_docs(match: re.Match[str]) -> str:
        target = match.group("target").strip('"')
        if resolved is None:
            raise ParseError(
                f"!{match.group('kind')} {target!r} requires a file context; "
                "parse from a file instead of a string"
            )
        doc_dirs.append((match.group("kind"), (resolved / target).resolve()))
        return ""

    flattened = _DOCS_RE.sub(extract_docs, flattened)
    tokens = _tokenize(flattened)
    try:
        workspace = _Parser(tokens, source_map).parse()
    except ParseError as error:
        # Positions from the parser are flattened-source lines; resolve them
        # to the file the user actually has to edit.
        if error.line is not None and error.path is None:
            error.path, error.line = source_map.resolve(error.line)
        raise
    # Preprocessing runs before tokenising, so its positions are flattened
    # lines too and resolve through the same map.
    for line, message in preprocess_warnings:
        origin_path, origin_line = source_map.resolve(line)
        diagnostic = Diagnostic(
            message=message,
            severity=Severity.WARNING,
            path=origin_path,
            line=origin_line,
            code="unsupported-directive",
        )
        warnings.warn(str(diagnostic), UnsupportedFeatureWarning, stacklevel=2)
        workspace.diagnostics.append(diagnostic)
        workspace.parse_warnings.append(str(diagnostic))

    for kind, directory in doc_dirs:
        if kind == "docs":
            workspace.documentation.sections.extend(load_sections(directory))
        else:
            workspace.documentation.decisions.extend(load_decisions(directory))
    return workspace


def parse_dsl_file(path: str | Path) -> Workspace:
    """Read a .dsl file and parse it, resolving any ``!include`` directives."""
    path = Path(path).resolve()
    return parse_dsl(
        path.read_text(encoding="utf-8"), base_dir=path.parent, path=path
    )


def collect_source_files(path: str | Path) -> list[Path]:
    """Return ``path`` plus every file it (transitively) ``!include``s.

    Best-effort: unreadable or missing include targets are skipped and
    cycles are ignored, so this is safe to call on sources that would fail
    to parse. Used by the web app to know which files to watch for
    live-reload.
    """
    root = Path(path).resolve()
    seen: set[Path] = set()
    ordered: list[Path] = []

    def visit(current: Path) -> None:
        if current in seen:
            return
        seen.add(current)
        ordered.append(current)
        try:
            text = current.read_text(encoding="utf-8")
        except OSError:
            return
        for match in _INCLUDE_RE.finditer(text):
            target = match.group("target").strip('"')
            included = (current.parent / target).resolve()
            if included.is_file():
                visit(included)
        for match in _DOCS_RE.finditer(text):
            target = match.group("target").strip('"')
            directory = (root.parent / target).resolve()
            for doc in markdown_files(directory):
                if doc not in seen:
                    seen.add(doc)
                    ordered.append(doc)

    visit(root)
    return ordered
