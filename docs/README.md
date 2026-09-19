# c4studio Documentation

Welcome to the c4studio documentation. This directory contains guides and references for working with Structurizr architecture models in Python.

## Guides

- **[DSL Reference](./dsl-reference.md)** - **Start here to write DSL.** Every construct c4studio accepts, the `c4studio.*` property extensions, what is accepted and ignored, and what is not in the DSL at all. Every example in it is parsed by the test suite, so it cannot drift from the parser.
- **[DSL Language Support](./dsl-support.md)** - The per-keyword ledger against the upstream language reference: what is supported, partial or refused, and why. For parity work rather than authoring.
- **[Feature Parity](./structurizr-parity.md)** - Where c4studio stands against the Java Structurizr UI, feature by feature. The closest thing to a status page; kept current as work lands.
- **[Roadmap](./roadmap.md)** - The staged forward plan (query layer, headless rendering, differentiators) and the delivery conventions.
- **[Studio editor plan](./studio-editor-plan.md)** - How in-app DSL editing was designed and built: Studio/Viewer modes, the CodeMirror editor, file navigation at scale, and the assistant. **Complete** as of 0.3.0 (PP-119 … PP-142); kept as the record of the decisions and the measurements behind them.
- **[Migration Guide](./MIGRATION.md)** - Breaking changes and how to adapt. Start here when upgrading: **0.3.0 makes `c4 webapp` writable by default**.

Field-level detail on the domain model is not documented here: read
`src/c4studio/models/`, which is typed, documented and checked. A prose
copy of it went stale within two days of the last model change, so it was
removed rather than re-synchronised.

## Samples

`samples/` holds workspaces used for live verification, and doubles as worked
examples:

- `internet_banking.dsl`, `saas_monitoring.dsl`, `ecommerce_platform.dsl` — the common cases.
- `hedge_fund/` — the richest model: documentation, ADRs, deployment, groups and themes, split across `!include`-ed files.
- `c4studio/` — **c4studio described in its own DSL**, down to component level: 10 containers, 42 components, 13 views including two dynamic ones tracing the save loop and the headless render path. Dogfooding, and the shortest route to understanding the codebase.
- `delta_release.dsl` — marking elements as new, existing or deprecated, and getting that into the legend. See [Marking elements as new, existing or deprecated](./dsl-support.md#marking-elements-as-new-existing-or-deprecated).

## Quick Start

The main entry point for c4studio is the `Workspace` model, which contains:

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

See [the DSL reference](./dsl-reference.md) for how to write each of
these, and `src/c4studio/models/` for the fields themselves.

## Parsing & Generation

- **DSL Parser** (`c4studio.parser.dsl`): Parse Structurizr DSL files
- **JSON Parser** (`c4studio.parser.json_parser`): Parse Structurizr JSON exports
- **Mermaid Generator** (`c4studio.generators.mermaid`): Generate Mermaid C4 diagrams

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
