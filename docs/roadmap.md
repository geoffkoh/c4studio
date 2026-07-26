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
| **Headless CI rendering** — `pystructurizr render` → SVG/PNG/Mermaid for all views, no browser | High (enabler) | L | Server-side SVG reusing `view_graph.py` semantics. **Now also pulled by Phase 5** (Confluence export, the GitHub Action, Pages), which settles the layout-engine question: dagre is pure JS and runs headless in Node, so layout stays in `diagram-core` with one implementation and no new Python dependency. |
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

**Parked as low value:** manual edge vertices (auto-layout + curve
separation already solve edge readability; hand-placed vertices rot on
every model change).

**Open chore:** PP-50 — vite/esbuild upgrade for the frontend's npm audit
advisories.

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
JSON emitted by `webapp/view_graph.py` is the contract between them, and
each renderer exists exactly once.

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
| **Mermaid renders from the graph model** | High (correctness) | S-M | Fixes the defect below and collapses the duplicate C4 semantics. Precondition for the GitHub work. |
| **`flowchart`/`subgraph` Mermaid target** | Med-High | S | Mermaid's `C4Context`/`C4Container` types are experimental upstream, lay out poorly on dense models, and GitHub pins its own Mermaid version. Same graph model in, more reliable rendering out. |
| **Headless SVG renderer** (`diagram-core` + `pystructurizr render`) | High (enabler) | L | This is Phase 3's headless-rendering item. Serves Confluence export, the GitHub Action and Pages — and answers Phase 3's open "Python dagre-equivalent vs small Node script" question: dagre is pure JS and runs headless in Node, so layout stays in one implementation. |
| **`diagram-core` extraction** | High (enabler) | M-L | Move `frontend/src/layout.ts`, the node/edge components and export out of the SPA into a package. `GraphPane` currently imports `api.ts` and saves layout itself; that coupling must be lifted into props before it can embed anywhere. |
| **`SourceResolver` injection** | Med-High | M | `!include` (`dsl.py`), `docs.py` and `locations.py` reach for the filesystem. Replace `base_dir: Path` with a `read(name) -> str` protocol; filesystem impl stays the default, Confluence supplies its own. Good hygiene regardless — it makes the parser testable without temp dirs. |
| **Pyodide bridge** | High | M-L | Loads Pyodide, installs the pure-Python wheel, typed `parse() -> graph JSON`. Shared by Confluence and github.dev. |
| **Confluence Forge macro** | High | L | Macro + config panel, DSL in Forge storage (macro *parameters* have size limits real DSL will exceed), cached render, static SVG path first — it is the one that must work everywhere. |
| **GitHub Action** | High | M | Render every view on push/PR, commit SVGs or upload artifacts, comment on the PR. Composite action using `uv`; runners already have Python. Becomes "diagram diff on PRs" once the model diff exists. |
| **github.dev web extension** | Med-High | M | The existing extension bootstraps a Python backend via `uv` (PP-68), which cannot work in a browser tab. With the Pyodide bridge it becomes a web extension: press `.` on any GitHub repo, get interactive C4. |

### Known defect this depends on

`generators/mermaid.py` filters *elements* by view visibility but then
emits relationships raw via `all_relationships_for(visible_ids)`, so a
system context view for `samples/internet_banking.dsl` declares five
elements and then references eight container-level aliases that were never
declared (`webApp`, `apiGateway`, `db`, …). `webapp/view_graph.py` gets
this right — `_lift_to()` walks each endpoint to its nearest visible
ancestor. The C4 semantics are implemented twice and only one copy is
correct; rendering Mermaid from the graph model removes the second copy.

### Layout engine: elkjs, considered and deferred

Layout is dagre (`frontend/src/layout.ts`). dagre has no notion of
compound graphs, so nested C4 boundaries are handled by running it
recursively: each boundary lays out its children, sizes itself to their
bounding box plus label space, then joins its parent's layout as a single
large node, with edges crossing a boundary lifted to the level being laid
out. That recursion is the bulk of the module.

**elkjs** (Eclipse Layout Kernel) is the obvious alternative, and two
things make it more attractive here than usual:

- It does **compound/nested layout natively**, which is most of what that
  recursion exists to work around — and nesting to arbitrary depth is core
  to C4, not an edge case.
- It computes **orthogonal edge routes with bend points**, the same shape
  of data PP-76 added persistence for. That turns "route this edge around
  the obstacle" into something the tool can do rather than something the
  user drags by hand.

Deferred, for three reasons:

- **New npm dependency, and a heavy one.** `elk.bundled.js` is over 1 MB
  against a bundle of roughly 490 KB. Lazy loading or a worker mitigates
  it, but that is more machinery, and new dependencies are ask-first.
- **ELK's API is asynchronous.** `layoutGraph()` is called synchronously
  from `toFlow`, itself called synchronously from the fetch handler.
  Going async ripples through `GraphPane`, the expand/collapse tween and
  the stored-position path — a refactor, not a swap.
- **It unblocks nothing in Phase 5.** Headless rendering needs a layout
  engine that runs in Node; dagre already does.

**Revisit during the `diagram-core` extraction**, when layout moves into a
package anyway and the engine sits behind a boundary that can be swapped.
Doing it before then means paying the async refactor twice. Nobody has
complained about layout *quality* so far — the friction has been in
interaction — so this is an enabler for auto-routing rather than a fix.

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
- **A GitHub markdown plugin.** There is no third-party renderer API for
  github.com; Mermaid renders because GitHub ships it. Generated Mermaid
  is the integration.
- **Interactive diagrams inline in GitHub markdown.** Sanitized — no JS,
  no scripted SVG. GitHub Pages and github.dev are the interactive routes.

### Open risk to spike before committing

Forge Custom UI's CSP: WASM instantiation typically needs
`wasm-unsafe-eval`, and whether Forge permits it (via
`permissions.content.scripts`) decides the whole design. Verify against
current Atlassian docs, then prove it end to end — load Pyodide,
`micropip` the wheel, parse `samples/internet_banking.dsl`, emit workspace
JSON. Secondary: app bundle size (load the Pyodide runtime from its CDN —
that fetches code, it does not send the DSL anywhere) and the CPython
version Pyodide ships versus this project's `requires-python = ">=3.13"`
floor, which looks like metadata rather than a real dependency (no PEP 695
generics or other 3.13-only syntax in the core).

If the spike fails, the damage is contained: view and export are already
Python-free, so only the authoring path needs a different answer.

### Sequencing

Mermaid-from-graph-model → flowchart target → headless renderer →
GitHub Action (all useful to the local tool on their own merits, and none
of them depend on Forge) → Pyodide spike → `SourceResolver` → Confluence
macro → github.dev.

## Delivery conventions (unchanged)

One Jira ticket per item, branch per ticket, PR-first merge, wait for
merge before the next ticket. TDD; `uv run pytest` + ruff + mypy green
per PR; no new Python/npm dependencies without asking; live verification
on the sample workspaces; update `docs/structurizr-parity.md` as items
land.
