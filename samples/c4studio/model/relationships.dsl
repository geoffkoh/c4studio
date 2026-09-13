// Relationships, declared at the most specific level the model knows.
// Coarser views lift them to the visible ancestor, so the context and
// container diagrams stay readable without anything being restated.

// --- People ---
architect -> spa        "Models and reads architecture in"
developer -> spa        "Edits the DSL in"
developer -> cli        "Generates and checks diagrams with"
developer -> vscode     "Previews diagrams while editing with"
reviewer  -> git        "Reads rendered diagrams committed to"

// --- Getting in ---
cli      -> core        "Parses and generates through"
backend  -> core        "Parses and builds view graphs through"
action   -> cli         "Invokes `c4 render`"
ci       -> action      "Runs on every push"

// --- Inside the core library ---
dslParser    -> sourceMap    "Records flattened positions in"
dslParser    -> models       "Builds"
dslParser    -> diagnostics  "Reports skipped constructs to"
dslParser    -> docsParser   "Loads !docs and !adrs via"
jsonParser   -> models       "Builds"
viewGraph    -> models       "Reads"
viewGraph    -> expressions  "Resolves includes and excludes with"
viewGraph    -> themes       "Resolves element and relationship styles with"
implied      -> models       "Adds derived relationships to"
mermaidGen   -> viewGraph    "Renders from"
flowchartGen -> viewGraph    "Renders from"
jsonExport   -> models       "Serialises"
templates    -> dslParser    "Are parse-tested by"

// --- Inside the backend ---
routes     -> capability  "Is guarded by"
routes     -> loader      "Loads and reloads workspaces through"
routes     -> discovery   "Lists sources through"
routes     -> flowGraph   "Builds view payloads with"
routes     -> modelGraph  "Builds the explorer graph with"
routes     -> sidecar     "Reads and writes UI state through"
routes     -> writer      "Saves DSL through"
routes     -> assistant   "Forwards assistant requests to"
loader     -> dslParser   "Parses with"
flowGraph  -> viewGraph   "Reshapes the output of"
modelGraph -> models      "Walks"
writer     -> sources     "Writes atomically to"
loader     -> sources     "Reads and watches"
sidecar    -> layoutSidecars "Reads and writes"

// --- Inside the SPA ---
appShell    -> apiClient   "Calls the backend through"
appShell    -> graphPane   "Renders the selected view with"
appShell    -> sourcePane  "Renders the editor with"
appShell    -> explorer    "Renders the whole model with"
appShell    -> docsPane    "Renders documentation with"
appShell    -> fileTree    "Browses sources with"
sourcePane  -> dslEditor   "Embeds"
sourcePane  -> assistantUi "Opens"
dslEditor   -> dslLanguage "Highlights and completes with"
graphPane   -> diagramCore "Lays out and draws with"
apiClient   -> routes      "Calls" "JSON over HTTP"

// --- Inside the VS Code extension ---
// Declared here rather than on the container, so the component view says
// something; the container and context views lift them to `vscode`.
previewMgr  -> resolver "Finds a runnable backend through"
previewMgr  -> routes   "Spawns, probes and embeds" "localhost HTTP"
previewMgr  -> spa      "Shows in a webview iframe"
diagnostics -> resolver "Finds the same backend through"
diagnostics -> cli      "Runs `c4 check --json` with"
resolver    -> cli      "Locates or installs"
grammar     -> sources  "Highlights"

// --- Inside diagram-core ---
nodeViews -> layout      "Is positioned by"
nodeViews -> edgePaint   "Paints relationships with"
svgRender -> layout      "Reuses"
svgRender -> edgePaint   "Reuses"

// --- The headless path ---
renderer  -> svgRender   "Is the bundled form of"
cli       -> renderer    "Pipes the graph payload to"

// --- Out to the network ---
assistant -> anthropic   "Asks for a rewritten file" "HTTPS"
themes    -> themeCdn    "Fetches theme JSON and icons from" "HTTPS"
pypi      -> cli         "Distributes"
developer -> git         "Commits the DSL to"
