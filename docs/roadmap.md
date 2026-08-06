# Enterprise roadmap

The staged plan for making pystructurizr an enterprise-grade,
**local-first** solution-architect toolset (no multi-user server/auth;
team sharing happens via git and generated artifacts). Phase 1 shipped in
July 2026 — Jira PP-60…PP-63, PRs #38–#41: workspace JSON export with
structurizr round-trip, remote themes + cloud-provider icons + the full
shape set, filtered views, and keyboard shortcuts.

Phases 2–4 were parked while the VS Code integration
(`editors/vscode/`) was built; that shipped (PP-64…PP-68) along with the
PyPI release (PP-67), so they are **unparked**. PP-69 took the full-model
explorer out of Phase 2 ahead of the rest. Value ratings come from a
solution-architect review of real workflows (solution reviews,
governance boards, CABs, onboarding). Complexity: S ≤ 1 ticket,
M = 1–2, L = 3+ / new subsystem.

**Phase 5 changes the priority order.** Publishing to Confluence and
GitHub turns out to consume the same two foundations as the enterprise
features — headless rendering above all — so the Phase 3 items are now
pulled by two independent demands. Read Phase 5 before scheduling Phase 2
or 3.

The structural insight behind the ordering: the three genuinely
differentiating features — **model lint in CI, diagram diff on PRs, and
impact analysis** — all fall out of two shared foundations, a public
**model-query layer** (Phase 2) and **headless rendering** (Phase 3).
Build each foundation once, harvest it repeatedly. The metamodel already
carries `properties` and `perspectives` on every element, so the
governance and overlay features are UI/reporting work, not model work.

## Phase 2 — Foundation A: model-query layer → model intelligence

| Feature | Value | Cx | Notes |
|---|---|---|---|
| **Public query layer + CLI** — `pystructurizr query` over elements/relationships/tags/properties, JSON/CSV out, transitive closure | High (enabler) | M | New `model/query.py`. Everything below consumes it; feeds scripts/CMDB sync. The filtered-view tag predicate (PP-62) is its seed. |
| **Model lint/validation** — orphans, missing description/technology, duplicate relationships, naming conventions; configurable ruleset; CLI exit code for CI | High | M | `pystructurizr lint`; rules as small classes. How standards get enforced without review bottlenecks. |
| **Full-model explorer + search** — whole-model graph page + element/relationship search across all `!include` fragments | High | M-L | Reuse React Flow + dagre (no new deps); jump from a result to the views containing the element. |
| **Governance inventory** — owner/team/lifecycle from element `properties` in the UI + CMDB/tech-radar report (HTML/CSV) | High | M | `pystructurizr inventory`; makes the model the system of record. |

## Phase 3 — Foundation B: headless rendering → docs-as-code

| Feature | Value | Cx | Notes |
|---|---|---|---|
| **Headless CI rendering** — `pystructurizr render` → SVG/PNG/Mermaid for all views, no browser | High (enabler) | L | Server-side SVG reusing `graph/view_graph.py` semantics. **Now also pulled by Phase 5** (Confluence export, the GitHub Action, Pages), which settles the layout-engine question: dagre is pure JS and runs headless in Node, so layout stays in `diagram-core` with one implementation and no new Python dependency. |
| **Static HTML site export** — self-contained site (diagrams + docs + ADRs + inventory) for any static host/Confluence | High | M-L | *The* sharing story for a local-first tool. Must embed fetched theme icons as data URIs. |
| **Diagram diff** — two git revisions compared: added/removed/changed elements & relationships per view, visual overlay + text report | High | L | `pystructurizr diff rev1 rev2` for PR comments; model diff on the query layer, overlay via the renderer. |

## Phase 4 — Differentiators & authoring depth

