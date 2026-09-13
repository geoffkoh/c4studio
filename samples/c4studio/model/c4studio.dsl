// c4studio itself: the containers, and the components of the three that
// carry the interesting decisions.
//
// The shape to notice is that `core` sits under everything. The CLI, the
// web backend and the headless renderer are all consumers of one parse and
// one view graph — which is why a diagram exported in CI matches the one on
// screen rather than merely resembling it.

c4studio = softwareSystem "c4studio" "Parses Structurizr DSL, models it, and renders C4 diagrams — with an editor for the DSL that produces them." {

    // ---------------------------------------------------------------
    // The library everything else is built on
    // ---------------------------------------------------------------
    core = container "Core Library" "Parsing, the domain model, the view graph and the generators. Pure Python, no I/O beyond reading source files." "Python 3.13" {
        dslParser    = component "DSL Parser" "Tokenises and parses Structurizr DSL. Rewrites the source before tokenising — !include flattened, !script stripped, constants substituted — which is why editing is text-first and there is no DSL writer." "Python, recursive descent"
        jsonParser   = component "JSON Parser" "Reads Structurizr workspace JSON into the same model the DSL parser builds." "Python"
        sourceMap    = component "Source Map" "Maps positions in the flattened source back to the file and line they came from, so a diagnostic names the fragment rather than the root." "Python"
        expressions  = component "Expression Engine" "Resolves include/exclude expressions — tags, types, parents, relationship forms — with deferred resolution so forward references work." "Python"
        implied      = component "Implied Relationships" "Derives the relationships upstream would imply, deduplicated and linked back to what implied them." "Python"
        docsParser   = component "Docs & ADR Reader" "Loads the markdown behind !docs and !adrs." "Python"
        models       = component "Domain Model" "Typed dataclasses for the whole Structurizr metamodel: elements, views, deployment, documentation." "Python dataclasses"
        viewGraph    = component "View Graph" "Workspace + view -> nodes and edges, with C4 visibility, boundary nesting and endpoint lifting applied. The one contract every renderer consumes." "Python"
        diagnostics  = component "Diagnostics" "Structured, positioned problems. Unsupported constructs are skipped whole and reported — never executed, never allowed to consume their enclosing scope." "Python"
        mermaidGen   = component "Mermaid Generator" "C4Context/C4Container/C4Component syntax, rendered from the view graph." "Python"
        flowchartGen = component "Flowchart Generator" "Mermaid flowchart + subgraph, covering every view type including dynamic and deployment." "Python"
        jsonExport   = component "JSON Exporter" "Writes Structurizr workspace JSON back out, round-tripping what was read." "Python"
        themes       = component "Theme Loader" "Fetches theme JSON and embeds service icons as data URIs, so an exported file renders offline." "Python"
        templates    = component "Starter Templates" "Four workspaces shipped as package data — valid DSL exactly as they sit on disk, so the suite can parse each one directly." "Python"
    }

    // ---------------------------------------------------------------
    // The web app
    // ---------------------------------------------------------------
    backend = container "Web Backend" "Serves the JSON API and the built SPA. Holds all mutable state on one injected AppState rather than in module globals." "Python, FastAPI" {
        routes       = component "API Routes" "The HTTP surface: sources, views, graphs, layout, check, save, files, templates, capabilities." "FastAPI"
        capability   = component "Capability Guards" "FastAPI dependencies that make Studio/Viewer and the assistant enforceable — a route cannot forget them, so the guarantee holds against a crafted request." "FastAPI dependencies"
        loader       = component "Workspace Loader" "Loads a workspace and watches its !include fragments by mtime. A failed reload keeps serving the last good one." "Python"
        discovery    = component "Source Discovery" "Walks the tree for loadable sources, revalidated by stat rather than re-read — the 8 KB probe per candidate was 79% of the endpoint's cost." "Python"
        flowGraph    = component "React Flow Reshape" "Turns the view graph into the node/edge payload the SPA draws, and attaches saved waypoints, labels and chrome." "Python"
        modelGraph   = component "Model Graph" "The whole static model as one graph at a chosen abstraction level, for the Explorer." "Python"
        sidecar      = component "Layout Sidecar I/O" "Reads and writes per-user UI state: positions, sizes, waypoints, labels, expansion, chrome. Additive sections, so an older sidecar still loads." "Python"
        writer       = component "Source Writer" "Atomic writes with content-hash fingerprints, so an edit made elsewhere is a conflict rather than a silent overwrite. Invalid DSL still saves." "Python"
        assistant    = component "Assistant" "The only component that opens a network connection at run time. Off unless asked for; reads its key from the environment at the moment of use." "Python, anthropic SDK"
    }

    spa = container "Studio (SPA)" "The browser app: browse, read, edit, and watch the diagram follow the text." "TypeScript, React, Vite" {
        appShell     = component "App Shell" "Owns the loaded workspace, the selected view, capabilities and the live-reload poll." "React"
        apiClient    = component "API Client" "One typed fetch wrapper per endpoint, so error handling and the URL scheme live in one place." "TypeScript"
        graphPane    = component "Graph Pane" "The interactive diagram: drag, zoom, drill in, align, export. Prop-injected for its backend, which is what lets it be embedded elsewhere." "React, React Flow"
        sourcePane   = component "Source Pane" "One buffer per file, with dirty tracking, conflict resolution and save." "React"
        dslEditor    = component "DSL Editor" "CodeMirror 6 surface: highlighting, completion and lint marks over the buffer." "CodeMirror 6"
        dslLanguage  = component "DSL Language" "A StreamLanguage and completion source built from one shared vocabulary — the SPA keeps a single copy of the DSL keyword set." "TypeScript"
        fileTree     = component "File Tree" "Searchable and windowed over uniform rows, so a tree of any size keeps ~25 rows in the DOM." "React"
        explorer     = component "Explorer" "The whole model as one searchable graph, independent of any curated view." "React"
        docsPane     = component "Docs Pane" "Renders !docs sections and !adrs decisions." "React, marked"
        assistantUi  = component "Assistant Panel" "Shows a proposal as a diff against the buffer. Applying it is an ordinary edit — nothing AI-specific touches the editor." "React"
    }

    // ---------------------------------------------------------------
    // The shared diagram layer, and the two things that consume it
    // ---------------------------------------------------------------
    diagramCore = container "Diagram Core" "The renderer-agnostic diagram layer. Knows nothing about the API or app state, which is what lets the headless renderer and the SPA share it." "TypeScript, npm workspace" {
        layout       = component "Layout" "Compound dagre layout, async by contract so the engine can be swapped." "TypeScript, dagre"
        nodeViews    = component "Node & Edge Views" "The React Flow components for elements, boundaries, chrome and floating edges." "React"
        edgePaint    = component "Edge Paint" "Relationship paint applied inline rather than by stylesheet, because export re-inlines computed styles and would otherwise drop it." "TypeScript"
        imageExport  = component "Image Export" "PNG and SVG of the live canvas." "html-to-image"
        svgRender    = component "Headless SVG" "Draws the same diagram as pure SVG markup from the graph payload alone, with no DOM." "TypeScript"
    }

    renderer = container "Headless Renderer" "Committed build artefact: diagram-core bundled for Node, so the wheel renders SVG without an npm install. The only part of c4studio that needs Node at run time." "JavaScript (bundled), Node 18+"

    cli = container "CLI" "generate, render, export, check, list-views, webapp, new." "Python, click"

    // ---------------------------------------------------------------
    // What is on disk
    // ---------------------------------------------------------------
    sources = container "Workspace Sources" "The user's .dsl and .json files, including !include fragments. The source of truth; c4studio never generates them from the model." "Files on disk" "File Store"

    layoutSidecars = container "Layout Sidecars" "<source>.layout.json — per-user UI state, gitignored, written next to the source." "JSON files" "File Store"
}
