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

**Phase 5 reordered the priorities and has now delivered its GitHub
half** (PP-88…PP-95): publishing consumed the same foundation as the
enterprise features — headless rendering above all — so Phase 3's renderer
was pulled forward and shipped. The Confluence half is parked; see Phase 5.

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
| ~~**Full-model explorer + search**~~ **shipped, PP-69** — whole-model graph page + element/relationship search across all `!include` fragments | High | M-L | Reuse React Flow + dagre (no new deps); jump from a result to the views containing the element. |
| **Governance inventory** — owner/team/lifecycle from element `properties` in the UI + CMDB/tech-radar report (HTML/CSV) | High | M | `pystructurizr inventory`; makes the model the system of record. |

## Phase 3 — Foundation B: headless rendering → docs-as-code

| Feature | Value | Cx | Notes |
|---|---|---|---|
| ~~**Headless CI rendering**~~ **shipped, PP-93** — `pystructurizr render` → SVG for all views, no browser | High (enabler) | L | Server-side SVG reusing `graph/view_graph.py` semantics. **Now also pulled by Phase 5** (Confluence export, the GitHub Action, Pages), which settles the layout-engine question: dagre is pure JS and runs headless in Node, so layout stays in `diagram-core` with one implementation and no new Python dependency. |
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

## Phase 5 — Publishing surfaces: GitHub (Confluence parked)

Take the diagrams to where the audience already reads. **The GitHub half
shipped** (PP-88, PP-89, PP-93, PP-95): Mermaid rendered from the graph
model, a `flowchart`/`subgraph` target covering every view type, headless
SVG, and an Action that renders on push and PR.

**The Confluence half is parked (August 2026)** — the integration proved
more complex than this plan assumed, and other approaches will be
considered later. What that removes: the Forge macro, the Pyodide bridge
and the github.dev web extension.

### What the Confluence attempt established

Kept deliberately, so a future attempt starts informed rather than
re-deriving it. The two original constraints — no service to run, and the
DSL must not leave Atlassian — pointed at running the real parser in the
browser under Pyodide/WASM. That much works:

- **Forge Custom UI does run WebAssembly.** Forge offers no
  `wasm-unsafe-eval`; `unsafe-eval` is the superset and admits WASM. Proved
  on a real site: an 8-byte module instantiated in 2 ms, Pyodide 0.28
  loaded from jsDelivr in 1,393 ms, and `micropip` installing the wheel
  plus parsing DSL took 1,972 ms — roughly 3.4 s for an author on a cold
  macro edit, once.
- **The parser runs unmodified under Pyodide**, including `!include`,
  `!docs` and `!adrs` against the virtual filesystem.
- **The wheel's dependencies are the obstacle**, not the parser.
  `uvicorn[standard]` pulls compiled packages with no pure-Python wheels,
  so `micropip` refuses the wheel unless the web stack is split into an
  extra — a breaking change for every existing user, which is not worth
  making for a parked feature. Reverted with the rest of this track.
- **MicroPython is not an alternative** — see the rejected options below.

The complexity that parked it is not any single blocker; it is the number
of moving parts a working macro needs at once: Forge storage for DSL that
exceeds macro parameter limits, staleness hashing, a Pyodide bridge, a
`SourceResolver` so `!include` resolves against Confluence rather than a
filesystem, and an export path for PDF/email where iframes do not render.

### Items

| Feature | Value | Cx | Notes |
|---|---|---|---|
| ~~**Mermaid renders from the graph model**~~ **shipped, PP-88** | High (correctness) | S-M | Fixed the defect below and collapsed the duplicate C4 semantics. `systemLandscape` came along nearly free; dynamic, deployment and filtered views still emit the unsupported comment and are the flowchart target's job. |
| ~~**`flowchart`/`subgraph` Mermaid target**~~ **shipped, PP-89** | Med-High | S | Mermaid's `C4Context`/`C4Container` types are experimental upstream, lay out poorly on dense models, and GitHub pins its own Mermaid version. Same graph model in, more reliable rendering out — and it took the view types the C4 target skips (dynamic, deployment, filtered), so every view now renders. `generate -f flowchart`; the C4 target stays the default. |
| ~~**Headless SVG renderer**~~ **shipped, PP-93** | High (enabler) | L | This was Phase 3's headless-rendering item. Serves Confluence export, the GitHub Action and Pages — and answers Phase 3's open "Python dagre-equivalent vs small Node script" question: dagre is pure JS and runs headless in Node, so layout stays in one implementation. |
| ~~**`diagram-core` extraction**~~ **shipped, PP-92** | High (enabler) | M-L | Move `frontend/src/layout.ts`, the node/edge components and export out of the SPA into a package. `GraphPane` currently imports `api.ts` and saves layout itself; that coupling must be lifted into props before it can embed anywhere. Also carries the settled layout-engine decision below: migrate to `@dagrejs/dagre` and give layout an async interface. |
| **`SourceResolver` injection** | Med | M | `!include` (`dsl.py`), `docs.py` and `locations.py` reach for the filesystem. Replace `base_dir: Path` with a `read(name) -> str` protocol. Kept after the Confluence parking because it stands on its own: it makes the parser testable without temp dirs. |
| ~~**GitHub Action**~~ **shipped, PP-95** | High | M | Renders every view on push/PR; `mode` selects artifact, commit or PR comment. Composite action installing the published wheel with pip — runners already have Python *and* Node, which `render` needs. `.github/workflows/diagrams.yml` dogfoods it against `samples/hedge_fund`. Becomes "diagram diff on PRs" once the model diff exists. |

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
- a browser-hosted surface ships that already carries a large runtime, next
  to which elk's weight stops mattering. (This trigger originally named the
  Confluence macro and github.dev; both are parked, so it cannot fire
  today.)

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

### The Pyodide measurements, for whoever revisits this

Run August 2026 against Pyodide 314.0.4 in Node, and repeated inside a
real Forge Custom UI iframe (see the parked-track summary above):

| | Node | Forge iframe |
| --- | --- | --- |
| Cold start | ~1.1 s | 1,393 ms (CDN) |
| Wheel install | 36 ms | — |
| Install + parse | — | 1,972 ms |
| `internet_banking.dsl` parse | 2 ms | — |
| `hedge_fund` with `!include`/`!docs`/`!adrs` | 8 ms | — |

Pyodide 314 ships CPython 3.14.2 and `pyodide@0.28` on the CDN ships
3.13.2 — both clear the `requires-python = ">=3.13"` floor, but the pin
decides which.

### Sequencing

~~Mermaid-from-graph-model~~ (PP-88) → ~~flowchart target~~ (PP-89) →
~~`diagram-core` extraction~~ (PP-92) → ~~headless renderer~~ (PP-93) →
~~GitHub Action~~ (PP-95) (all useful to the local tool on their
own merits, and none of them depend on Forge) → ~~Pyodide spike~~
(PP-96, everything but the Forge CSP question) → dependency-free core
wheel → Forge CSP verification → `SourceResolver` → Confluence macro →
github.dev.

**Next up: the Forge CSP verification**, the one remaining item that can
invalidate a design rather than merely cost time. Splitting the core's
dependencies out of the wheel can proceed in parallel, since it is
worthwhile on its own.

## Delivery conventions (unchanged)

One Jira ticket per item, branch per ticket, PR-first merge, wait for
merge before the next ticket. TDD; `uv run pytest` + ruff + mypy green
per PR; no new Python/npm dependencies without asking; live verification
on the sample workspaces; update `docs/structurizr-parity.md` as items
land.