| Feature | Value | Cx | Notes |
|---|---|---|---|
| **Impact analysis** — transitive dependents/dependencies + affected views for a chosen element | High | M | The most-asked change-advisory-board question; query-layer walk + UI highlight mode. |
| **Perspectives overlays** — security/data/infra per-element overlays | Med-High | M | Parsed already; toolbar overlay selector + badge/tint rendering. |
| **Workspace composition / landscape roll-up** — stitch per-team workspaces (`extends`/federation) into one enterprise landscape | High | L | The real "enterprise" scope gap; align DSL semantics with upstream `extends`. |
| **ADR workflow tooling** — CLI create/supersede, ADR↔element links, status dashboard | Med | M | Templates + git already cover much; links add traceability. |
| **In-browser DSL editor** — diagnostics + element-id autocomplete | Med | L | Live reload + external editor already tight; needs an editor component dep (ask first). |
| **Scaffolding** — `pystructurizr init` org templates; deterministic diff-friendly layout sidecars | Med | S-M | Onboarding ergonomics. |

**Previously parked, now shipped:** manual edge vertices (PP-76). The
original reasoning — auto-layout plus curve separation already solve edge
readability, and hand-placed vertices rot on every model change — missed
that the metamodel already carries `Vertex` and `RelationshipView.vertices`,
so this is Structurizr fidelity rather than decoration. The rot concern was
addressed by keying bend points to edge ids that are numbered per endpoint
pair instead of by position in the view's edge list, so an unrelated
relationship elsewhere in the view no longer renumbers them. Bend points
live in the layout sidecar as per-user UI state, and Reset layout clears
them along with node positions.

**Also shipped:** PP-50 — the vite/esbuild upgrade that cleared the
frontend's npm audit advisories.

## Phase 5 — Publishing surfaces: Confluence and GitHub

Take the diagrams to where the audience already reads: a Confluence Cloud
macro that renders Structurizr DSL (interactive *and* as a static image),
and GitHub rendering of models committed alongside the code.

### Fixed constraints

Two user constraints rule out most of the obvious designs, and everything
below follows from them:

1. **No additional service to run.** Nothing that requires hosting,
   uptime or an on-call rota.
2. **The DSL stays inside Atlassian.** Data governance; model source must
   not be shipped to a third-party backend.

### The architecture

The Python core (`models/`, `parser/`, `generators/`) is **stdlib-only** —
`pydantic` appears once in the whole tree, in `webapp/server.py`, and
`click`/`fastapi`/`uvicorn` are CLI and webapp only. No compiled wheels
means the real parser runs under **Pyodide/WASM**, so nothing is ported
and nothing is hosted. `parse_dsl(source, base_dir=None)` already takes a
string, which is the entry point the browser needs.

Parsing is split by *when* it happens:

- **Author time** (macro editor, in the iframe): Pyodide runs
  pystructurizr, produces **workspace JSON**, stores it next to the DSL in
  Forge storage with a hash for staleness. Costs a one-off second or two.
- **View time** (every page load): no Python. The shared TypeScript
  package renders the stored JSON.
- **Export time** (PDF/Word/email/mobile, where iframes do not render):
  the Forge resolver is Node and the renderer is pure JS, so static SVG is
  produced there.

Two packages carry every surface. Python owns
`DSL → Workspace → graph JSON → Mermaid text`; TypeScript (`diagram-core`)
owns `graph JSON → layout → React Flow canvas | headless SVG`. The graph
JSON emitted by `graph/view_graph.py` is the contract between them, and
each renderer exists exactly once. PP-88 moved that module out of
`webapp/` for exactly this reason — it is consumed by the CLI and the
Mermaid generator, not just the web app.

| Surface | New code beyond the two packages |
|---|---|
| Studio SPA | none — consumes `diagram-core` |
| Confluence macro | macro + Forge storage + Pyodide host |
| GitHub markdown | none — generated Mermaid, rendered natively |
| GitHub Action | `action.yml` + thin wrapper over `pystructurizr render` |
| GitHub Pages | site template around `diagram-core` |
| VS Code desktop | already shipped (PP-64…PP-68) |
| github.dev / vscode.dev | swap the backend call for the Pyodide bridge |

