---
name: run-webapp
description: Launch the pystructurizr viewer (FastAPI + React SPA) against a sample workspace and exercise it over the API, for manual checks or live verification of a change. Use when the user wants to run, demo, screenshot, or verify the web app.
disable-model-invocation: false
argument-hint: "[sample-name] [--port N] [--rebuild-frontend]"
---

# Run the pystructurizr Viewer

Live verification against `samples/` is required before opening a PR for any
webapp or parser change — tests alone do not catch rendering regressions.

## 1. Pick a sample

| Sample | Why you'd use it |
| --- | --- |
| `samples/hedge_fund/workspace.dsl` | Richest model: `!include` fragments, docs + ADRs, deployment environments, groups, themes. **Default choice.** |
| `samples/internet_banking.dsl` | Classic C4 example, has a committed layout sidecar. |
| `samples/saas_monitoring.dsl` | Mid-size model with styles. |
| `samples/ecommerce_platform.dsl` | Plain, no frills — good for isolating a parser bug. |

Point the app at the `samples/` directory instead of a file to get the file
picker and switch between workspaces in the UI.

## 2. Rebuild the frontend first — only if you changed it

`src/pystructurizr/webapp/static/` is a committed build artifact. Python-only
changes do not need a rebuild. If you touched `frontend/`:

```bash
# node/npm exist ONLY in the conda env "pystructurizr" — plain npm will not resolve
conda run -n pystructurizr --no-capture-output npm install
conda run -n pystructurizr --no-capture-output npm run build
```

The build writes into `src/pystructurizr/webapp/static/` — commit that output
with the change.

## 3. Launch

```bash
uv sync
uv run pystructurizr webapp samples/ --port 8090 --no-browser
```

Run it in the background so you can drive the API in the same session, and use a
non-default port if 8090 might already be occupied. `--no-browser` keeps it from
stealing focus. The server live-reloads when the DSL, its `!include` fragments,
or the docs change on disk; a parse error keeps the last good workspace and
surfaces the error rather than blanking the UI.

## 4. Exercise it over the API

```bash
BASE=http://127.0.0.1:8090

curl -s "$BASE/api/files"                      # workspaces discoverable under the served path
curl -s -X POST "$BASE/api/load" -H 'Content-Type: application/json' \
     -d '{"path":"hedge_fund/workspace.dsl"}'  # load one
curl -s "$BASE/api/status"                     # loaded workspace + parse warnings
curl -s "$BASE/api/views"                      # view index (flags the default view)
curl -s "$BASE/api/views/<key>/graph"          # nodes/edges/rankDirection for a view
curl -s "$BASE/api/source"                     # DSL source for the Source pane
```

Check the response shape rather than just the status code — a 200 with zero
nodes is the failure mode that matters. Parse warnings in `/api/status` are the
fastest signal that a DSL feature silently degraded.

## 5. Verify in the browser

For anything visual, open the app and look. Worth confirming: the default view
opens first, boundaries nest correctly, drag persists to a `<source>.layout.json`
sidecar and Reset returns to auto-layout, double-click drills in and the
breadcrumb drills out, and PNG/SVG export produces a cropped diagram.

## 6. Clean up

Kill the server when done, and **do not commit any `*.layout.json`** the session
produced — sidecars are per-user UI state and are gitignored.
