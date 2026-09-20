# c4studio

Python implementation of [Structurizr](https://structurizr.com/) for architecture
modeling and C4 diagram generation — with a local-first **Studio** for writing
the DSL and watching the diagram follow.

## Install
Published on PyPI as **`c4studio`**; the import package is `c4studio`
and the command is `c4`:

```bash
pipx install c4studio          # or: pip install c4studio
c4 new my-architecture.dsl     # start from a template
c4 webapp my-architecture.dsl  # edit it, and see it

# or run without installing:
uvx --from c4studio c4 webapp my-architecture.dsl
```

Requires Python 3.13+ (uv/uvx can provision it automatically).

## Features
- ✅ Full Structurizr metamodel support (C4 architecture model)
- ✅ DSL and JSON parsing
- ✅ **In-browser DSL editor** — syntax highlighting, autocomplete, live
  diagnostics, save straight to disk, diagram beside the text
- ✅ **Searchable file tree** with create, rename and delete
- ✅ **Starter templates** and `c4 new`
- ✅ Mermaid diagram generation — C4 syntax or `flowchart`/`subgraph`
- ✅ Headless SVG rendering for CI and docs-as-code
- ✅ Comprehensive type hints
- ✅ **Perspectives** — annotate elements and relationships with security,
  ownership or anything else, then show one over the diagram
- ✅ **`c4 lint`** — model standards in CI: orphans, missing descriptions,
  duplicate relationships, styles that match nothing
- ✅ Custom properties on all elements
- ✅ Deployment infrastructure modeling
- ✅ Style and configuration management
- ⚙️ Optional AI assistant — off by default, and the only feature that
  uses the network

## Studio — the web app
A React (Vite + TypeScript) single-page app, served by a FastAPI backend and
launched from the CLI. It loads DSL/JSON from disk, renders each view as an
interactive [React Flow](https://reactflow.dev/) graph, and — since 0.3.0 —
lets you write the DSL that produces them.

```bash
uv run c4 webapp samples/          # browse a directory
uv run c4 webapp file.dsl          # preload a single file
uv run c4 webapp samples/ --viewer # read-only, for a kiosk or an embed
# → opens http://127.0.0.1:8090 (use --no-browser to skip, --port to change)
```

### Studio and Viewer

| | Command | Behaviour |
| --- | --- | --- |
| **Studio** | `c4 webapp <path>` | Browse, edit, save, create. **The default.** |
| **Viewer** | `c4 webapp <path> --viewer` | No DSL writes — the routes answer 403. Layout dragging and group collapse still persist. |

> **Upgrading from 0.2.0?** `c4 webapp` used to be read-only and is now
> writable. If you point it at anything public-facing, add `--viewer`. The
> guarantee lives on the server, so it holds against a crafted request and
> not merely a hidden button.

### Editing

The **Source** tab is a [CodeMirror 6](https://codemirror.net/) editor with
the diagram beside it:

- **Syntax highlighting and autocomplete** for DSL keywords, your own element
  identifiers, and view keys — drawn from the loaded workspace, so it knows
  what you have actually defined.
- **Diagnostics as you type**, from the same parser the CLI uses. Invalid DSL
  still saves: an editor that refuses to save mid-thought is unusable.
- **⌘S / Ctrl+S saves**, and the diagram re-renders from the text. Saving is
  the render trigger — the same live-reload loop an external editor drives.
- **Conflict detection.** If a file changed on disk since you opened it, the
  save stops and offers you both sides rather than overwriting.
- **A searchable file tree** covering every source under the root, including
  `!include` fragments, with right-click to create, rename or delete.
- **New workspaces from templates** — `minimal`, `system-context`, `full-c4`
  or `deployment`.

The diagram is a preview of the text, never the other way round: c4studio
never generates DSL from the model, so your comments, formatting and
`!include` structure are yours.

Select several nodes (Shift+drag, or ⌘/Ctrl+click) to align or distribute
them from the toolbar that appears, and nudge a selection with the arrow
keys — 10px with Shift. Everything persists to the layout sidecar.

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

The built SPA ships inside the package (`c4studio/webapp/static/`),
so end users need no Node toolchain. To rebuild the frontend after
changes (requires Node 20.19+ or 22.12+, what Vite asks for — distinct
from the Node 18+ that `c4 render` needs at runtime, below):

The frontend is an npm workspace: `packages/diagram-core` holds the
diagram layer (layout, node/edge components, image export) and
`frontend/` is the SPA that consumes it, so build from the repo root.

```bash
npm install
npm run build          # diagram-core, then the SPA
                       # outputs to src/c4studio/webapp/static/
# dev loop: `npm run dev --workspace c4studio-frontend`
#           (Vite :5173, proxies /api → :8090) alongside
#           `uv run c4 webapp samples/ --no-browser`
```

> **Security**: the web app has no authentication and is intended for local
> use on `127.0.0.1`. It is local-first by design — single user, no server,
> no accounts — and sharing happens through git and generated artifacts.
> The one exception is the assistant, which is off unless you pass
> `--assistant`.

### Tests

```bash
uv run pytest                      # full suite
uv run pytest tests/test_webapp    # web app tests only
```

## Starter templates
```bash
uv run c4 new                             # workspace.dsl, minimal
uv run c4 new arch.dsl --template full-c4 --name "Acme Platform"
uv run c4 new --list                      # what is available
```

| Template | What it shows |
| --- | --- |
| `minimal` | One person, one system, one view — the smallest thing that renders |
| `system-context` | A system in its context: who uses it, what it depends on |
| `full-c4` | Context, containers and components, drillable in the viewer |
| `deployment` | Containers mapped onto the infrastructure that runs them |

Existing files are never overwritten without `--force`.

## Assistant (optional, off by default)
c4studio is local-first: nothing it does reaches the network, with one
exception you have to switch on deliberately.

```bash
pip install 'c4studio[assistant]'
export ANTHROPIC_API_KEY=...
uv run c4 webapp samples/ --assistant
```

Ask for a change in words; the reply comes back as a **diff against your
buffer**, which you apply or reject. Applying only changes the editor —
nothing is written until you save.

**What leaves your machine:** the workspace source, including unsaved
changes to the file you are editing. The panel lists exactly which files
were sent. Without `--assistant` the endpoint answers 403; the API key is
read from the environment at the moment of use and is never stored, logged
or sent back. A default install pulls in no extra dependency and behaves
exactly as it did before.

## Python API

c4studio is a library as well as an app: the parser, the model and the
generators are importable, and the web app is one consumer of them.

```python
from c4studio.models import Workspace, Person, SoftwareSystem, Container, Relationship, View, ViewType

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

## Parsing
Parse Structurizr DSL or JSON files:

```python
from c4studio.parser.dsl import parse_dsl_file
from c4studio.parser.json_parser import parse_json_file

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
from c4studio.generators import FlowchartGenerator, MermaidGenerator

for view_name, mermaid_code in MermaidGenerator(ws).generate_all().items():
    print(f"{view_name}:\n{mermaid_code}\n")

# Or the flowchart target, which renders every view type:
diagrams = FlowchartGenerator(ws).generate_all()
```

From the CLI:

```bash
uv run c4 generate architecture.dsl                     # C4 (default)
uv run c4 generate architecture.dsl -f flowchart        # flowchart
uv run c4 generate architecture.dsl -f flowchart -o out # one .mmd per view
```

## Perspectives
A perspective is a named annotation you hang on elements and
relationships — security, ownership, cost, anything — and then **show over
the diagram**. What carries it keeps its place and gets a badge with its
value; everything else fades. The legend follows, listing the values
rather than the element styles the diagram is no longer painted with.

```
api = container "Payments API" "Authorises and captures." "Python, FastAPI" {
    perspectives {
        "security" "mTLS to the ledger, PCI DSS scope." "High"
    }
}
```

![The security perspective shown over a container diagram: two containers
badged "High", a person badged "Medium", the rest faded, and a legend of
the values](https://raw.githubusercontent.com/geoffkoh/c4studio/main/docs/images/perspective-overlay.png)

Colour comes from ordinary styles, matched on the perspective and
optionally on its value:

```
element "Perspective:security[value==High]" {
    background #2e7d32
    color #ffffff
}
```

The same overlay is available everywhere the diagram is:

```bash
uv run c4 render architecture.dsl --perspective security -o diagrams/
```

and in the VS Code preview through **C4Studio: Show Perspective…**. A
perspective carrying a `url` instead of a value has that value **read
live** — off by default, because the addresses come from the workspace
file; `c4 webapp --dynamic-perspectives` turns it on.

## Impact analysis
What else is involved when one element changes — asked of the model
rather than of whoever remembers:

```bash
uv run c4 impact architecture.dsl paymentsApi
uv run c4 impact architecture.dsl paymentsApi --json --depth 2
```

Dependents (what reaches it, and so may break when it changes),
dependencies (what it reaches, and so may break it), each with how many
relationships away it is, plus **the views that draw it** — so a change
advisory board knows which diagrams to open.

Containment counts in both directions: a relationship declared against a
container is one its software system takes part in, which is the same
rule the views apply when they lift an edge to the nearest visible
ancestor. An answer that ignored the hierarchy would disagree with the
diagrams it is about.

## Model standards (`c4 lint`)
Where `c4 check` asks whether a file parses, `c4 lint` asks whether it is
a good model — the review comments someone would otherwise have to make
every time:

```bash
uv run c4 lint architecture.dsl
```

Orphaned elements, missing descriptions and technologies, relationships
declared twice, and styles whose tag nothing carries (invisible
otherwise, because the legend only lists styles in use). Every finding is
a warning — a model that breaks a house style still parses and renders —
so the **exit code** is what gates CI: 1 on any finding, `--exit-zero` to
report without failing on a model nobody has linted before.

Configure it in `c4studio.lint.json` beside the workspace:

```json
{"ignore": ["missing-technology"], "naming": {"container": "^[A-Z]"}}
```

`--json` emits the same shape editors already read, so findings land in
the Studio's problems list and the VS Code Problems panel.

## Headless SVG Rendering
`c4 render` draws diagrams as standalone SVG with no browser
and no server — for CI, docs-as-code pipelines and static sites. Layout is
the same code the web app runs, so positions match what you see in the
viewer, including any layout you have saved for a view.

```bash
uv run c4 render architecture.dsl -o diagrams/   # one .svg per view
uv run c4 render architecture.dsl -v Containers  # one view to stdout
```

Each diagram carries its own title and a legend of the styles it actually
uses, so an exported file explains itself to someone who did not build it.
Pass `--no-title` or `--no-legend` to leave either out.

The output is self-contained: no external fonts or stylesheets, and theme
icons (the AWS/Azure/GCP service logos) are fetched once and embedded as
`data:` URIs, so a file renders identically wherever it is opened — even
offline. An icon that cannot be fetched is simply left out.

> **This is the only command that needs [Node.js](https://nodejs.org) 18+**
> (the renderer is bundled into the wheel, so there is no `npm install`).
> Set `C4STUDIO_NODE` if `node` is not on your `PATH`. Parsing,
> Mermaid generation, JSON export and the web app all work without it.

## Workspace JSON Export
Export any workspace (DSL or JSON) back to Structurizr workspace JSON,
round-tripping with structurizr.com, Structurizr Lite, and this package's
own parser:

```bash
uv run c4 export workspace.dsl -o workspace.json
```

Or programmatically via `c4studio.generators.json_export.export_json`.

## GitHub Action
Render the diagrams on every push and pull request, so reviewers see the
architecture change alongside the code change:

```yaml
name: Diagrams
on: [push, pull_request]

jobs:
  render:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: geoffkoh/c4studio@v0.3.0
        id: diagrams
        with:
          workspace: docs/architecture.dsl
      - uses: actions/upload-artifact@v4
        with:
          name: diagrams
          path: ${{ steps.diagrams.outputs.diagrams-path }}
```

| Input | Default | What it does |
| --- | --- | --- |
| `workspace` | *required* | The `.dsl` or `.json` file to render |
| `output` | `diagrams` | Directory for the SVGs, one per view |
| `view` | *(all)* | Render a single view key |
| `mode` | `render` | `render`, `commit` (push the files back when they change) or `comment` (comment on the PR) |
| `version` | `c4studio` | pip requirement to install; `local` uses the checkout |
| `python-version` | `3.13` | Python to set up first — runners still default to an older one than this package needs. Empty string skips the step |

The action checks the workspace before rendering, so a parse error fails
the job with diagnostics rather than a traceback, and sets a `changed`
output. Because rendering is deterministic, `mode: commit` produces no
diff when the model has not changed.

## VS Code Extension
[`editors/vscode/`](./editors/vscode/) ships a VS Code extension with
Structurizr DSL syntax highlighting and an in-editor C4 diagram preview
(the full web app in a side panel, live-reloading as you save). The preview
runs in **Viewer** mode — VS Code already has the file open in its own
editor, and a second editor writing to it behind VS Code's back is the one
thing the preview must not do. Build and install it locally:

```bash
cd editors/vscode && npm install && npm run package
code --install-extension c4studio-vscode-*.vsix
```

## Documentation
- **[DSL Reference](./docs/dsl-reference.md)** - **How to write DSL for c4studio**: every construct, the `c4studio.*` extensions, and what is silently ignored. Examples are parsed by the test suite
- **[DSL Language Support](./docs/dsl-support.md)** - Every keyword in the Structurizr DSL and whether c4studio supports it
- **[Getting Started](./docs/README.md)** - Workflow and common patterns
- **[Studio Editor Plan](./docs/studio-editor-plan.md)** - How the editor was designed and built, and the decisions behind it
- **[Migration Guide](./docs/MIGRATION.md)** - Breaking changes, including the 0.3.0 Studio-by-default flip
- **[Enterprise Roadmap](./docs/roadmap.md)** - The staged forward plan