### Items

| Feature | Value | Cx | Notes |
|---|---|---|---|
| ~~**Mermaid renders from the graph model**~~ **shipped, PP-88** | High (correctness) | S-M | Fixed the defect below and collapsed the duplicate C4 semantics. `systemLandscape` came along nearly free; dynamic, deployment and filtered views still emit the unsupported comment and are the flowchart target's job. |
| ~~**`flowchart`/`subgraph` Mermaid target**~~ **shipped, PP-89** | Med-High | S | Mermaid's `C4Context`/`C4Container` types are experimental upstream, lay out poorly on dense models, and GitHub pins its own Mermaid version. Same graph model in, more reliable rendering out — and it took the view types the C4 target skips (dynamic, deployment, filtered), so every view now renders. `generate -f flowchart`; the C4 target stays the default. |
| ~~**Headless SVG renderer**~~ **shipped, PP-93** | High (enabler) | L | This was Phase 3's headless-rendering item. Serves Confluence export, the GitHub Action and Pages — and answers Phase 3's open "Python dagre-equivalent vs small Node script" question: dagre is pure JS and runs headless in Node, so layout stays in one implementation. |
| **`diagram-core` extraction** | High (enabler) | M-L | Move `frontend/src/layout.ts`, the node/edge components and export out of the SPA into a package. `GraphPane` currently imports `api.ts` and saves layout itself; that coupling must be lifted into props before it can embed anywhere. Also carries the settled layout-engine decision below: migrate to `@dagrejs/dagre` and give layout an async interface. |
| **`SourceResolver` injection** | Med-High | M | `!include` (`dsl.py`), `docs.py` and `locations.py` reach for the filesystem. Replace `base_dir: Path` with a `read(name) -> str` protocol; filesystem impl stays the default, Confluence supplies its own. Good hygiene regardless — it makes the parser testable without temp dirs. |
| **Pyodide bridge** | High | M-L | Loads Pyodide, installs the pure-Python wheel, typed `parse() -> graph JSON`. Shared by Confluence and github.dev. |
| **Confluence Forge macro** | High | L | Macro + config panel, DSL in Forge storage (macro *parameters* have size limits real DSL will exceed), cached render, static SVG path first — it is the one that must work everywhere. |
| ~~**GitHub Action**~~ **shipped, PP-95** | High | M | Renders every view on push/PR; `mode` selects artifact, commit or PR comment. Composite action installing the published wheel with pip — runners already have Python *and* Node, which `render` needs. `.github/workflows/diagrams.yml` dogfoods it against `samples/hedge_fund`. Becomes "diagram diff on PRs" once the model diff exists. |
| **github.dev web extension** | Med-High | M | The existing extension bootstraps a Python backend via `uv` (PP-68), which cannot work in a browser tab. With the Pyodide bridge it becomes a web extension: press `.` on any GitHub repo, get interactive C4. |

### The defect this fixed (PP-88, resolved)

`generators/mermaid.py` filtered *elements* by view visibility but then
emitted relationships raw via `all_relationships_for(visible_ids)`, with no
endpoint lifting. Every static view in every sample was affected, not just
the reported one: the `samples/internet_banking.dsl` system context view
declared five elements and referenced eight undeclared container aliases
(`webApp`, `apiGateway`, `db`, …), and `samples/hedge_fund` reached 30
undeclared aliases on a single view. `graph/view_graph.py` had it right all
along — `_lift_to()` walks each endpoint to its nearest visible ancestor —
so the fix was to delete the second copy of the semantics rather than
patch it. The sweep that proved it is now a test
(`tests/test_generators/test_mermaid_graph_model.py`): for every view of
every sample, each `Rel()` endpoint must be an alias the same diagram
declares.

