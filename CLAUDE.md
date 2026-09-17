# CLAUDE.md: c4studio

> **Scope:** This file governs the c4studio repository and supersedes any
> workspace-level guidance describing other projects for all work under
> `c4studio/`. It is self-contained: every rule that applies here is stated
> here.

## Project Overview

c4studio is a Python implementation of [Structurizr](https://structurizr.com/):
it parses Structurizr DSL and workspace JSON into a typed domain model, generates
Mermaid C4 diagrams, and ships a local-first **Studio** — a FastAPI backend
serving a React SPA that renders views as interactive React Flow graphs *and*
edits the DSL that produces them (CodeMirror 6, autocomplete, live diagnostics,
save-to-disk with conflict detection). A VS Code extension in `editors/vscode/`
embeds it as a diagram preview.

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
  it. React Flow + dagre for graph layout; CodeMirror 6 for the DSL editor,
  which is a `frontend/` dependency **only** — `diagram-core` is bundled into
  the headless Node renderer and must never need a DOM. `npm run build` writes to
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
| `src/c4studio/cli/main.py` | click CLI: `generate`, `render`, `export`, `check`, `list-views`, `webapp`, `new`. |
| `src/c4studio/templates.py` + `templates/*.dsl` | Starter workspaces, shipped as package data. **Valid DSL exactly as they sit on disk** — naming is a literal replacement of `"My Workspace"`, not a template language, so the suite parses each one directly. |
| `src/c4studio/webapp/assistant.py` | The assistant. Opt-in, lazily imports the optional `anthropic` extra, reads the key at the moment of use, returns text and executes nothing. |
| `src/c4studio/render.py` | Headless SVG rendering: builds the same graph payload the web app serves and pipes it to the bundled Node renderer. The **only** thing in the project that needs Node at runtime. |
| `src/c4studio/renderer/diagram-render.mjs` | **Committed build artefact** — `diagram-core` bundled for Node, so the wheel can render without npm. Rebuilt by the root `npm run build`; never edit by hand. |
| `packages/diagram-core/` | The renderer-agnostic diagram layer: `layout.ts` (compound dagre, **async by contract** so the engine can be swapped), the React Flow node/edge components, `export.ts` (PNG/SVG) and `edgePaint.ts`. Knows nothing about the API or app state — that is what lets the headless renderer and the embedded surfaces reuse it. |
| `frontend/src/` | The SPA. Beyond the panes: `dslLanguage.ts` (CodeMirror `StreamLanguage`), `dslComplete.ts` (completion), `highlight.ts` (**the one copy of the DSL vocabulary** — build from it, never restate it), `fileTree.ts` and `lineDiff.ts` (pure, so they can be exercised headlessly). |
| `editors/vscode/` | VS Code extension (TypeScript, esbuild, packaged as `.vsix`). The preview renders **one view as an SVG** via `c4 render --view` (PP-170) — no server, no port, no iframe — with `Show View…` to switch and `Open in Studio (browser)` for the full app, which is the only command that spawns `c4 webapp`. The webview CSP is `default-src 'none'` plus `img-src data:`, and dropping that `img-src` makes theme icons vanish silently; `e2e/svg-preview.spec.ts` pins it. |
| `samples/` | Sample workspaces used for live verification. |

## Environment & Commands

- **Install deps:** `uv sync --extra dev` — **not** a bare `uv sync`, which
  leaves out `anthropic` and so fails three assistant tests. The extras are
  `[project.optional-dependencies]`, which uv does not install by default.
- **Run CLI:** `uv run c4 --help`
- **New workspace:** `uv run c4 new <file> --template minimal|system-context|full-c4|deployment`
- **Render SVG:** `uv run c4 render <file> -o out/` (needs Node; set
  `C4STUDIO_NODE` if it is not on `PATH`)
- **Web app:** `uv run c4 webapp <dir-or-file>` (FastAPI + React SPA
  on `127.0.0.1:8090`; loads DSL/JSON from disk, live-reloads on edits).
  Serves the full **Studio** by default; `--viewer` serves **Viewer**,
  where routes that write DSL refuse with 403. Viewer still saves layout
  and expansion state — you cannot change the model, but you can arrange
  the view, and that arrangement is gitignored per-user UI state either
  way. Capability lives on the server (`GET /api/capabilities`), not in
  hidden buttons, so the guarantee holds against a crafted request.
- **Assistant:** `uv run c4 webapp <path> --assistant` — **off by default**,
  the only feature that leaves the machine. Needs `ANTHROPIC_API_KEY` in the
  environment and the optional extra (`uv sync --extra assistant`, or
  `pip install 'c4studio[assistant]'`). Sends the whole workspace source; the
  UI states which files. Never test it against the real API without asking —
  that spends the user's money.
- **Run tests:** `uv run pytest`
- **Lint/Format:** `uv run ruff check .` and `uv run ruff format .`
- **Type check:** `uv run mypy .`
- **Visual tests:** `npm run test:visual` from the repo root — Playwright
  over the real backend and the committed bundle. It asserts what `tsc`
  cannot see: that a pane has height, that chrome is not most of the
  window, that a breakpoint fires where the arithmetic said. **Rebuild the
  bundle first** or you are testing the previous one.
  `npm run test:visual:update` rewrites the screenshot baselines — only
  when a layout change is intended, and look at the diff before accepting.
- **Rebuild frontend:** `npm install && npm run build` **from the repo root** —
  it is a workspace, so `diagram-core` must be built before the SPA. The root
  `build` script does both in order.
- **Audit frontend deps:** `npm audit` at the repo root **and**
  `npm --prefix editors/vscode audit` — two separate installs, two separate
  lockfiles. Both are kept at zero advisories. The root audit alone missed
  eight advisories in the extension, which is what Dependabot surfaced when
  it was switched on; its `.github/dependabot.yml` covers both directories
  for the same reason. Note `npm audit` and Dependabot do not always agree:
  the root `nanoid` advisory was reported by npm and not by Dependabot.

### Dependabot cannot merge a frontend bump on its own

**Every** npm PR Dependabot opens is unmergeable as it arrives, and this is
structural rather than a mishap. `src/c4studio/webapp/static/` and
`src/c4studio/renderer/diagram-render.mjs` are committed build artefacts,
CI fails any PR whose committed bundle does not match its source, and
Dependabot does not run `npm run build`. A bundler bump changes the bundle
by definition. PR #118 sat open for two weeks before anyone noticed why.

Take the PR over rather than trying to fix it in place (PP-159 weighed the
alternatives; this one keeps Dependabot's signal that a dependency is
behind, at the cost of a manual step):

```bash
git checkout -b chore/frontend-deps-<month>
# apply the same version bumps to package.json by hand
conda run -n pystructurizr --no-capture-output npm install
conda run -n pystructurizr --no-capture-output npm --prefix editors/vscode install
conda run -n pystructurizr --no-capture-output npm run build   # the part Dependabot cannot do
```

Then close the Dependabot PR pointing at yours. A bundler swap is exactly
where a green build and a broken app diverge, so verify beyond "it built":
`npm run test:visual` including the screenshot baselines, and `c4 render`
over a sample for the Node renderer artefact, which nothing else exercises.

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
  renderer; the file tree's virtualisation and the assistant's diff are both
  hand-written for this reason). The one dependency added since is `anthropic`,
  as an **optional extra**, agreed explicitly before it went in.
