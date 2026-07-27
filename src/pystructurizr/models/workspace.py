"""The Model and Workspace roots that tie the metamodel together."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from pystructurizr.models.deployment import DeploymentNode, InfrastructureNode
from pystructurizr.models.documentation import Documentation
from pystructurizr.models.elements import (
    Component,
    Container,
    CustomElement,
    Enterprise,
    Person,
    Relationship,
    SoftwareSystem,
)
from pystructurizr.models.views import Configuration, ViewSet
from pystructurizr.diagnostics import Diagnostic


# ---------------------------------------------------------------------------
# Model — static structure container
# ---------------------------------------------------------------------------


@dataclass
class Model:
    """Static C4 model: all elements and relationships in the workspace."""

    people: list[Person] = field(default_factory=list)
    software_systems: list[SoftwareSystem] = field(default_factory=list)
    custom_elements: list[CustomElement] = field(default_factory=list)
    relationships: list[Relationship] = field(default_factory=list)
    deployment_nodes: list[DeploymentNode] = field(default_factory=list)
    deployment_environments: list[str] = field(default_factory=list)
    enterprise: Optional[Enterprise] = None
    properties: dict[str, str] = field(default_factory=dict)

    def find_element(
        self, element_id: str
    ) -> (
        Person
        | SoftwareSystem
        | Container
        | Component
        | DeploymentNode
        | InfrastructureNode
        | CustomElement
        | None
    ):
        """Look up any element by id across all levels of the model."""
        for p in self.people:
            if p.id == element_id:
                return p
        for ce in self.custom_elements:
            if ce.id == element_id:
                return ce
        for s in self.software_systems:
            if s.id == element_id:
                return s
            for c in s.containers:
                if c.id == element_id:
                    return c
                for comp in c.components:
                    if comp.id == element_id:
                        return comp
        for dn in self.deployment_nodes:
            result = _find_in_deployment_node(dn, element_id)
            if result is not None:
                return result
        return None

    def all_relationships_for(self, ids: set[str]) -> list[Relationship]:
        """Return relationships where both source and destination are in ids."""
        return [
            r
            for r in self.relationships
            if r.source_id in ids and r.destination_id in ids
        ]


# ---------------------------------------------------------------------------
# Workspace
# ---------------------------------------------------------------------------


@dataclass
class User:
    """A user granted access to the workspace (Structurizr configuration)."""

    username: str
    role: str = "read"


@dataclass
class WorkspaceConfiguration:
    """Workspace-level configuration: scope, visibility, and users.

    Distinct from the *views* :class:`Configuration` exposed as
    ``Workspace.configuration``.
    """

    scope: str = ""
    visibility: str = ""
    users: list[User] = field(default_factory=list)


@dataclass
class Workspace:
    """Root container for an entire Structurizr model."""

    name: str
    description: str = ""
    model: Model = field(default_factory=Model)
    views: ViewSet = field(default_factory=ViewSet)
    id: str = ""
    version: int = 1
    revision: int = 1
    last_modified_date: str = ""
    last_modified_by: str = ""
    created_date: str = ""
    created_by: str = ""
    documentation: Documentation = field(default_factory=Documentation)
    # Non-fatal warnings collected while parsing (e.g. unsupported DSL
    # features that were skipped); never serialised to workspace JSON.
    parse_warnings: list[str] = field(default_factory=list)
    #: Structured form of the problems found while parsing. ``parse_warnings``
    #: is retained as the human-readable strings for existing callers.
    diagnostics: list[Diagnostic] = field(default_factory=list)
    workspace_configuration: WorkspaceConfiguration = field(
        default_factory=WorkspaceConfiguration
    )

    @property
    def people(self) -> list[Person]:
        return self.model.people

    @property
    def custom_elements(self) -> list[CustomElement]:
        return self.model.custom_elements

    @property
    def software_systems(self) -> list[SoftwareSystem]:
        return self.model.software_systems

    @property
    def relationships(self) -> list[Relationship]:
        return self.model.relationships

    @property
    def deployment_nodes(self) -> list[DeploymentNode]:
        return self.model.deployment_nodes

    @property
    def deployment_environments(self) -> list[str]:
        return self.model.deployment_environments

    @property
    def enterprise(self) -> Optional[Enterprise]:
        return self.model.enterprise

    @enterprise.setter
    def enterprise(self, value: Optional[Enterprise]) -> None:
        self.model.enterprise = value

    @property
    def configuration(self) -> Configuration:
        return self.views.configuration

    @configuration.setter
    def configuration(self, value: Configuration) -> None:
        self.views.configuration = value

    def find_element(
        self, element_id: str
    ) -> (
        Person
        | SoftwareSystem
        | Container
        | Component
        | DeploymentNode
        | InfrastructureNode
        | CustomElement
        | None
    ):
        return self.model.find_element(element_id)

    def all_relationships_for(self, ids: set[str]) -> list[Relationship]:
        return self.model.all_relationships_for(ids)

    def validate(self) -> list[str]:
        """Return a list of validation issues; empty list means the workspace is well-formed.

        Checks:
        - View keys must be non-empty.
        - View keys must be unique across the workspace.
        """
        issues: list[str] = []
        seen: dict[str, int] = {}
        for view in self.views:
            if not view.key:
                issues.append(f"View of type {view.type.value} has an empty key.")
                continue
            seen[view.key] = seen.get(view.key, 0) + 1
        for key, count in seen.items():
            if count > 1:
                issues.append(f"Duplicate view key {key!r} appears {count} times.")
        return issues


def _find_in_deployment_node(
    node: DeploymentNode, element_id: str
) -> DeploymentNode | InfrastructureNode | None:
    """Recursively search a deployment node subtree for an element by id."""
    if node.id == element_id:
        return node
    for infra in node.infrastructure_nodes:
        if infra.id == element_id:
            return infra
    for child in node.children:
        result = _find_in_deployment_node(child, element_id)
        if result is not None:
            return result
    return None
