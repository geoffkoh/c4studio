"""Static-structure elements and their supporting value objects."""

from __future__ import annotations

from dataclasses import dataclass, field

from c4studio.models.documentation import Documentation
from c4studio.models.enums import InteractionStyle, Location


# ---------------------------------------------------------------------------
# Supporting value objects
# ---------------------------------------------------------------------------


@dataclass
class Perspective:
    """A named viewpoint on an element (e.g. security, performance)."""

    name: str
    description: str = ""
    value: str = ""
    url: str = ""
    title: str = ""


@dataclass
class Enterprise:
    """Named enterprise or organisation boundary shown on system landscape views."""

    name: str


# ---------------------------------------------------------------------------
# Relationship
# ---------------------------------------------------------------------------


@dataclass
class Relationship:
    """A directed relationship between two model elements."""

    source_id: str
    destination_id: str
    description: str = ""
    technology: str = ""
    tags: list[str] = field(default_factory=list)
    id: str = ""
    interaction_style: InteractionStyle = InteractionStyle.SYNCHRONOUS
    linked_relationship_id: str = ""
    url: str = ""
    properties: dict[str, str] = field(default_factory=dict)
    perspectives: list[Perspective] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Static structure elements
# ---------------------------------------------------------------------------


@dataclass
class Component:
    """A component within a container."""

    id: str
    name: str
    description: str = ""
    technology: str = ""
    tags: list[str] = field(default_factory=list)
    url: str = ""
    properties: dict[str, str] = field(default_factory=dict)
    perspectives: list[Perspective] = field(default_factory=list)
    group: str = ""
    parent_id: str = ""
    documentation: Documentation = field(default_factory=Documentation)


@dataclass
class Container:
    """A container (application/datastore) within a software system."""

    id: str
    name: str
    description: str = ""
    technology: str = ""
    components: list[Component] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    url: str = ""
    properties: dict[str, str] = field(default_factory=dict)
    perspectives: list[Perspective] = field(default_factory=list)
    group: str = ""
    parent_id: str = ""
    documentation: Documentation = field(default_factory=Documentation)


@dataclass
class SoftwareSystem:
    """A software system in the C4 model."""

    id: str
    name: str
    description: str = ""
    containers: list[Container] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    location: Location = Location.UNSPECIFIED
    url: str = ""
    properties: dict[str, str] = field(default_factory=dict)
    perspectives: list[Perspective] = field(default_factory=list)
    group: str = ""
    documentation: Documentation = field(default_factory=Documentation)


@dataclass
class Person:
    """A human actor (user or role) in the C4 model."""

    id: str
    name: str
    description: str = ""
    tags: list[str] = field(default_factory=list)
    location: Location = Location.UNSPECIFIED
    url: str = ""
    properties: dict[str, str] = field(default_factory=dict)
    perspectives: list[Perspective] = field(default_factory=list)
    group: str = ""


@dataclass
class CustomElement:
    """A user-defined element type."""

    id: str
    name: str
    description: str = ""
    metadata: str = ""
    tags: list[str] = field(default_factory=list)
    url: str = ""
    properties: dict[str, str] = field(default_factory=dict)
    perspectives: list[Perspective] = field(default_factory=list)
    group: str = ""
    icon: str = ""
