"""View models, styling, and the view collection."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Optional

from pystructurizr.models.enums import (
    Border,
    ColorScheme,
    FilterMode,
    IconPosition,
    LineStyle,
    PaperSize,
    RankDirection,
    Routing,
    Shape,
    ViewSortOrder,
    ViewType,
)


# ---------------------------------------------------------------------------
# View supporting value objects
# ---------------------------------------------------------------------------


@dataclass
class AutomaticLayout:
    """Automatic layout configuration for a view."""

    rank_direction: RankDirection = RankDirection.TOP_BOTTOM
    rank_separation: int = 100
    node_separation: int = 100
    edge_separation: int = 0
    vertices: bool = False


@dataclass
class Vertex:
    """A bend-point on a rendered relationship line."""

    x: int
    y: int


@dataclass
class Animation:
    """One step in an animated view."""

    order: int
    element_ids: list[str] = field(default_factory=list)
    relationship_ids: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# View models
# ---------------------------------------------------------------------------


@dataclass
class Dimensions:
    """Canvas size of a rendered view, in pixels."""

    width: int = 0
    height: int = 0


@dataclass
class ViewElement:
    """An element included in a view with optional x/y position."""

    id: str
    x: Optional[int] = None
    y: Optional[int] = None
    title: str = ""
    description: str = ""
    width: Optional[int] = None
    height: Optional[int] = None


@dataclass
class RelationshipView:
    """A relationship included in a view, with optional rendering metadata."""

    id: str
    description: str = ""
    url: str = ""
    order: str = ""
    response: Optional[bool] = None
    vertices: list[Vertex] = field(default_factory=list)
    routing: Optional[Routing] = None
    jump: Optional[bool] = None
    position: Optional[int] = None
    properties: dict[str, str] = field(default_factory=dict)
    title: str = ""
    link: Optional[bool] = None
    link_element: Optional[int] = None


@dataclass
class View:
    """A view (diagram) in the workspace."""

    type: ViewType
    key: str
    element_id: str = ""
    title: str = ""
    description: str = ""
    include_all: bool = False
    included_ids: list[str] = field(default_factory=list)
    excluded_ids: list[str] = field(default_factory=list)
    # raw DSL include/exclude expressions (kept for debuggability; the
    # resolved element/relationship ids live in the fields around this)
    include_expressions: list[str] = field(default_factory=list)
    exclude_expressions: list[str] = field(default_factory=list)
    excluded_relationship_ids: list[str] = field(default_factory=list)
    auto_layout: Optional[AutomaticLayout] = None
    order: int = 0
    properties: dict[str, str] = field(default_factory=dict)
    paper_size: Optional[PaperSize] = None
    relationship_views: list[RelationshipView] = field(default_factory=list)
    element_views: list[ViewElement] = field(default_factory=list)
    animations: list[Animation] = field(default_factory=list)
    owner: str = ""
    disable_automatic_layout: bool = False
    hide_element_metadata: bool = False
    hide_relationship_metadata: bool = False
    # Deployment / dynamic views
    environment: str = ""
    external_boundaries_visible: bool = False
    # Filtered views
    base_view_key: str = ""
    filter_mode: Optional[FilterMode] = None
    filter_tags: list[str] = field(default_factory=list)
    # Image views
    content: str = ""
    content_light: str = ""
    content_dark: str = ""
    content_type: str = ""
    # Per-type fields, named and defaulted as in structurizr-core. The two
    # that default to True are why the exporter cannot simply drop falsy
    # values for them.
    #: System landscape and system context views.
    enterprise_boundary_visible: bool = True
    #: Container views.
    external_software_system_boundaries_visible: bool = False
    #: Component views: the container the view is scoped to.
    container_id: str = ""
    #: Component views.
    external_container_boundaries_visible: bool = False
    #: True when the key was generated rather than written by the author.
    generated_key: bool = False
    #: Canvas size, when the workspace records one.
    dimensions: Optional[Dimensions] = None
    #: Whether a remote workspace's layout may be merged into this view.
    merge_from_remote: bool = True


# ---------------------------------------------------------------------------
# Styling models
# ---------------------------------------------------------------------------


@dataclass
class ElementStyle:
    """Styling rule applied to elements whose tags match."""

    tag: str
    width: Optional[int] = None
    height: Optional[int] = None
    background: str = ""
    stroke: str = ""
    stroke_width: Optional[int] = None
    color: str = ""
    font_size: Optional[int] = None
    shape: Optional[Shape] = None
    icon: str = ""
    border: Optional[Border] = None
    opacity: Optional[int] = None
    metadata: Optional[bool] = None
    description: Optional[bool] = None
    color_scheme: Optional[ColorScheme] = None
    icon_position: Optional[IconPosition] = None


@dataclass
class RelationshipStyle:
    """Styling rule applied to relationships whose tags match."""

    tag: str
    thickness: Optional[int] = None
    color: str = ""
    font_size: Optional[int] = None
    width: Optional[int] = None
    dashed: Optional[bool] = None
    style: Optional[LineStyle] = None
    routing: Optional[Routing] = None
    jump: Optional[bool] = None
    position: Optional[int] = None
    opacity: Optional[int] = None
    metadata: Optional[bool] = None
    description: Optional[bool] = None
    color_scheme: Optional[ColorScheme] = None


@dataclass
class Styles:
    """Collection of element and relationship styling rules."""

    element_styles: list[ElementStyle] = field(default_factory=list)
    relationship_styles: list[RelationshipStyle] = field(default_factory=list)


@dataclass
class Terminology:
    """Custom label overrides for each element type."""

    enterprise: str = "Enterprise"
    person: str = "Person"
    software_system: str = "Software System"
    container: str = "Container"
    component: str = "Component"
    code: str = "Code"
    deployment_node: str = "Deployment Node"
    infrastructure_node: str = "Infrastructure Node"
    relationship: str = "Relationship"


@dataclass
class Font:
    """A branding font: a family name and an optional web-font URL."""

    name: str = ""
    url: str = ""


@dataclass
class Branding:
    """Custom branding configuration: font and logo URL."""

    font: Font = field(default_factory=Font)
    logo: str = ""


@dataclass
class Configuration:
    """Workspace view configuration: styles, themes, and terminology."""

    styles: Styles = field(default_factory=Styles)
    themes: list[str] = field(default_factory=list)
    terminology: Terminology = field(default_factory=Terminology)
    default_view: str = ""
    last_saved_view: str = ""
    metadata_symbols: str = ""
    view_sort_order: Optional[ViewSortOrder] = None
    properties: dict[str, str] = field(default_factory=dict)
    branding: Optional[Branding] = None
    generators_and_exporters: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# ViewSet — typed view collection with list-protocol back-compat
# ---------------------------------------------------------------------------


_VIEW_TYPE_TO_ATTR: dict[ViewType, str] = {
    ViewType.SYSTEM_LANDSCAPE: "system_landscape_views",
    ViewType.SYSTEM_CONTEXT: "system_context_views",
    ViewType.CONTAINER: "container_views",
    ViewType.COMPONENT: "component_views",
    ViewType.DYNAMIC: "dynamic_views",
    ViewType.DEPLOYMENT: "deployment_views",
    ViewType.CUSTOM: "custom_views",
    ViewType.IMAGE: "image_views",
    ViewType.FILTERED: "filtered_views",
}


@dataclass
class ViewSet:
    """All views, grouped by type. Supports list-like access for legacy callers."""

    system_landscape_views: list[View] = field(default_factory=list)
    system_context_views: list[View] = field(default_factory=list)
    container_views: list[View] = field(default_factory=list)
    component_views: list[View] = field(default_factory=list)
    dynamic_views: list[View] = field(default_factory=list)
    deployment_views: list[View] = field(default_factory=list)
    custom_views: list[View] = field(default_factory=list)
    image_views: list[View] = field(default_factory=list)
    filtered_views: list[View] = field(default_factory=list)
    configuration: Configuration = field(default_factory=Configuration)

    def get_all_views(self) -> list[View]:
        """Return every view across all types, in declaration order."""
        return [
            *self.system_landscape_views,
            *self.system_context_views,
            *self.container_views,
            *self.component_views,
            *self.dynamic_views,
            *self.deployment_views,
            *self.custom_views,
            *self.image_views,
            *self.filtered_views,
        ]

    def append(self, view: View) -> None:
        """Append a view to the typed list matching its view.type."""
        attr = _VIEW_TYPE_TO_ATTR.get(view.type)
        if attr is None:
            return
        target: list[View] = getattr(self, attr)
        target.append(view)

    def __iter__(self) -> Iterator[View]:
        return iter(self.get_all_views())

    def __len__(self) -> int:
        return (
            len(self.system_landscape_views)
            + len(self.system_context_views)
            + len(self.container_views)
            + len(self.component_views)
            + len(self.dynamic_views)
            + len(self.deployment_views)
            + len(self.custom_views)
            + len(self.image_views)
            + len(self.filtered_views)
        )

    def __getitem__(self, index: int) -> View:
        return self.get_all_views()[index]