Rendering from the graph model also corrected `include *` on system
context views, which used to pull in every person and system in the model
instead of the scope plus its directly related elements.

### Layout engine: settled (August 2026, supersedes PP-77's deferral)

Layout is dagre (`frontend/src/layout.ts`). dagre has no notion of
compound graphs, so nested C4 boundaries are handled by running it
recursively: each boundary lays out its children, sizes itself to their
bounding box plus label space, then joins its parent's layout as a single
large node, with edges crossing a boundary lifted to the level being laid
out. That recursion is the bulk of the module.

**The decision: keep dagre behind an async seam — and change engine only
on a named trigger, judged on layout quality.** The async seam landed
with the `diagram-core` extraction (PP-92):
`layout(nodes, edges, direction): Promise<Node[]>`, synchronous dagre
inside, every caller awaiting. That is what makes a different engine a
swap rather than a refactor.

The `@dagrejs/dagre` migration this section originally prescribed was
**tried and reverted** — see the measurement below. It is not the free
hygiene upgrade it looked like.

**Adopt elkjs when one of these happens**, and not merely because it
would be nicer:

- someone asks for orthogonal auto-routing;
- a real model lays out visibly badly under recursive dagre;
- the Confluence macro or github.dev surfaces ship — those pages already
  load a Pyodide runtime, next to which elk's weight stops mattering.

#### What the numbers actually are

Measured August 2026, not estimated. The earlier "over 1 MB against a
bundle of roughly 490 KB" was in the right direction but compared raw
bytes to raw bytes:

| | raw | gzip |
| --- | --- | --- |
| current app bundle | 470 KB | **151 KB** |
| `elk.bundled.js` | 1.61 MB | **467 KB** |
| worker split: `elk-api.js` (main bundle) | 9.8 KB | 3 KB |
| worker split: `elk-worker.min.js` (deferred) | 1.60 MB | 462 KB |

Inlining elk is 4.1× the gzipped bundle; a worker split keeps the main
bundle nearly unchanged but still pays 462 KB on first layout. That cost
lands on the PyPI wheel and the `.vsix`, not on a localhost viewer —
which is why the browser surfaces, where it would be network weight, are
also where it stops mattering relative to Pyodide.

#### The maintained fork is not coordinate-compatible (PP-92, measured)

`@dagrejs/dagre@3.1.0` is the maintained fork of `dagre@0.8.5`: same API,
own types, no lodash, and it shrinks the bundle by 34.5 KB raw / 9.6 KB
gzip. It also **changes the layout**. Running the *same* `layout.ts`
against both engines over ten real sample view payloads:

| | |
| --- | --- |
| views compared | 10 |
| identical | 1 |
| differ, horizontal ordering only | 7 |
| differ, with nodes changing rank | 2 (both cyclic) |

The rank changes come from **cycle-breaking**, not tie-breaking, and are
not tunable — `network-simplex`, `tight-tree` and `longest-path` all
agree with each other and disagree with 0.8.5. The visible case: on
`samples/internet_banking.dsl`'s system context view, `customer` moves
from the top rank to the bottom (y=55 → y=685) because the
`email -> customer` notification edge closes a cycle. A Person at the
bottom of a C4 context diagram is against convention.

So the engine stays on `dagre@0.8.5`, stale and lodash-laden, until the
engine question is decided on its merits. Nobody's saved layout was ever
at risk — sidecars store absolute positions keyed by element id — but
every *auto* layout would have shifted, as a side effect of a dependency
upgrade nobody asked for. If a future engine change is taken, the same
harness should be re-run and the shift accepted deliberately.

#### Correction: the async objection was overstated

