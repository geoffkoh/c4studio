"""Documentation value objects: sections, decisions, and images."""

from __future__ import annotations

from dataclasses import dataclass, field

from c4studio.models.enums import Format


@dataclass
class Section:
    """A section of long-form documentation attached to an element or workspace."""

    content: str = ""
    format: Format = Format.MARKDOWN
    title: str = ""
    filename: str = ""
    order: int = 0
    element_id: str = ""


@dataclass
class DecisionLink:
    """A link from one architecture decision to another."""

    id: str
    description: str = ""


@dataclass
class Decision:
    """An architecture decision record (ADR)."""

    id: str
    title: str = ""
    date: str = ""
    status: str = ""
    content: str = ""
    format: Format = Format.MARKDOWN
    element_id: str = ""
    links: list[DecisionLink] = field(default_factory=list)


@dataclass
class Image:
    """An image embedded in documentation."""

    name: str = ""
    content: str = ""
    type: str = ""


@dataclass
class Documentation:
    """A container for documentation sections, decisions, and images.

    Attached to a workspace or to a static-structure element
    (software system, container, or component).
    """

    sections: list[Section] = field(default_factory=list)
    decisions: list[Decision] = field(default_factory=list)
    images: list[Image] = field(default_factory=list)
