"""Expression engine for view include/exclude lines and bulk directives.

Implements the Structurizr DSL expression grammar:

- ``*`` — all elements
- ``<identifier>`` — a single element
- ``element.type==<Type>`` / ``!=`` — by element type
- ``element.tag==T1,T2`` / ``!=`` — elements carrying *all* listed tags
  (implicit type tags such as ``Person``/``Software System`` participate)
- ``element.parent==<identifier>`` — direct children of an element
- ``-><id>`` / ``<id>->`` / ``-><id>->`` — element plus afferent/efferent
  neighbours
- ``<id> -> <id>`` — relationships between two elements
- ``relationship==*``, ``relationship.tag==``, ``relationship.source==``,
  ``relationship.destination==`` — relationship selections

Terms are parsed from ``(token_type, value)`` pairs produced by the DSL
tokenizer (kept as plain strings to avoid importing the parser module).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

from c4studio.models import Relationship, Workspace

# Term tuples:
#   ("wildcard",)
#   ("ident", name)
#   ("compare", subject, prop, negate: bool, values: list[str])
#   ("between", src, dst)
#   ("afferent", ident) / ("efferent", ident) / ("both", ident)
Term = tuple[Any, ...]

_STRING_TERM_RE = re.compile(
    r"^(?P<subject>element|relationship)"
    r"(?:\.(?P<prop>\w+))?"
    r"(?P<op>==|!=)"
    r"(?P<values>.*)$"
)

# element type display names double as implicit tags ("Software System")
_TYPE_DISPLAY = {
    "person": "Person",
    "softwaresystem": "Software System",
    "container": "Container",
    "component": "Component",
    "deploymentnode": "Deployment Node",
    "infrastructurenode": "Infrastructure Node",
    "customelement": "Custom",
}


@dataclass
class ExpressionResult:
    """Elements and relationships matched by an expression list."""

    element_ids: set[str] = field(default_factory=set)
    relationships: list[Relationship] = field(default_factory=list)


def parse_terms(tokens: list[tuple[str, str]]) -> list[Term]:
    """Parse one include/exclude line's tokens into expression terms."""
    terms: list[Term] = []
    i = 0
    n = len(tokens)

    def tt(index: int) -> str:
        return tokens[index][0] if index < n else ""

    def tv(index: int) -> str:
        return tokens[index][1] if index < n else ""

    def consume_values(index: int) -> tuple[list[str], int]:
        values: list[str] = []
        while tt(index) in ("IDENT", "STRING", "NUMBER", "WILDCARD"):
            values.append(tv(index).strip('"'))
            index += 1
            if tt(index) == "COMMA":
                index += 1
            else:
                break
        return values, index

    while i < n:
        kind = tt(i)
        if kind == "WILDCARD":
            terms.append(("wildcard",))
            i += 1
        elif kind == "STRING":
            term = _parse_string_term(tv(i).strip('"'))
            if term is not None:
                terms.append(term)
            i += 1
        elif kind == "ARROW":
            if tt(i + 1) == "IDENT":
                if tt(i + 2) == "ARROW":
                    terms.append(("both", tv(i + 1)))
                    i += 3
                else:
                    terms.append(("afferent", tv(i + 1)))
                    i += 2
            else:
                i += 1
        elif kind == "IDENT":
            if (
                tt(i + 1) == "DOT"
                and tt(i + 2) == "IDENT"
                and tt(i + 3)
                in (
                    "EQEQ",
                    "NEQ",
                )
            ):
                subject = tv(i).lower()
                prop = tv(i + 2).lower()
                negate = tt(i + 3) == "NEQ"
                values, i = consume_values(i + 4)
                terms.append(("compare", subject, prop, negate, values))
            elif tt(i + 1) in ("EQEQ", "NEQ"):
                subject = tv(i).lower()
                negate = tt(i + 1) == "NEQ"
                values, i = consume_values(i + 2)
                terms.append(("compare", subject, "", negate, values))
            elif tt(i + 1) == "ARROW":
                if tt(i + 2) == "IDENT" and tt(i + 3) != "ARROW":
                    terms.append(("between", tv(i), tv(i + 2)))
                    i += 3
                else:
                    terms.append(("efferent", tv(i)))
                    i += 2
            else:
                terms.append(("ident", tv(i)))
                i += 1
        else:
            i += 1
    return terms


def _parse_string_term(text: str) -> Term | None:
    """Parse a quoted expression such as ``"element.tag==Software System"``."""
    match = _STRING_TERM_RE.match(text.strip())
    if match is None:
        return ("ident", text) if text else None
    values = [v.strip() for v in match.group("values").split(",") if v.strip()]
    return (
        "compare",
        match.group("subject"),
        (match.group("prop") or "").lower(),
        match.group("op") == "!=",
        values,
    )