PP-77 recorded that going async "ripples through `GraphPane`, the
expand/collapse tween and the stored-position path — a refactor, not a
swap." That is wrong, and it was one of the three reasons for deferring.
There are exactly two `layoutGraph` call sites — `GraphPane.tsx` and
`ExplorerPane.tsx`, both inside their `toFlow` helper — and **both are
already invoked from inside a `.then()` callback**. The expand/collapse
tween consumes layout *results* and never calls layout itself; expanding
re-fetches through the same promise chain. Making layout async is a
contained change, which is exactly why the async seam is cheap enough to
put in now.

#### What elk would still buy, when the trigger comes

- **Compound/nested layout natively**, which is most of what the
  recursion exists to work around — nesting to arbitrary depth is core to
  C4, not an edge case. Roughly 100 of `layout.ts`'s 284 lines.
- **Orthogonal edge routes with bend points**, the same shape of data
  PP-76 added persistence for: routing around an obstacle becomes
  something the tool does rather than something the user drags.

Nobody has complained about layout *quality*; the friction has been
interaction, addressed by PP-73…PP-76. elk remains an enabler for
auto-routing, not a fix for a defect.

### Rejected options — do not re-litigate

- **Forge Remote to a hosted FastAPI service.** Reuses all the Python, but
  breaks both constraints: something to run, and the DSL leaves Atlassian.
- **Porting the parser to TypeScript.** ~6,200 LOC (parser 3,193, models
  1,105, generators 936, view_graph/graph/themes 1,257) plus 5,094 lines
  of tests to mirror, and a permanent parity tax on every DSL feature.
- **Grammar codegen (ANTLR targets, tree-sitter).** Shares only the syntax
  layer; `dsl.py` is a hand-written line/regex parser, so adopting it
  rewrites both sides, and the semantics — implied relationships,
  include/exclude resolution, view scoping, style cascade — stay
  duplicated. That is the expensive part.
- **MicroPython instead of Pyodide.** Its WASM build is ~1.5 MB against
  Pyodide's ~13 MB, which is genuinely tempting — and it cannot run this
  code. Checked August 2026, three independent blockers: MicroPython's
  `re` documents that named groups `(?P<name>...)` and counted
  repetitions `{m,n}` are **not supported**, and 31 of the core's 38
  patterns use named groups (the tokenizer is one alternation of them);
  `dataclasses` does not exist in micropython-lib (`python-stdlib`,
  `python-ecosys`, `micropython` and `unix-ffi` all checked) and the model
  is 38 dataclasses; `enum` and `typing` are likewise absent, against 16
  enum classes. Making 7,388 lines of core run there is the
  port-the-parser cost in a less pleasant language. The size argument also
  matters less than it looks: Pyodide loads once at *author* time, and
  view time is already Python-free.

- **A GitHub markdown plugin.** There is no third-party renderer API for
  github.com; Mermaid renders because GitHub ships it. Generated Mermaid
  is the integration.
- **Interactive diagrams inline in GitHub markdown.** Sanitized — no JS,
  no scripted SVG. GitHub Pages and github.dev are the interactive routes.

### Open risk: Forge's CSP (the rest of the spike is done)

**Everything that could be proved off Atlassian, has been** — run in Node
against Pyodide 314.0.4, August 2026:

| Question | Answer |
| --- | --- |
| Does Pyodide's CPython satisfy `requires-python = ">=3.13"`? | **Yes** — Pyodide 314 ships CPython **3.14.2**. Not the blocker it looked like. |
| Does our own wheel install under `micropip`? | **Yes**, with `deps=false` (see below). 36 ms. |
| Does the parser actually run? | **Yes.** `samples/internet_banking.dsl` parses in **2 ms**; workspace JSON export and Mermaid generation both work. |
| Does the *hard* sample work — `!include`, `!docs`, `!adrs`? | **Yes**, against Pyodide's virtual filesystem: `samples/hedge_fund` gives 10 systems, 20 containers, 13 views, 2 deployment nodes, 3 doc sections, 3 ADRs, no warnings, in **8 ms**. |
| Cold start? | **~1.1 s** to boot Pyodide, plus 36 ms to install the wheel. The roadmap's "a one-off second or two" was right. |