- **Unsupported DSL features fail soft.** `!script`, `!plugin`, `!components`,
  unknown `!directives` and unrecognised blocks are never executed — they are
  skipped whole and recorded as structured `Diagnostic`s in
  `Workspace.diagnostics` (and as strings in `Workspace.parse_warnings`, kept
  for existing callers), which the CLI prints to stderr. Keep that contract: a
  skipped construct must never consume its enclosing scope.
- **Layout sidecars** (`*.layout.json`) are per-user UI state, gitignored, and
  written next to the source file. Never commit one. Sections are top-level
  and additive — `views` (element positions/sizes), `edges` (waypoints),
  `labels` (dragged label offsets), `expanded` (elements expanded in place),
  `collapsed` (collapsed group nodes) and `chrome` (dragged title/legend
  positions) — so a sidecar written by an older version still loads. Add
  new state as a new section, never by changing an existing one's shape.

## Verification

CI runs the standing gate on every PR (`.github/workflows/checks.yml`):
ruff, mypy, pytest, a rebuild of the frontend that **fails if the committed
bundle is stale**, the Playwright layout assertions, and `vsce package` for
the extension. Screenshot comparison is deliberately local-only — the
baselines are `-darwin` and a Linux set would be churn for no extra signal.

The extension job exists because `editors/vscode` is a separate install
that the frontend job never touches, so nothing built it. A dependency bump
raised `@types/vscode` above `engines.vscode`; `typecheck` and `esbuild`
both passed, `vsce package` rejects it outright, and the break surfaced
only when a release tried to cut a `.vsix` by hand (PP-163).

