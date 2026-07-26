# pystructurizr Documentation

Welcome to the pystructurizr documentation. This directory contains guides and references for working with Structurizr architecture models in Python.

## Guides

- **[Data Models](./data-models.md)** - Comprehensive reference for all Structurizr data models, including static structure elements, relationships, views, deployment infrastructure, and styling configuration.
- **[Feature Parity](./structurizr-parity.md)** - Where pystructurizr stands against the Java Structurizr UI, feature by feature. The closest thing to a status page; kept current as work lands.
- **[Roadmap](./roadmap.md)** - The staged forward plan (query layer, headless rendering, differentiators) and the delivery conventions.
- **[Migration Guide](./MIGRATION.md)** - Breaking changes from the Structurizr Java compatibility work and how to adapt.
- **[Compatibility Roadmap](./COMPATIBILITY_ROADMAP.md)** - Historical record of that compatibility work, now complete.

## Quick Start

The main entry point for pystructurizr is the `Workspace` model, which contains:

- **People & Systems**: Define actors and software systems
- **Containers & Components**: Decompose systems into logical parts
- **Relationships**: Connect elements and document interactions
- **Views**: Create different diagrams for different stakeholders
- **Deployment**: Define runtime infrastructure and deployments
- **Configuration**: Style elements and customize appearance

## Typical Workflow

1. Create a `Workspace` with name and description
2. Add `Person` elements (actors/users)
3. Add `SoftwareSystem` elements (applications/services)
4. Add `Container` and `Component` elements (decomposition)
5. Add `Relationship` elements (connections and interactions)
6. Define `View` elements (diagrams/visualizations)
7. Add optional `DeploymentNode` hierarchy for runtime topology
8. Configure `Styles` and appearance

See [Data Models](./data-models.md) for detailed documentation on each model and its fields.

## Parsing & Generation

- **DSL Parser** (`pystructurizr.parser.dsl`): Parse Structurizr DSL files
- **JSON Parser** (`pystructurizr.parser.json_parser`): Parse Structurizr JSON exports
- **Mermaid Generator** (`pystructurizr.generators.mermaid`): Generate Mermaid C4 diagrams

## Common Patterns

### Accessing Elements

```python
ws = Workspace(...)
# Find any element by ID
element = ws.find_element("element-id")

# Get all relationships between a set of elements
ids = {"system1", "system2", "system3"}
rels = ws.all_relationships_for(ids)
```

### Adding Perspectives

Perspectives represent named viewpoints on elements (security, performance, cost, etc.):

```python
system = SoftwareSystem(
    id="api",
    name="API Service",
    perspectives=[
        Perspective(
            name="Security",
            description="Security considerations",
            value="OAuth 2.0 protected endpoints"
        )
    ]
)
```

### Custom Properties

All elements support custom key-value properties:

```python
container = Container(
    id="db",
    name="Database",
    properties={
        "cost": "$100/month",
        "team": "platform",
        "sla": "99.9%"
    }
)
```

## Model Relationships

The model follows a hierarchical structure:

```
Workspace (root)
├── People
├── Software Systems
│   ├── Containers
│   │   └── Components
│   └── Relationships
├── Deployment Nodes (hierarchical)
│   ├── Infrastructure Nodes
│   ├── System Instances
│   └── Container Instances
├── Views
│   ├── System Context View
│   ├── Container View
│   ├── Component View
│   ├── Dynamic View
│   └── Deployment View
└── Configuration
    ├── Styles
    ├── Terminology
    └── Themes
```
