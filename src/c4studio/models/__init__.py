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
    Dimensions,
    Font,
    Configuration,
    ElementStyle,
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
    # enums
    "ElementType",
    "ViewType",
    "Location",
    "InteractionStyle",
    "RankDirection",
    "Shape",
    "Routing",
    "LineStyle",
    "Border",
    "FilterMode",
    "ColorScheme",
    "IconPosition",
    "ViewSortOrder",
    "PaperSize",
    "Format",
    # documentation
    "Section",
    "DecisionLink",
    "Decision",
    "Image",
    "Documentation",
    # elements
    "Perspective",
    "Enterprise",
    "Relationship",
    "Component",
    "Container",
    "SoftwareSystem",
    "Person",
    "CustomElement",
    # deployment
    "HttpHealthCheck",
    "InfrastructureNode",
    "SoftwareSystemInstance",
    "ContainerInstance",
    "DeploymentNode",
    # views
    "AutomaticLayout",
    "Vertex",
    "Animation",
    "ViewElement",
    "RelationshipView",
    "View",
    "ElementStyle",
    "RelationshipStyle",
    "Styles",
    "Terminology",
    "Branding",
    "Dimensions",
    "Font",
    "Configuration",
    "ViewSet",
    # workspace
    "Model",
    "User",
    "Workspace",
    "WorkspaceConfiguration",
]
