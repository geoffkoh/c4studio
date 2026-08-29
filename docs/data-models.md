# Structurizr Data Models

This document provides an overview of the main data models used in c4studio, which represent the Structurizr C4 metamodel for architecture visualization and documentation.

## Table of Contents

1. [Overview](#overview)
2. [Static Structure Elements](#static-structure-elements)
3. [Relationships](#relationships)
4. [Views](#views)
5. [Deployment Infrastructure](#deployment-infrastructure)
6. [Styling & Configuration](#styling--configuration)
7. [Value Objects](#value-objects)
8. [Root Model](#root-model)

---

## Overview

Structurizr uses a layered architecture model based on the C4 model (Context, Container, Component, Code levels). The data models in c4studio represent this architecture:

```
Workspace (root)
├── People & Software Systems (static structure)
├── Relationships (connections between elements)
├── Deployment Infrastructure (runtime deployment)
├── Views (diagrams/visualizations)
└── Configuration (styling, terminology, themes)
```

---

## Static Structure Elements

The static structure represents the logical architecture of your system.

### Person

Represents a human actor or user role in the system.

```python
@dataclass
class Person:
    id: str                              # Unique identifier
    name: str                            # Display name
    description: str = ""                # Detailed description
    tags: list[str] = field(...)         # Comma-separated labels
    location: Location = UNSPECIFIED     # Internal/External/Unspecified
    url: str = ""                        # External documentation link
    properties: dict[str, str] = {}      # Custom key-value pairs
    perspectives: list[Perspective] = [] # Named viewpoints (security, performance, etc.)
    group: str = ""                      # Grouping identifier for organization
```

**Example:** End users, support staff, system administrators

### SoftwareSystem

Represents a software application or service that delivers value to one or more users.

```python
@dataclass
class SoftwareSystem:
    id: str                              # Unique identifier
    name: str                            # Display name
    description: str = ""                # Detailed description
    containers: list[Container] = []     # Logical containers (apps, databases)
    tags: list[str] = []                 # Labels
    location: Location = UNSPECIFIED     # Internal/External/Unspecified
    url: str = ""                        # External documentation link
    properties: dict[str, str] = {}      # Custom properties
    perspectives: list[Perspective] = [] # Named viewpoints
    group: str = ""                      # Grouping identifier
```

**Example:** Email system, web application, mobile app

### Container

A logical container (application, microservice, database, file system) within a software system.

```python
@dataclass
class Container:
    id: str                              # Unique identifier
    name: str                            # Display name
    description: str = ""                # Detailed description
    technology: str = ""                 # Technology stack (Node.js, PostgreSQL, etc.)
    components: list[Component] = []     # Components within this container
    tags: list[str] = []                 # Labels
    url: str = ""                        # External documentation link
    properties: dict[str, str] = {}      # Custom properties
    perspectives: list[Perspective] = [] # Named viewpoints
    group: str = ""                      # Grouping identifier
```

**Example:** Web API, database server, message queue, cache layer

### Component

A logical component within a container, representing a grouping of related code/functionality.

```python
@dataclass
class Component:
    id: str                              # Unique identifier
    name: str                            # Display name
    description: str = ""                # Detailed description
    technology: str = ""                 # Technology/framework
    tags: list[str] = []                 # Labels
    url: str = ""                        # External documentation link
    properties: dict[str, str] = {}      # Custom properties
    perspectives: list[Perspective] = [] # Named viewpoints
    group: str = ""                      # Grouping identifier
```

**Example:** Authentication service, payment processor, user repository

### CustomElement

A user-defined element type for representing custom concepts not covered by the standard C4 model.

```python
@dataclass
class CustomElement:
    id: str                              # Unique identifier
    name: str                            # Display name
    description: str = ""                # Detailed description
    metadata: str = ""                   # Additional metadata
    tags: list[str] = []                 # Labels
    url: str = ""                        # External documentation link
    properties: dict[str, str] = {}      # Custom properties
    perspectives: list[Perspective] = [] # Named viewpoints
    group: str = ""                      # Grouping identifier
```

---

## Relationships

Relationships represent connections and interactions between elements.

### Relationship

A directed relationship between two model elements.

```python
@dataclass
class Relationship:
    source_id: str                       # ID of source element
    destination_id: str                  # ID of destination element
    description: str = ""                # Relationship description
    technology: str = ""                 # Technology used (HTTP, gRPC, etc.)
    tags: list[str] = []                 # Labels
    id: str = ""                         # Unique identifier
    interaction_style: InteractionStyle  # Synchronous/Asynchronous
    linked_relationship_id: str = ""     # Reference to related relationship
    url: str = ""                        # External documentation link
    properties: dict[str, str] = {}      # Custom properties
    perspectives: list[Perspective] = [] # Named viewpoints
```

**Example:** "User sends HTTP requests to Web API", "Service calls database"

---

## Views

Views define the different diagrams and visualizations available in your architecture.

### View

A view represents a diagram or visualization in the workspace.

```python
@dataclass
class View:
    type: ViewType                       # Type of view (see ViewType enum)
    key: str                             # Unique key for this view
    element_id: str = ""                 # Primary element ID for scoped views
    title: str = ""                      # Display title
    description: str = ""                # Detailed description
    include_all: bool = False            # Include all elements?
    included_ids: list[str] = []         # Specific elements to include
    excluded_ids: list[str] = []         # Specific elements to exclude
    auto_layout: AutomaticLayout | None  # Automatic layout configuration
    order: int = 0                       # Display order
    properties: dict[str, str] = {}      # Custom properties
    paper_size: PaperSize | None         # Paper size for printing
    relationship_views: list[RelationshipView] = []  # Relationship rendering
    animations: list[Animation] = []     # Animation steps for dynamic views
```

### ViewType (Enum)

The type of view being displayed:

- `SYSTEM_LANDSCAPE`: All people, software systems, and their relationships
- `SYSTEM_CONTEXT`: A specific software system in context with external actors
- `CONTAINER`: Internal containers within a software system
- `COMPONENT`: Internal components within a container
- `DYNAMIC`: Interactions between elements over time
- `DEPLOYMENT`: Runtime deployment infrastructure
- `CUSTOM`: Custom/domain-specific diagram
- `IMAGE`: Image-based diagram
- `FILTERED`: Filtered view of other views

### RelationshipView

Rendering and metadata for a specific relationship within a view.

```python
@dataclass
class RelationshipView:
    id: str                              # Relationship ID
    description: str = ""                # Alternative description
    url: str = ""                        # External documentation link
    order: str = ""                      # Sequence order (for dynamic views)
    response: bool | None = None         # Is this a response? (for dynamic views)
    vertices: list[Vertex] = []          # Bend-points on the line
    routing: Routing | None = None       # Routing style (Direct, Curved, Orthogonal)
    jump: bool | None = None             # Jump across other lines?
    position: int | None = None          # Position along relationship line
    properties: dict[str, str] = {}      # Custom properties
```

### AutomaticLayout

Configuration for automatic layout of elements in a view.

```python
@dataclass
class AutomaticLayout:
    rank_direction: RankDirection = TOP_BOTTOM  # Direction (TopBottom, BottomTop, LeftRight, RightLeft)
    rank_separation: int = 300           # Spacing between ranks
    node_separation: int = 300           # Spacing between nodes
    edge_separation: int = 0             # Spacing between edges
    vertices: bool = False               # Show bend-points on edges?
```

### Animation

A sequence step in an animated/dynamic view.

```python
@dataclass
class Animation:
    order: int                           # Step order (1, 2, 3, ...)
    element_ids: list[str] = []          # Elements to show in this step
    relationship_ids: list[str] = []     # Relationships to show in this step
```

### Vertex

A bend-point on a rendered relationship line.

```python
@dataclass
class Vertex:
    x: int                               # X coordinate
    y: int                               # Y coordinate
```

---

## Deployment Infrastructure

Deployment models represent the runtime infrastructure and deployment topology.

### DeploymentNode

A hierarchical node representing infrastructure (AWS region, Kubernetes cluster, VM, container, etc.).

```python
@dataclass
class DeploymentNode:
    id: str                              # Unique identifier
    name: str                            # Display name
    description: str = ""                # Detailed description
    technology: str = ""                 # Technology (AWS, Docker, etc.)
    instances: str = "1"                 # Number of instances
    environment: str = ""                # Environment name (production, staging)
    tags: list[str] = []                 # Labels
    url: str = ""                        # External documentation link
    properties: dict[str, str] = {}      # Custom properties
    perspectives: list[Perspective] = [] # Named viewpoints
    group: str = ""                      # Grouping identifier
    children: list[DeploymentNode] = []  # Child deployment nodes (hierarchy)
    infrastructure_nodes: list[InfrastructureNode] = []
    software_system_instances: list[SoftwareSystemInstance] = []
    container_instances: list[ContainerInstance] = []
    deployment_groups: list[str] = []    # Deployment group membership
```

### InfrastructureNode

Infrastructure components within a deployment node (load balancer, firewall, etc.).

```python
@dataclass
class InfrastructureNode:
    id: str                              # Unique identifier
    name: str                            # Display name
    description: str = ""                # Detailed description
    technology: str = ""                 # Technology
    tags: list[str] = []                 # Labels
    url: str = ""                        # External documentation link
    properties: dict[str, str] = {}      # Custom properties
    perspectives: list[Perspective] = [] # Named viewpoints
    group: str = ""                      # Grouping identifier
```

### SoftwareSystemInstance

A deployed instance of a software system within a deployment node.

```python
@dataclass
class SoftwareSystemInstance:
    id: str                              # Unique identifier
    software_system_id: str              # Reference to software system
    instance_id: int = 1                 # Instance number
    environment: str = ""                # Environment name
    deployment_groups: list[str] = []    # Deployment groups
    health_checks: list[HttpHealthCheck] = []  # Health check endpoints
    tags: list[str] = []                 # Labels
    url: str = ""                        # External documentation link
    properties: dict[str, str] = {}      # Custom properties
    perspectives: list[Perspective] = [] # Named viewpoints
```

### ContainerInstance

A deployed instance of a container within a deployment node.

```python
@dataclass
class ContainerInstance:
    id: str                              # Unique identifier
    container_id: str                    # Reference to container
    instance_id: int = 1                 # Instance number
    environment: str = ""                # Environment name
    deployment_groups: list[str] = []    # Deployment groups
    health_checks: list[HttpHealthCheck] = []  # Health check endpoints
    tags: list[str] = []                 # Labels
    url: str = ""                        # External documentation link
    properties: dict[str, str] = {}      # Custom properties
    perspectives: list[Perspective] = [] # Named viewpoints
```

### HttpHealthCheck

HTTP endpoint for monitoring container/system instance health.

```python
@dataclass
class HttpHealthCheck:
    name: str                            # Health check name
    url: str                             # HTTP endpoint URL
    interval: int = 60                   # Check interval (seconds)
    timeout: int = 0                     # Request timeout (seconds)
    headers: dict[str, str] = {}         # Custom HTTP headers
```

---

## Styling & Configuration

Configuration for diagram styling, themes, and element appearance.

### Styles

Collection of styling rules applied to elements and relationships.

```python
@dataclass
class Styles:
    element_styles: list[ElementStyle] = []      # Rules for elements
    relationship_styles: list[RelationshipStyle] = []  # Rules for relationships
```

### ElementStyle

Styling rules applied to elements matching specific tags.

```python
@dataclass
class ElementStyle:
    tag: str                             # Tag to match (e.g., "Web", "Database")
    width: int | None = None             # Width in pixels
    height: int | None = None            # Height in pixels
    background: str = ""                 # Background color (#RGB or name)
    stroke: str = ""                     # Border color
    stroke_width: int | None = None      # Border width in pixels
    color: str = ""                      # Text color
    font_size: int | None = None         # Font size in pixels
    shape: Shape | None = None           # Element shape
    icon: str = ""                       # Icon URL or name
    border: Border | None = None         # Border style
    opacity: int | None = None           # Opacity (0-100)
    metadata: bool | None = None         # Show metadata?
    description: bool | None = None      # Show description?
    color_scheme: ColorScheme | None     # Light or Dark
    icon_position: IconPosition | None   # Icon position (Top, Bottom, Left)
```

### RelationshipStyle

Styling rules applied to relationships matching specific tags.

```python
@dataclass
class RelationshipStyle:
    tag: str                             # Tag to match
    thickness: int | None = None         # Line thickness in pixels
    color: str = ""                      # Line color
    font_size: int | None = None         # Font size
    width: int | None = None             # Label width in pixels
    dashed: bool | None = None           # Dashed line?
    style: LineStyle | None = None       # Line style (Solid, Dashed, Dotted)
    routing: Routing | None = None       # Routing style
    jump: bool | None = None             # Jump across other lines?
    position: int | None = None          # Position along line
    opacity: int | None = None           # Opacity (0-100)
    metadata: bool | None = None         # Show metadata?
    description: bool | None = None      # Show description?
    color_scheme: ColorScheme | None     # Light or Dark
```

### Configuration

Workspace-level configuration for styles, themes, and terminology.

```python
@dataclass
class Configuration:
    styles: Styles = field(default_factory=Styles)
    themes: list[str] = []               # Theme URLs
    terminology: Terminology = field(default_factory=Terminology)
    default_view: str = ""               # Default view key
    view_sort_order: ViewSortOrder | None = None  # View ordering
    properties: dict[str, str] = {}      # Custom properties
```

### Terminology

Custom labels for element types to match your domain language.

```python
@dataclass
class Terminology:
    enterprise: str = ""                 # Custom "Enterprise" label
    person: str = ""                     # Custom "Person" label
    software_system: str = ""            # Custom "Software System" label
    container: str = ""                  # Custom "Container" label
    component: str = ""                  # Custom "Component" label
    code: str = ""                       # Custom "Code" label
    deployment_node: str = ""            # Custom "Deployment Node" label
    infrastructure_node: str = ""        # Custom "Infrastructure Node" label
    relationship: str = ""               # Custom "Relationship" label
```

---

## Value Objects

Supporting types and enumerations.

### Enterprise

Named enterprise or organization boundary shown on system landscape views.

```python
@dataclass
class Enterprise:
    name: str                            # Enterprise/organization name
```

### Perspective

A named viewpoint on an element (security perspective, performance perspective, etc.).

```python
@dataclass
class Perspective:
    name: str                            # Perspective name
    description: str = ""                # Detailed description
    value: str = ""                      # Perspective value/content
    url: str = ""                        # External documentation link
```

### Enumerations

**Location:**
- `INTERNAL`: Part of the enterprise
- `EXTERNAL`: Outside the enterprise
- `UNSPECIFIED`: Location not specified

**InteractionStyle:**
- `SYNCHRONOUS`: Request/response (blocking)
- `ASYNCHRONOUS`: Fire-and-forget (non-blocking)

**RankDirection:**
- `TOP_BOTTOM`: Vertical layout (top to bottom)
- `BOTTOM_TOP`: Vertical layout (bottom to top)
- `LEFT_RIGHT`: Horizontal layout (left to right)
- `RIGHT_LEFT`: Horizontal layout (right to left)

**Shape:**
Box, RoundedBox, Circle, Ellipse, Hexagon, Diamond, Cylinder, Bucket, Pipe, Person, Robot, Folder, WebBrowser, Window, Terminal, Shell, MobileDevicePortrait, MobileDeviceLandscape, Component

**Routing:**
- `DIRECT`: Straight line
- `CURVED`: Curved line
- `ORTHOGONAL`: Right-angle bends

**LineStyle:**
- `SOLID`: Solid line
- `DASHED`: Dashed line
- `DOTTED`: Dotted line

**Border:**
- `SOLID`: Solid border
- `DASHED`: Dashed border
- `DOTTED`: Dotted border

**ColorScheme:**
- `LIGHT`: Light theme
- `DARK`: Dark theme

**IconPosition:**
- `TOP`: Icon above label
- `BOTTOM`: Icon below label
- `LEFT`: Icon left of label

**ViewSortOrder:**
- `DEFAULT`: Default order
- `TYPE`: Sort by element type
- `KEY`: Sort by view key

**PaperSize:**
Various paper sizes for printing (A6-A0 portrait/landscape, Letter, Legal, Slide formats)

**FilterMode:**
- `INCLUDE`: Include specified elements
- `EXCLUDE`: Exclude specified elements

---

## Root Model

### Workspace

The root container for an entire Structurizr model and architecture definition.

```python
@dataclass
class Workspace:
    name: str                                    # Workspace name
    description: str = ""                        # Detailed description
    people: list[Person] = []                    # All people in the architecture
    software_systems: list[SoftwareSystem] = []  # All software systems
    relationships: list[Relationship] = []       # All relationships
    views: list[View] = []                       # All views/diagrams
    deployment_nodes: list[DeploymentNode] = []  # Deployment infrastructure
    deployment_environments: list[str] = []      # Environment names (prod, staging, etc.)
    enterprise: Enterprise | None = None         # Optional enterprise boundary
    configuration: Configuration = field(...)    # Styling and configuration
```

**Key Methods:**
- `find_element(id: str)`: Look up any element by ID across all levels
- `all_relationships_for(ids: set[str])`: Get relationships between a set of elements

---

## Usage Example

```python
from c4studio.models import (
    Workspace, Person, SoftwareSystem, Container,
    Relationship, View, ViewType, Location
)

# Create workspace
ws = Workspace(
    name="E-Commerce System",
    description="E-commerce platform architecture"
)

# Add people
customer = Person(
    id="customer",
    name="Customer",
    description="A customer using the e-commerce platform",
    location=Location.EXTERNAL
)
ws.people.append(customer)

# Add software system
ecommerce = SoftwareSystem(
    id="ecommerce",
    name="E-Commerce Platform",
    description="Main e-commerce platform",
    location=Location.INTERNAL
)
ws.software_systems.append(ecommerce)

# Add containers
web_app = Container(
    id="web-app",
    name="Web Application",
    description="Browser-based web interface",
    technology="React"
)
ecommerce.containers.append(web_app)

# Add relationship
rel = Relationship(
    source_id="customer",
    destination_id="web-app",
    description="Browses products and places orders",
    technology="HTTPS"
)
ws.relationships.append(rel)

# Create view
context_view = View(
    type=ViewType.SYSTEM_CONTEXT,
    key="SystemContext",
    title="E-Commerce System Context"
)
ws.views.append(context_view)
```

---

## Model Hierarchy

```
Workspace
├── Enterprise (optional)
├── People[]
├── SoftwareSystem[]
│   ├── Container[]
│   │   └── Component[]
│   └── Perspective[]
├── Relationship[]
├── DeploymentNode[] (hierarchical)
│   ├── DeploymentNode[] (children)
│   ├── InfrastructureNode[]
│   ├── SoftwareSystemInstance[]
│   └── ContainerInstance[]
├── View[]
│   ├── RelationshipView[]
│   ├── Animation[]
│   └── AutomaticLayout
└── Configuration
    ├── Styles
    │   ├── ElementStyle[]
    │   └── RelationshipStyle[]
    ├── Terminology
    └── Themes[]
```

---

## Related Documentation

- [C4 Model](https://c4model.com/) - The foundational architecture model
- [Structurizr DSL](https://github.com/structurizr/dsl) - Domain-specific language for defining architectures
- [Mermaid C4 Diagram Generation](./mermaid-generation.md) - Converting models to Mermaid diagrams