Two findings that change the plan:

- **The wheel cannot install with its dependencies.** `uvicorn[standard]`
  pulls `httptools`, `watchfiles` and `uvloop`, which are compiled and
  have no pure-Python wheels, so `micropip` refuses. `deps=false` works
  because the core genuinely is stdlib-only — but relying on that flag is
  fragile. `click`/`pydantic`/`fastapi`/`uvicorn` should become optional
  extras so the core wheel is dependency-free.
- **`!include` works without `SourceResolver`** if the host writes the DSL
  fragments into the virtual filesystem first. That does not retire the
  `SourceResolver` item — Confluence storage is not a filesystem, and
  faking one for every include is worse than injecting a `read()` — but it
  does mean the Confluence macro is not *blocked* on it.

**Forge Custom UI runs WebAssembly — measured, not inferred (PP-98,
August 2026).** The design survives.

Checking the docs first narrowed the question: Atlassian documents exactly
five values for `permissions.content.scripts` — `unsafe-inline`,
`unsafe-hashes`, `unsafe-eval`, `blob:` and script hashes.
**`wasm-unsafe-eval`, the permission this section originally named, does
not exist in Forge.** `unsafe-eval` is the CSP superset that also admits
WASM compilation, and deploying a real app to a real Confluence site
proved it behaves that way:

| Step, inside the Custom UI iframe | Result |
| --- | --- |
| Instantiate an 8-byte WebAssembly module | **yes — 2 ms** |
| Load Pyodide 0.28 from jsDelivr | yes — 1,393 ms |
| `micropip` the wheel and parse DSL | yes — 1,972 ms |

So an author waits roughly **3.4 s** on a cold macro edit — the same order
as the "one-off second or two" the plan assumed, and three times PP-96's
Node-only figure. Both are one-off: parsing happens at author time, the
result is stored as workspace JSON, and view time stays Python-free.

Two manifest details worth carrying into the real macro, both learnt the
hard way here:

- `app.runtime` is required by the schema **even for an app with no
  functions**. A static Custom UI resource still needs `runtime: name:
  nodejs22.x`.
- Egress permissions take the `- address: https://...` object form. The
  bare-string form deploys and installs, but `forge lint` flags it as
  deprecated.

Also note the CDN pin decides the Python version: `pyodide@0.28` ships
CPython **3.13.2** where the npm `pyodide@314` used in PP-96 ships 3.14.2.
Both clear the `>=3.13` floor, but the pin is load-bearing.

`spikes/forge-csp/` holds the app that established this. It is throwaway —
delete it once the Confluence macro exists, or promote it.

Had it failed, the damage would have been contained — view and export are
already Python-free, so only the authoring path needed a different answer.
That contingency is now moot.

### Sequencing

~~Mermaid-from-graph-model~~ (PP-88) → ~~flowchart target~~ (PP-89) →
~~`diagram-core` extraction~~ (PP-92) → ~~headless renderer~~ (PP-93) →
~~GitHub Action~~ (PP-95) (all useful to the local tool on their
own merits, and none of them depend on Forge) → ~~Pyodide spike~~
(PP-96, everything but the Forge CSP question) → ~~dependency-free core
wheel~~ (PP-97) → ~~Forge CSP verification~~ (PP-98) → `SourceResolver` → Confluence macro →
github.dev.

**Next up: `SourceResolver` and then the Confluence macro.** Nothing
unproven stands between here and a working macro — the CSP question that
could have invalidated the design is answered, the parser runs in the
iframe, and the wheel installs from the app's own resources.

## Delivery conventions (unchanged)

One Jira ticket per item, branch per ticket, PR-first merge, wait for
merge before the next ticket. TDD; `uv run pytest` + ruff + mypy green
per PR; no new Python/npm dependencies without asking; live verification
on the sample workspaces; update `docs/structurizr-parity.md` as items
land.