def is_expression_term(tokens: list[tuple[str, str]]) -> bool:
    """Whether a line's tokens need the expression engine (vs plain idents)."""
    for token_type, value in tokens:
        if token_type in ("DOT", "EQEQ", "NEQ", "ARROW", "COMMA"):
            return True
        if token_type == "STRING" and _STRING_TERM_RE.match(value.strip('"')):
            return True
    return False


def _element_index(
    workspace: Workspace,
) -> dict[str, tuple[Any, str, str]]:
    """Map element id → (element, type display name, parent id)."""
    index: dict[str, tuple[Any, str, str]] = {}

    def add(element: Any, parent_id: str = "") -> None:
        display = _TYPE_DISPLAY.get(type(element).__name__.lower(), "Element")
        index[element.id] = (element, display, parent_id)

    for person in workspace.people:
        add(person)
    for custom in workspace.custom_elements:
        add(custom)
    for system in workspace.software_systems:
        add(system)
        for container in system.containers:
            add(container, system.id)
            for component in container.components:
                add(component, container.id)

    def walk(node: Any, parent_id: str) -> None:
        add(node, parent_id)
        for infra in node.infrastructure_nodes:
            add(infra, node.id)
        for child in node.children:
            walk(child, node.id)

    for node in workspace.deployment_nodes:
        walk(node, "")
    return index


def _tags_of(element: Any, display: str) -> set[str]:
    return {"Element", display, *getattr(element, "tags", [])}


def evaluate(
    terms: list[Term],
    workspace: Workspace,
    relationships: list[Relationship],
    resolve: Callable[[str], str],
) -> ExpressionResult:
    """Evaluate expression terms against the workspace model.

    Args:
        terms: Parsed terms from :func:`parse_terms`.
        workspace: The (possibly still-building) workspace.
        relationships: Relationship candidates; endpoints are passed through
            ``resolve`` so unresolved parse-buffer entries match too.
        resolve: Maps a DSL identifier to its element id.
    """
    index = _element_index(workspace)
    result = ExpressionResult()

    def rel_source(rel: Relationship) -> str:
        return resolve(rel.source_id)

    def rel_dest(rel: Relationship) -> str:
        return resolve(rel.destination_id)

    for term in terms:
        kind = term[0]
        if kind == "wildcard":
            result.element_ids.update(index.keys())
        elif kind == "ident":
            result.element_ids.add(resolve(term[1]))
        elif kind in ("afferent", "efferent", "both"):
            eid = resolve(term[1])
            result.element_ids.add(eid)
            for rel in relationships:
                if kind in ("afferent", "both") and rel_dest(rel) == eid:
                    result.element_ids.add(rel_source(rel))
                if kind in ("efferent", "both") and rel_source(rel) == eid:
                    result.element_ids.add(rel_dest(rel))
        elif kind == "between":
            src, dst = resolve(term[1]), resolve(term[2])
            result.relationships.extend(
                rel
                for rel in relationships
                if rel_source(rel) == src and rel_dest(rel) == dst
            )
        elif kind == "compare":
            _, subject, prop, negate, values = term
            if subject == "element":
                matched = _match_elements(index, prop, values, resolve)
                if negate:
                    matched = set(index.keys()) - matched
                result.element_ids.update(matched)
            elif subject == "relationship":
                matched_rels = _match_relationships(
                    relationships, prop, values, resolve
                )
                if negate:
                    keep = {id(r) for r in matched_rels}
                    matched_rels = [r for r in relationships if id(r) not in keep]
                result.relationships.extend(matched_rels)
    return result


def _match_elements(
    index: dict[str, tuple[Any, str, str]],
    prop: str,
    values: list[str],
    resolve: Callable[[str], str],
) -> set[str]:
    matched: set[str] = set()
    if prop == "type":
        wanted = {v.replace(" ", "").lower() for v in values}
        for eid, (_, display, _parent) in index.items():
            if display.replace(" ", "").lower() in wanted:
                matched.add(eid)
    elif prop == "tag":
        for eid, (element, display, _parent) in index.items():
            if set(values) <= _tags_of(element, display):
                matched.add(eid)
    elif prop == "parent":
        wanted_parents = {resolve(v) for v in values}
        for eid, (_, _display, parent_id) in index.items():
            if parent_id and parent_id in wanted_parents:
                matched.add(eid)
    return matched


def _match_relationships(
    relationships: list[Relationship],
    prop: str,
    values: list[str],
    resolve: Callable[[str], str],
) -> list[Relationship]:
    if prop == "" and "*" in values:
        return list(relationships)
    matched: list[Relationship] = []
    for rel in relationships:
        if prop == "tag":
            if set(values) <= {"Relationship", *rel.tags}:
                matched.append(rel)
        elif prop == "source":
            if resolve(rel.source_id) in {resolve(v) for v in values}:
                matched.append(rel)
        elif prop == "destination":
            if resolve(rel.destination_id) in {resolve(v) for v in values}:
                matched.append(rel)
    return matched
