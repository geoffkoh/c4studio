# CLAUDE.md: pystructurizr

> **Scope:** This file governs the pystructurizr repository and supersedes any
> workspace-level guidance describing other projects for all work under
> `pystructurizr/`. It is self-contained: every rule that applies here is
> stated here.

## Project Overview

pystructurizr is a Python implementation of [Structurizr](https://structurizr.com/):
it parses Structurizr DSL and workspace JSON into a typed domain model, generates
Mermaid C4 diagrams, and ships a local-first viewer — a FastAPI backend serving a
React SPA that renders views as interactive React Flow graphs. A VS Code extension
in `editors/vscode/` embeds that viewer as a diagram preview.

Published on PyPI as **`pystructurizr-studio`** (the name `pystructurizr` belongs
to an unrelated project); the import package and CLI are still `pystructurizr`.

**Local-first by design.** No multi-user server, no auth, no workspace locking or
branches. Sharing happens through git and generated artifacts. Do not propose
features that assume a hosted multi-user deployment.

## Tech Stack & Architecture

- **Language:** Python 3.13+, `uv` for dependency and env management.
- **Pattern:** Domain-driven design, test-driven development.
- **Frontend:** Vite + React + TypeScript SPA in `frontend/`, React Flow +
  dagre for graph layout. `npm run build` writes to
  `src/pystructurizr/webapp/static/` — a **committed** bundle, so the wheel
  ships a working UI and end users never need Node.

### Module map

| Path | Responsibility |
| --- | --- |
| `src/pystructurizr/models/` | The domain model: `workspace`, `elements`, `views`, `deployment`, `documentation`, `enums`. |
| `src/pystructurizr/parser/` | `dsl.py` (DSL parser), `json_parser.py`, `expressions.py` (include/exclude engine), `implied.py`, `docs.py`, `locations.py` (source spans for go-to-definition). |
| `src/pystructurizr/generators/` | `mermaid.py`, `json_export.py` (Structurizr JSON round-trip). |
| `src/pystructurizr/webapp/` | `server.py` (FastAPI), `loader.py` (load + live reload), `view_graph.py` / `graph.py` (view and full-model graph builders), `static/` (built SPA). |
| `src/pystructurizr/cli/main.py` | click CLI: `generate`, `export`, `list-views`, `webapp`. |
| `editors/vscode/` | VS Code extension (TypeScript, esbuild, packaged as `.vsix`). |
| `samples/` | Sample workspaces used for live verification. |

## Environment & Commands

- **Install deps:** `uv sync`
- **Run CLI:** `uv run pystructurizr --help`
- **Web app:** `uv run pystructurizr webapp <dir-or-file>` (FastAPI + React SPA
  on `127.0.0.1:8090`; loads DSL/JSON from disk, live-reloads on edits).
- **Run tests:** `uv run pytest`
- **Lint/Format:** `uv run ruff check .` and `uv run ruff format .`
- **Type check:** `uv run mypy .`
- **Rebuild frontend:** `cd frontend && npm install && npm run build`

### Node is not on PATH

`node`/`npm`/`npx` are **only** available in the conda env `pystructurizr`
(`/opt/miniconda3/envs/pystructurizr`). Any frontend or VS Code extension build
must go through it, e.g.:

```bash
conda run -n pystructurizr --no-capture-output npm --prefix frontend run build
```

Plain `npm ...` will fail with "command not found". This applies to
`frontend/` and `editors/vscode/` alike.

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
- **Unsupported DSL features fail soft.** `!script`, `!plugin`, `!components`
  and unknown `!directives` are never executed — they are skipped and recorded
  as an `UnsupportedFeatureWarning` in `Workspace.parse_warnings`, which the CLI
  prints to stderr. Keep that contract.
- **Layout sidecars** (`*.layout.json`) are per-user UI state, gitignored, and
  written next to the source file. Never commit one.

## Verification

Tests alone are not sufficient for webapp or parser changes. Before opening a PR:

1. `uv run pytest`, `uv run ruff check .`, `uv run mypy .` — all green.
2. Live-check against `samples/` — `samples/hedge_fund/workspace.dsl` is the
   richest model (docs, ADRs, deployment, groups, themes);
   `internet_banking.dsl` and `saas_monitoring.dsl` cover the common cases.
3. For frontend changes, rebuild the bundle and commit it — a stale
   `src/pystructurizr/webapp/static/` ships a broken UI.

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
  GitHub REST API (`https://api.github.com/repos/geoffkoh/pystructurizr/pulls`)
  with `curl`, not the `gh` CLI.

## Documentation Upkeep

- `docs/structurizr-parity.md` tracks pystructurizr against the Java Structurizr
  UI and is the closest thing to a status page — **update it as items land**.
- `docs/roadmap.md` holds the staged plan (phases 2–4) and delivery conventions.
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