Tests alone are not sufficient for webapp or parser changes. Before opening a PR:

1. `uv run pytest`, `uv run ruff check .`, `uv run mypy .` — all green.
2. Live-check against `samples/` — `samples/hedge_fund/workspace.dsl` is the
   richest model (docs, ADRs, deployment, groups, themes);
   `internet_banking.dsl` and `saas_monitoring.dsl` cover the common cases;
   `logistics_network.dsl` exercises the wide end of the DSL (groups, bulk
   `!…` directives, deployment groups, health checks, animation, branding)
   and is pinned keyword-by-keyword in `tests/test_samples/`.
   `c4studio/workspace.dsl` models this codebase itself, down to component
   level — the fastest way to check a change against a model you can verify
   by reading the source next to it, and the only sample with component
   views for more than one container.
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

- **One Jira ticket per item** in the `PP` project. Reference the ticket in
  the commit subject: `... (PP-70)`.

  Jira lives in the **workspace-level** skill `../.claude/skills/jira/`, which
  is shared with `bizkit/`. Being workspace-level, it is *not* discoverable as
  `/jira` while working inside this repo — invoking it by name fails with
  "Unknown skill". Call the helper directly instead:

  ```bash
  cd ../.claude/skills/jira
  python3 jira_helper.py query "project = PP AND status != Done"
  python3 jira_helper.py create PP Task "Summary" --description "..."
  python3 jira_helper.py comment PP-157 "Merged in PR #169."
  python3 jira_helper.py transition PP-157 Done
  ```

  `JIRA_INSTANCE`, `JIRA_USER_EMAIL` and `JIRA_API_TOKEN` are in the
  environment. `JIRA_INSTANCE` is a bare host, not a URL.
- **Branch per ticket**, cut from `main`: `feature/<name>` or `fix/<name>`.
- **Semantic commits:** `feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, with an
  optional scope — `feat(parser): ...`, `feat(webapp): ...`.
- **PR-first merge — never merge a feature branch locally.** Push the branch,
  open a PR, merge the PR, and wait for the merge before starting the next
  ticket.
- **Use `gh` for pull requests** — `gh pr create --body-file …`,
  `gh pr checks`, `gh pr merge --merge --delete-branch`. Check
  `gh auth status` first; if it reports logged out, **ask** rather than
  reaching for the REST API. Hitting `api.github.com` with `curl` does not
  work here: there is no `GITHUB_TOKEN` in the environment, and reading the
  token back out of the osxkeychain helper to build an `Authorization`
  header is refused as credential materialization. A successful `git push`
  proves nothing — git gets the credential through the helper, which a
  `curl` call cannot.

## Documentation Upkeep

- `docs/next-steps.md` is the **short horizon: read it first when picking
  up work.** What just landed, what is open right now, what to do next,
  what needs a human, and the traps that cost time last session. Update it
  at the end of a run of work — it is only worth reading if it is true.
- `docs/structurizr-parity.md` tracks c4studio against the Java Structurizr
  UI and is the closest thing to a status page — **update it as items land**.
- `docs/roadmap.md` holds the staged plan (phases 2–4) and delivery conventions.
- `docs/studio-editor-plan.md` is the **completed** plan for in-app DSL
  editing (PP-119 … PP-142, shipped in 0.3.0). No longer a to-do list: it
  is the record of the decisions, the measurements behind them, and the
  three places the plan itself turned out to be wrong. Read it before
  changing the editor, the file tree, the caches or the assistant.
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
React Flow SPA), `ux-reviewer` (information architecture and screen real estate —
**read-only**, so the agent that judges a layout is not the one that wrote it). Skills live in `.claude/skills/`: `run-webapp` (launch the
viewer on a sample) and `release` (cut a PyPI + `.vsix` release).
