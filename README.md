# pystructurizr

Python implementation of [Structurizr](https://structurizr.com/) for architecture modeling and C4 diagram generation.

## Install

Published on PyPI as **`pystructurizr-studio`** (the name `pystructurizr`
belongs to an unrelated project); the import package and the CLI are
still `pystructurizr`:

```bash
pipx install pystructurizr-studio          # or: pip install pystructurizr-studio
pystructurizr webapp my-architecture.dsl

# or run without installing:
uvx --from pystructurizr-studio pystructurizr webapp my-architecture.dsl
```

Requires Python 3.13+ (uv/uvx can provision it automatically).

## Quick Start

```python
from pystructurizr.models import Workspace, Person, SoftwareSystem, Container, Relationship, View, ViewType

# Create workspace
ws = Workspace(
    name="My Architecture",
    description="System architecture model"
)

# Define people and systems
user = Person(id="user", name="User")
system = SoftwareSystem(id="sys", name="System")
ws.people.append(user)
ws.software_systems.append(system)

# Add relationship
rel = Relationship(
    source_id="user",
    destination_id="sys",
    description="Uses"
)
ws.relationships.append(rel)

# Create view
view = View(type=ViewType.SYSTEM_CONTEXT, key="context")
ws.views.append(view)
```

## Documentation

- **[Data Models Reference](./docs/data-models.md)** - Complete guide to all Structurizr models and their fields
- **[Getting Started](./docs/README.md)** - Workflow and common patterns
- **[Enterprise Roadmap](./docs/roadmap.md)** - Parked phases 2-4 (model intelligence, headless rendering, differentiators)

## Features

- ✅ Full Structurizr metamodel support (C4 architecture model)
- ✅ DSL and JSON parsing
- ✅ Mermaid diagram generation — C4 syntax or `flowchart`/`subgraph`
- ✅ Comprehensive type hints
- ✅ Custom properties and perspectives on all elements
- ✅ Deployment infrastructure modeling
- ✅ Style and configuration management

## Parsing

Parse Structurizr DSL or JSON files:

```python
from pystructurizr.parser.dsl import parse_dsl_file
from pystructurizr.parser.json_parser import parse_json_file

# Parse DSL
ws = parse_dsl_file("architecture.dsl")

# Parse JSON
ws = parse_json_file("workspace.json")
```

## Diagram Generation

Two Mermaid targets, both rendering from the same view graph — so what they
show matches the web app's view semantics exactly:

| Target | Syntax | Covers |
| --- | --- | --- |
| `MermaidGenerator` | `C4Context` / `C4Container` / `C4Component` | system landscape, system context, container, component views |
| `FlowchartGenerator` | `flowchart` + `subgraph` | all of the above **plus** dynamic, deployment and filtered views |

Mermaid's C4 diagram types are experimental upstream and lay out poorly on
dense models, and GitHub pins its own Mermaid version — so prefer the
flowchart target for anything rendered on GitHub or in a wiki.

```python
from pystructurizr.generators import FlowchartGenerator, MermaidGenerator

for view_name, mermaid_code in MermaidGenerator(ws).generate_all().items():
    print(f"{view_name}:\n{mermaid_code}\n")

# Or the flowchart target, which renders every view type:
diagrams = FlowchartGenerator(ws).generate_all()
```

From the CLI:

```bash
uv run pystructurizr generate architecture.dsl                     # C4 (default)
uv run pystructurizr generate architecture.dsl -f flowchart        # flowchart
uv run pystructurizr generate architecture.dsl -f flowchart -o out # one .mmd per view
```

## Workspace JSON Export

Export any workspace (DSL or JSON) back to Structurizr workspace JSON,
round-tripping with structurizr.com, Structurizr Lite, and this package's
own parser:

```bash
uv run pystructurizr export workspace.dsl -o workspace.json
```

Or programmatically via `pystructurizr.generators.json_export.export_json`.

## VS Code Extension

[`editors/vscode/`](./editors/vscode/) ships a VS Code extension with
Structurizr DSL syntax highlighting and an in-editor C4 diagram preview
(the full web app in a side panel, live-reloading as you save). Build and
install it locally:

```bash
cd editors/vscode && npm install && npm run package
code --install-extension pystructurizr-vscode-*.vsix
```

## React Web App

A React (Vite + TypeScript) single-page app, served by a FastAPI backend
and launched from the CLI, for loading DSL/JSON files from disk and
exploring each view as an interactive [React Flow](https://reactflow.dev/)
graph (draggable nodes, pan/zoom, minimap).

```bash
uv run pystructurizr webapp samples/          # browse a directory
uv run pystructurizr webapp file.dsl          # preload a single file
# → opens http://127.0.0.1:8090 (use --no-browser to skip, --port to change)
```

Pass a directory to browse and load any `.dsl`/`.json` file from the
in-app file picker, or a single file to preload it. The element tree and
per-view graph come from the parser and `graph/view_graph`;
`systemLandscape`, `systemContext`, `container`, `component`, `dynamic`
and `deployment` views all render as interactive graphs (other view
types are flagged "not renderable yet").

The **Explorer** tab renders the entire static model as one graph —
independent of any curated view — at a selectable abstraction level
(systems / containers / components), with search across every element
(press `/`), and a details panel showing an element's metadata,
relationships, the views it appears in (click to jump) and a
show-definition link into the Source pane.

The built SPA ships inside the package (`pystructurizr/webapp/static/`),
so end users need no Node toolchain. To rebuild the frontend after
changes (requires Node 18+):

```bash
cd frontend
npm install
npm run build          # outputs to ../src/pystructurizr/webapp/static/
# dev loop: `npm run dev` (Vite :5173, proxies /api → :8090) alongside
#           `uv run pystructurizr webapp samples/ --no-browser`
```

> **Security**: the web app has no authentication and is intended for
> local use on `127.0.0.1`.

### Tests

```bash
uv run pytest                      # full suite
uv run pytest tests/test_webapp    # web app tests only
```
