# CLAUDE.md: c4studio

> **Scope:** This file governs the c4studio repository and supersedes any
> workspace-level guidance describing other projects for all work under
> `c4studio/`. It is self-contained: every rule that applies here is stated
> here.

## Project Overview

c4studio is a Python implementation of [Structurizr](https://structurizr.com/):
it parses Structurizr DSL and workspace JSON into a typed domain model, generates
Mermaid C4 diagrams, and ships a local-first viewer — a FastAPI backend serving a
React SPA that renders views as interactive React Flow graphs. A VS Code extension
in `editors/vscode/` embeds that viewer as a diagram preview.

Published on PyPI as **`c4studio`**; the import package is `c4studio` and
the CLI is `c4`. It was `pystructurizr-studio` / `pystructurizr` through 0.1.0
— see `docs/MIGRATION.md`. Only the conda env below still carries the old
name.

**Local-first by design.** No multi-user server, no auth, no workspace locking or
branches. Sharing happens through git and generated artifacts. Do not propose
features that assume a hosted multi-user deployment.

## Tech Stack & Architecture

- **Language:** Python 3.13+, `uv` for dependency and env management.
- **Pattern:** Domain-driven design, test-driven development.
- **Frontend:** an npm **workspace** at the repo root. `packages/diagram-core`
  holds the renderer-agnostic diagram layer (layout, React Flow node/edge
  components, image export); `frontend/` is the Vite + React SPA that consumes
  it. React Flow + dagre for graph layout. `npm run build` writes to
  `src/c4studio/webapp/static/` — a **committed** bundle, so the wheel
  ships a working UI and end users never need Node.

### Module map

| Path | Responsibility |
| --- | --- |
| `src/c4studio/models/` | The domain model: `workspace`, `elements`, `views`, `deployment`, `documentation`, `enums`. |
| `src/c4studio/parser/` | `dsl.py` (DSL parser), `json_parser.py`, `expressions.py` (include/exclude engine), `implied.py`, `docs.py`, `locations.py` (source spans for go-to-definition). |
| `src/c4studio/graph/` | `view_graph.py` — workspace + view → `{nodes, edges}` with C4 visibility, boundary nesting and endpoint lifting applied. The shared contract every renderer consumes; depends only on `models/` and `themes.py`. |
| `src/c4studio/generators/` | `mermaid.py` (Mermaid C4 syntax) and `flowchart.py` (Mermaid `flowchart`/`subgraph`, covers every view type) — both render from `graph/`, sharing `mermaid_common.py`; `json_export.py` (Structurizr JSON round-trip). |
| `src/c4studio/webapp/` | `server.py` (FastAPI), `loader.py` (load + live reload), `graph.py` / `model_graph.py` (React Flow reshape and full-model graph, both over `graph/view_graph`), `static/` (built SPA). |
| `src/c4studio/cli/main.py` | click CLI: `generate`, `render`, `export`, `check`, `list-views`, `webapp`. |
| `src/c4studio/render.py` | Headless SVG rendering: builds the same graph payload the web app serves and pipes it to the bundled Node renderer. The **only** thing in the project that needs Node at runtime. |
| `src/c4studio/renderer/diagram-render.mjs` | **Committed build artefact** — `diagram-core` bundled for Node, so the wheel can render without npm. Rebuilt by the root `npm run build`; never edit by hand. |
| `packages/diagram-core/` | The renderer-agnostic diagram layer: `layout.ts` (compound dagre, **async by contract** so the engine can be swapped), the React Flow node/edge components, `export.ts` (PNG/SVG) and `edgePaint.ts`. Knows nothing about the API or app state — that is what lets the headless renderer and the embedded surfaces reuse it. |
| `editors/vscode/` | VS Code extension (TypeScript, esbuild, packaged as `.vsix`). |
| `samples/` | Sample workspaces used for live verification. |

## Environment & Commands

- **Install deps:** `uv sync`
- **Run CLI:** `uv run c4 --help`
- **Render SVG:** `uv run c4 render <file> -o out/` (needs Node; set
  `C4STUDIO_NODE` if it is not on `PATH`)
- **Web app:** `uv run c4 webapp <dir-or-file>` (FastAPI + React SPA
  on `127.0.0.1:8090`; loads DSL/JSON from disk, live-reloads on edits).
- **Run tests:** `uv run pytest`
- **Lint/Format:** `uv run ruff check .` and `uv run ruff format .`
- **Type check:** `uv run mypy .`
- **Rebuild frontend:** `npm install && npm run build` **from the repo root** —
  it is a workspace, so `diagram-core` must be built before the SPA. The root
  `build` script does both in order.
- **Audit frontend deps:** `npm audit` at the repo root (kept at zero advisories)

### Node is not on PATH

`node`/`npm`/`npx` are **only** available in the conda env `pystructurizr`
(`/opt/miniconda3/envs/pystructurizr`) — an env name, deliberately not renamed
with the product. Any frontend or VS Code extension build
must go through it, e.g.:

```bash
conda run -n pystructurizr --no-capture-output npm install
conda run -n pystructurizr --no-capture-output npm run build
```

Plain `npm ...` will fail with "command not found". This applies to the
workspace (`packages/*`, `frontend/`) and `editors/vscode/` alike.

## Rules & Coding Conventions

- **Style:** PEP 8, `ruff` for all formatting — never hand-format.
- **Types:** Strict type hinting on every function signature; `mypy` must stay clean.
- **Docstrings:** Google-style for all public modules and functions.
- **Async:** Prefer `async/await` for I/O-bound work.
- **Imports:** Standard library, third-party, then local — separated by blank lines.
- **Tests:** Live in `tests/`, mirroring the source tree (`test_parser/`,
  `test_webapp/`, `test_generators/`). Use pytest fixtures for setup/teardown;
  shared DSL/JSON inputs go in `tests/fixtures/`.
- **Error handling:** Custom exception classes; never a bare `except:`.
- **Global state:** Avoid module-level mutable state; pass config objects.

## Constraints

- **No new dependencies** — Python or npm — without asking first. This is a hard
  rule and the reason several roadmap items are shaped the way they are (e.g.
  headless rendering must reuse existing layout code rather than pull in a
  renderer).
- **Unsupported DSL features fail soft.** `!script`, `!plugin`, `!components`,
  unknown `!directives` and unrecognised blocks are never executed — they are
  skipped whole and recorded as structured `Diagnostic`s in
  `Workspace.diagnostics` (and as strings in `Workspace.parse_warnings`, kept
  for existing callers), which the CLI prints to stderr. Keep that contract: a
  skipped construct must never consume its enclosing scope.
- **Layout sidecars** (`*.layout.json`) are per-user UI state, gitignored, and
  written next to the source file. Never commit one. Sections are top-level
  and additive — `views` (element positions/sizes), `edges` (waypoints),
  `labels` (dragged label offsets) — so a sidecar written by an older
  version still loads. Add new state as a new section, never by changing
  an existing one's shape.

## Verification

Tests alone are not sufficient for webapp or parser changes. Before opening a PR:

1. `uv run pytest`, `uv run ruff check .`, `uv run mypy .` — all green.
2. Live-check against `samples/` — `samples/hedge_fund/workspace.dsl` is the
   richest model (docs, ADRs, deployment, groups, themes);
   `internet_banking.dsl` and `saas_monitoring.dsl` cover the common cases.
3. For frontend changes, rebuild the bundle and commit it — a stale
   `src/c4studio/webapp/static/` ships a broken UI.

## Answering Structurizr parity questions

The upstream Java source is checked out beside this repo at
`../structurizr/`. **Check it before deciding any compatibility question** —
it settles in seconds what the roadmap docs and old tickets disagree about,
and those disagreements have sent work in the wrong direction more than once.

| Where | What it answers |
| --- | --- |
| `../structurizr/structurizr-dsl/src/main/java/com/structurizr/dsl/` | DSL syntax. Each parser declares a literal `GRAMMAR` string and index constants — e.g. `DeploymentNodeParser` has `"deploymentNode <name> [description] [technology] [tags] [instances] {"` with `TAGS_INDEX = 4`, `INSTANCES_INDEX = 5`. Definitive for positional argument order. |
| `../structurizr/structurizr-core/src/main/java/com/structurizr/model/` | Model field names, types and defaults — e.g. `DeploymentNode.instances` is `private String instances = "1"`. |
| `../structurizr/structurizr-application/` | The Java web UI, for behaviour comparisons (see `docs/structurizr-parity.md`). |

Worked example: PP-87 changed `instances` from `int` back to `str` because
range expressions like `"0..N"` were being discarded, and the upstream field
turned out to be exactly `String instances = "1"`. The same check disproved a
suspected positional-order bug in the same ticket.

Note this checkout is a convenience of *this machine*, not part of the repo,
so it may be absent elsewhere. Prefer it over memory when it is there; record
the finding in the code or docs so the answer survives without it.

## Git & Workflow

- **One Jira ticket per item** in the `PP` project (Jira access is via the
  `jira` skill; `JIRA_INSTANCE`, `JIRA_USER_EMAIL`, `JIRA_API_TOKEN` are in the
  environment). Reference the ticket in the commit subject: `... (PP-70)`.
- **Branch per ticket**, cut from `main`: `feature/<name>` or `fix/<name>`.
- **Semantic commits:** `feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, with an
  optional scope — `feat(parser): ...`, `feat(webapp): ...`.
- **PR-first merge — never merge a feature branch locally.** Push the branch,
  open a PR, merge the PR, and wait for the merge before starting the next
  ticket.
- **`gh` is not installed on this machine.** Create and merge PRs through the
  GitHub REST API (`https://api.github.com/repos/geoffkoh/c4studio/pulls`)
  with `curl`, not the `gh` CLI.

## Documentation Upkeep

- `docs/structurizr-parity.md` tracks c4studio against the Java Structurizr
  UI and is the closest thing to a status page — **update it as items land**.
- `docs/roadmap.md` holds the staged plan (phases 2–4) and delivery conventions.
- `docs/dsl-support.md` maps every keyword in the Structurizr DSL language
  reference to what this parser does with it, established by probing rather
  than by reading. Update it when parser coverage changes — and re-probe
  rather than assuming.
- `docs/data-models.md` documents the domain model; keep it honest when model
  fields change.
- `docs/MIGRATION.md` records breaking changes from the compatibility work.
- Whenever the workflow or stack changes, update this file, the agents in
  `.claude/agents/`, and the skills in `.claude/skills/` in the same change.

## Claude Configuration

Project-scoped agents live in `.claude/agents/`: `c4-architect` (C4 modeling and
tool-fit review), `python-pro` (typed async Python), `frontend-react` (the Vite +
React Flow SPA). Skills live in `.claude/skills/`: `run-webapp` (launch the
viewer on a sample) and `release` (cut a PyPI + `.vsix` release).
