"""C4 model data classes representing the Structurizr metamodel.

This package is split into focused modules (``enums``, ``documentation``,
``elements``, ``deployment``, ``views``, ``workspace``). Every public name is
re-exported here so ``from c4studio.models import X`` keeps working
regardless of which module X lives in.
"""

from __future__ import annotations

from c4studio.models.deployment import (
    ContainerInstance,
    DeploymentNode,
    HttpHealthCheck,
    InfrastructureNode,
    SoftwareSystemInstance,
)
from c4studio.models.documentation import (
    Decision,
    DecisionLink,
    Documentation,
    Image,
    Section,
)
from c4studio.models.elements import (
    Component,
    Container,
    CustomElement,
    Enterprise,
    Person,
    Perspective,
    Relationship,
    SoftwareSystem,
)
from c4studio.models.enums import (
    Border,
    ColorScheme,
    ElementType,
    FilterMode,
    Format,
    IconPosition,
    InteractionStyle,
    LineStyle,
    Location,
    PaperSize,
    RankDirection,
    Routing,
    Shape,
    ViewSortOrder,
    ViewType,
)
from c4studio.models.views import (
    Animation,
    AutomaticLayout,
    Branding,
    Configuration,
    Dimensions,
    ElementStyle,
    Font,
    RelationshipStyle,
    RelationshipView,
    Styles,
    Terminology,
    Vertex,
    View,
    ViewElement,
    ViewSet,
)
from c4studio.models.workspace import (
    Model,
    User,
    Workspace,
    WorkspaceConfiguration,
)

__all__ = [
    "Animation",
    # views
    "AutomaticLayout",
    "Border",
    "Branding",
    "ColorScheme",
    "Component",
    "Configuration",
    "Container",
    "ContainerInstance",
    "CustomElement",
    "Decision",
    "DecisionLink",
    "DeploymentNode",
    "Dimensions",
    "Documentation",
    "ElementStyle",
    # enums
    "ElementType",
    "Enterprise",
    "FilterMode",
    "Font",
    "Format",
    # deployment
    "HttpHealthCheck",
    "IconPosition",
    "Image",
    "InfrastructureNode",
    "InteractionStyle",
    "LineStyle",
    "Location",
    # workspace
    "Model",
    "PaperSize",
    "Person",
    # elements
    "Perspective",
    "RankDirection",
    "Relationship",
    "RelationshipStyle",
    "RelationshipView",
    "Routing",
    # documentation
    "Section",
    "Shape",
    "SoftwareSystem",
    "SoftwareSystemInstance",
    "Styles",
    "Terminology",
    "User",
    "Vertex",
    "View",
    "ViewElement",
    "ViewSet",
    "ViewSortOrder",
    "ViewType",
    "Workspace",
    "WorkspaceConfiguration",
]
