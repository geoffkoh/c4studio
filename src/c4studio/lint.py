"""Model standards, checked the way a compiler checks code (PP-187).

`c4 check` answers "does this parse?". This answers "is this a good
model?" — orphaned elements, missing descriptions, duplicated
relationships, styles that match nothing. They are the review comments a
person would otherwise have to make every time, which is the point: a
rule enforces a standard without a review bottleneck.

Rules are small classes with a code, a summary and a `check`. They report
:class:`Diagnostic`, the same type the parser produces, so the webapp's
problems list and the VS Code Problems panel understand a lint finding
without knowing what linting is.

Everything here is a **warning**, never an error: a model that breaks a
house style still parses, still renders, and is still worth looking at.
The exit code is what makes CI care.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from c4studio.diagnostics import Diagnostic, Severity
from c4studio.models import (
    Component,
    Container,
    Person,
    SoftwareSystem,
    Workspace,
)

#: Implicit tag per element type, as Structurizr applies them. Styles match
#: on these as readily as on an author's own tags, so a rule about unused
#: styles has to know them or it reports every default style as dead.
IMPLICIT_TAGS: dict[type, str] = {
    Person: "Person",
    SoftwareSystem: "Software System",
    Container: "Container",
    Component: "Component",
}


@dataclass
class LintConfig:
    """What to check, and how strictly.

    Attributes:
        ignore: Rule codes to skip entirely.
        select: When non-empty, the only rule codes to run.
        naming: Regex per element keyword (``softwareSystem``,
            ``container``, …) that element names must match. Rules with no
            pattern configured do not run — a naming convention nobody
            wrote down is not a standard.
    """

    ignore: set[str] = field(default_factory=set)
    select: set[str] = field(default_factory=set)
    naming: dict[str, str] = field(default_factory=dict)

    def wants(self, code: str) -> bool:
        """Whether a rule should run under this configuration."""
        if code in self.ignore:
            return False
        return not self.select or code in self.select


def load_config(path: Path) -> LintConfig:
    """Read a lint configuration from JSON.

    Args:
        path: File holding ``{"ignore": [...], "select": [...],
            "naming": {"container": "^[A-Z]"}}``. Missing keys are
            defaults; a file that is not an object is treated as empty.

    Returns:
        The configuration.

    Raises:
        ValueError: If the file is not valid JSON.
    """
    data: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return LintConfig()
    return LintConfig(
        ignore={str(code) for code in data.get("ignore", [])},
        select={str(code) for code in data.get("select", [])},
        naming={str(k): str(v) for k, v in (data.get("naming") or {}).items()},
    )


@dataclass(frozen=True)
class Element:
    """One element of the model, flattened for the rules.

    Attributes:
        id: The element's id — the DSL alias where it had one.
        name: Its name.
        kind: The DSL keyword that declared it.
        description: Its description, possibly empty.
        technology: Its technology, empty for people and systems.
        tags: Its own tags, without the implicit ones.
        parent: The name of the element it lives in, if any.
    """

    id: str
    name: str
    kind: str
    description: str
    technology: str
    tags: tuple[str, ...]
    parent: str | None = None


def elements(workspace: Workspace) -> Iterator[Element]:
    """Every person, system, container and component, in declaration order."""
    for person in workspace.model.people:
        yield Element(
            person.id, person.name, "person", person.description, "", tuple(person.tags)
        )
    for system in workspace.model.software_systems:
        yield Element(
            system.id,
            system.name,
            "softwareSystem",
            system.description,
            "",
            tuple(system.tags),
        )
        for container in system.containers:
            yield Element(
                container.id,
                container.name,
                "container",
                container.description,
                container.technology,
                tuple(container.tags),
                system.name,
            )
            for component in container.components:
                yield Element(
                    component.id,
                    component.name,
                    "component",
                    component.description,
                    component.technology,
                    tuple(component.tags),
                    container.name,
                )


class Rule(Protocol):
    """A model standard that can be checked."""

    code: str
    summary: str

    def check(self, workspace: Workspace) -> Iterable[tuple[str, str]]:
        """Yield ``(element id, message)`` for everything that breaks it."""


class OrphanElement:
    """An element nothing relates to, in either direction.

    Usually a leftover from a rename or a deletion. Occasionally
    deliberate — a system recorded for completeness — which is why this
    is a warning and why the rule can be switched off.

    **A parent counts as related when a child is.** Relationships are
    routinely declared at container level while the diagram people look
    at is the system context, and a view lifts them to the nearest
    visible ancestor for exactly that reason. Reporting the parent as an
    orphan would flag every well-modelled system in the samples — which
    is how a linter teaches people to turn it off.
    """

    code = "orphan-element"
    summary = "element has no relationships"

    def check(self, workspace: Workspace) -> Iterable[tuple[str, str]]:
        touched: set[str] = set()
        for relationship in workspace.relationships:
            touched.add(relationship.source_id)
            touched.add(relationship.destination_id)

        def connected(element_id: str, descendants: Iterable[str]) -> bool:
            return element_id in touched or any(d in touched for d in descendants)

        for person in workspace.model.people:
            if not connected(person.id, ()):
                yield person.id, f"person {person.name!r} has no relationships"
        for system in workspace.model.software_systems:
            component_ids = [
                component.id
                for container in system.containers
                for component in container.components
            ]
            container_ids = [container.id for container in system.containers]
            if not connected(system.id, container_ids + component_ids):
                yield (
                    system.id,
                    f"softwareSystem {system.name!r} has no relationships",
                )
                continue
            for container in system.containers:
                ids = [component.id for component in container.components]
                if not connected(container.id, ids):
                    yield (
                        container.id,
                        f"container {container.name!r} has no relationships",
                    )
                    continue
                for component in container.components:
                    if not connected(component.id, ()):
                        yield (
                            component.id,
                            f"component {component.name!r} has no relationships",
                        )


class MissingDescription:
    """An element with no description.

    The description is what a diagram shows under the name, and what a
    reader who did not build the system needs most.
    """

    code = "missing-description"
    summary = "element has no description"

    def check(self, workspace: Workspace) -> Iterable[tuple[str, str]]:
        for element in elements(workspace):
            if not element.description.strip():
                yield element.id, f"{element.kind} {element.name!r} has no description"


class MissingTechnology:
    """A container or component with no technology.

    People and software systems have none by design; containers and
    components are the level where "what is it built with" is the
    question being asked.
    """

    code = "missing-technology"
    summary = "container or component has no technology"

    def check(self, workspace: Workspace) -> Iterable[tuple[str, str]]:
        for element in elements(workspace):
            if element.kind in ("container", "component") and not (
                element.technology.strip()
            ):
                yield element.id, f"{element.kind} {element.name!r} has no technology"


class DuplicateRelationship:
    """The same relationship declared twice.

    Same source, same destination, same description — which draws one
    edge and leaves the reader wondering which line they are looking at.
    Two relationships between the same pair with *different* descriptions
    are ordinary and are not reported.
    """

    code = "duplicate-relationship"
    summary = "relationship declared more than once"

    def check(self, workspace: Workspace) -> Iterable[tuple[str, str]]:
        seen: set[tuple[str, str, str]] = set()
        for relationship in workspace.relationships:
            if relationship.linked_relationship_id:
                continue  # implied, not written by anyone
            key = (
                relationship.source_id,
                relationship.destination_id,
                relationship.description,
            )
            if key in seen:
                message = (
                    f"{relationship.source_id} -> {relationship.destination_id} "
                    f"{relationship.description!r} is declared more than once"
                )
                yield relationship.source_id, message
            seen.add(key)


class UnusedStyle:
    """A style whose tag nothing carries.

    Silent by construction: the legend only lists styles in use, so a
    style that matches nothing simply never appears, and the author is
    left believing they styled something.
    """

    code = "unused-style"
    summary = "style matches no element or relationship"

    def check(self, workspace: Workspace) -> Iterable[tuple[str, str]]:
        element_tags: set[str] = {"Element"}
        for person in workspace.model.people:
            element_tags.update(person.tags)
            element_tags.add("Person")
        for system in workspace.model.software_systems:
            element_tags.update(system.tags)
            element_tags.add("Software System")
            for container in system.containers:
                element_tags.update(container.tags)
                element_tags.add("Container")
                for component in container.components:
                    element_tags.update(component.tags)
                    element_tags.add("Component")

        relationship_tags: set[str] = {"Relationship"}
        for relationship in workspace.relationships:
            relationship_tags.update(relationship.tags)

        styles = workspace.views.configuration.styles
        for style in styles.element_styles:
            # A `Perspective:` style is matched by perspective name, not by
            # a tag any element carries, so it is never "unused" here.
            if style.tag.startswith("Perspective:"):
                continue
            if style.tag not in element_tags:
                yield "", f"element style {style.tag!r} matches no element"
        for rel_style in styles.relationship_styles:
            if rel_style.tag.startswith("Perspective:"):
                continue
            if rel_style.tag not in relationship_tags:
                yield (
                    "",
                    f"relationship style {rel_style.tag!r} matches no relationship",
                )


class NamingConvention:
    """Element names that do not match a configured pattern.

    Does nothing until a pattern is configured: a convention nobody wrote
    down is not a standard, and guessing one would make the linter's
    first run a wall of noise.
    """

    code = "naming-convention"
    summary = "element name does not match the configured pattern"

    def __init__(self, patterns: dict[str, str]) -> None:
        self._patterns = {
            kind.lower(): re.compile(pattern) for kind, pattern in patterns.items()
        }

    def check(self, workspace: Workspace) -> Iterable[tuple[str, str]]:
        if not self._patterns:
            return
        for element in elements(workspace):
            pattern = self._patterns.get(element.kind.lower())
            if pattern is not None and not pattern.search(element.name):
                message = (
                    f"{element.kind} {element.name!r} does not match "
                    f"{pattern.pattern!r}"
                )
                yield element.id, message


def default_rules(config: LintConfig) -> list[Rule]:
    """Every rule, in report order, honouring ``config``."""
    rules: list[Rule] = [
        MissingDescription(),
        MissingTechnology(),
        OrphanElement(),
        DuplicateRelationship(),
        UnusedStyle(),
        NamingConvention(config.naming),
    ]
    return [rule for rule in rules if config.wants(rule.code)]


def lint(
    workspace: Workspace,
    config: LintConfig | None = None,
    locations: dict[str, tuple[Path, int]] | None = None,
) -> list[Diagnostic]:
    """Check ``workspace`` against the model standards.

    Args:
        workspace: The parsed workspace.
        config: Which rules to run; all of them by default.
        locations: Element id → definition site, from
            :func:`c4studio.parser.locations.element_locations`. When
            given, a finding points at the line that declares the element
            rather than at the file as a whole.

    Returns:
        One warning-severity :class:`Diagnostic` per finding, rule by
        rule, in declaration order within each rule.
    """
    settings = config or LintConfig()
    found: list[Diagnostic] = []
    for rule in default_rules(settings):
        for element_id, message in rule.check(workspace):
            path, line = (locations or {}).get(element_id, (None, None))
            found.append(
                Diagnostic(
                    message=message,
                    severity=Severity.WARNING,
                    path=path,
                    line=line,
                    code=rule.code,
                )
            )
    return found
