# Where things stand, and what to pick up next

The working state of the repo between sessions. `roadmap.md` holds the
long-range plan and `studio-editor-plan.md` is the completed record of the
editor work; this file is the short horizon — what just landed, what is
open right now, and what to do next.

**Keep it current.** It is only worth reading if it is true, so update it
when you finish a run of work, not when you remember.

Last updated: **18 September 2026**, after the perspectives run
(PP-172 … PP-186) and the documentation prune.

---

## Current state

| | |
|---|---|
| PyPI | **0.3.0** — published 13 Sep 2026, tagged `v0.3.0`, verified by isolated install |
| VS Code extension | **0.3.1**, packaged as `.vsix` only. Not on the Marketplace, and versioned independently of the Python package |
| `main` | Green. Four CI jobs: Python gate, bundle + layout, VS Code extension packaging, and the `render` dogfood |
| Open PRs | **None** |
| Open `PP` tickets | **None** — PP-170 … PP-186 all closed |
| Frontend runtime | React **19**, TypeScript **7**, Vite **8**, marked **18**. `reactflow` stays on **11** — see below |

---

## Recent work

The last run only. Older entries are in the tickets and in git;
keeping them here turned this file into a changelog, which is not what
it is for — it is the thing you read *first*, so it has to stay short.

### The renderer honours your arrangement (17 September): PP-180, PP-181

`c4 render` called `react_flow_graph(workspace, view)` with no layout at
all, so a rendered SVG was a fresh auto-layout rather than the diagram
you arranged. The sidecar reading lived inside `webapp/server.py`, which
is why: it now lives in `c4studio/layout_sidecar.py` and both surfaces
read it through one implementation. `svg.ts` gained the two sections it
had never seen — dragged label offsets and dragged title/legend chrome,
the latter expanding the canvas so a dragged legend cannot be clipped.
`--no-layout` renders as if nothing had been arranged, which is what
keeps a committed diagram the same on any machine.

**PP-181, found on the way, is the bigger one.** Saved layouts were being
discarded on *any view containing a group* — in the Studio, not just in
`render`. Two causes, both needed fixing:

1. A synthetic group boundary is created after placement, so it got a
   stored size and no position; both renderers re-run auto-layout when
   any node lacks one.
2. `normalizeStoredPositions` gave up and re-laid-out as soon as one
   boundary sat inside another — which is every grouped container view.
   It now adapts absolute positions to nested nodes at any depth,
   innermost first.

Verified against the running API (positions survive a save/reload) and in
the browser (the diagram follows the stored layout instead of the
auto-layout). **Neither cause had a test**, which is how a bug this
visible survived: both fixes now have one.

**A Playwright trap, twice.** `scrollTo` in `e2e/highlight.spec.ts` only
scrolls down, and the editor keeps a scroll position across a file
switch, so a test that passed alone failed in the suite. Assigning
`scrollTop = 0` does not hold — CodeMirror restores its own scroll a
frame later. Pressing its `Mod-Home` binding and polling until the
scroller is actually at the top does.

### The VS Code preview became a picture (17 September): PP-170

Chosen over PP-171, which kept the SPA in the webview and taught it to
show less. Both were built to be compared; this one wins because it
removes the machinery rather than accommodating it — no server, no port,
no iframe for the common case — and because it carries its own escape
hatch: `Open in Studio (browser)` spawns `c4 webapp` and opens a tab,
which is a better home for a canvas with toolbars than a 400px panel.
`Show View…` switches views through a quick-pick fed by
`c4 list-views --json`, the same function behind `/api/views`, so the
picker cannot disagree with Studio about the default.

What it gives up: pan, zoom and drill-down in the panel, and a re-render
per change rather than a live canvas. PP-171 is closed as the road not
taken; its measurements are in the ticket.

Two things the branch found that are worth keeping in mind:

- **The CSP would have shipped broken.** `default-src 'none'` covers
  `img-src`, and the renderer inlines theme icons as `data:` URIs — so
  without `img-src data:` they vanish with no error, and only 2 of
  hedge_fund's 13 views have any. `e2e/svg-preview.spec.ts` renders a
  deployment view, asserts each image decodes, and asserts the failure
  case too.
- **Node is there even when it is not.** With neither `C4STUDIO_NODE` nor
  `node` on PATH, the extension host is itself Node — measured,
  `process.execPath` under `ELECTRON_RUN_AS_NODE` reports 24.18.1.

Rebased onto 19 commits of `main` with no conflicts, and it inherits
PP-180 for free: the preview runs plain `c4 render --view`, so the
picture follows the layout you arranged.

### A DSL reference that cannot drift (17 September): PP-184

`docs/dsl-reference.md` is the authoring reference — enough to write DSL
for c4studio without reading the code, written as much for an agent as a
person. `tests/test_docs_examples.py` parses every ```dsl block in it and
asserts no diagnostics, which caught three wrong examples while it was
being written. Add examples there rather than prose claims.

Probing for it turned up three things now recorded rather than assumed:
`healthCheck` is instance-only (as upstream), `!docs` in an element body
attaches to the workspace (PP-185), and **`parallel` in a dynamic view
consumes the rest of the view** (PP-186) — which breaks the contract this
file's own rules state, that a skipped construct never eats its enclosing
scope. `paperSize` is discarded with no diagnostic at all.

**`e2e/highlight.spec.ts` has now been flaky three separate times**, each
for a different reason in the same area: the editor keeps a scroll
position across a file switch; `scrollTop = 0` is undone a frame later by
CodeMirror's own restore; and a line found by scrolling can be scrolled
back out of the DOM before the assertion reads it — which counts as zero
tokens and reads exactly like the bug being tested for. It now presses
`Mod-Home`, tolerates a few pixels of padding, and **re-scrolls inside
the polling loop** so a count of zero means "not painted" rather than
"not on screen". If it goes red again, suspect the harness before the
vocabulary.

### First contact (18 September): PP-182

Two bugs that only showed before anyone touched the app, which is where
they cost most. `ViewInfo` never modelled the `default` flag — the server
has returned it and sorted by it since PP-119 — so the app opened on "No
view selected", and below 900px the sidebar starts collapsed, leaving
nothing visible to choose from. And the reload error rendered *inside*
that sidebar, so a failed reload left a stale diagram explaining nothing.
Errors now sit in a strip above the body.

Both fixes existed on the abandoned PP-171 branch and were nearly lost
with it; they had nothing to do with which preview design won. Worth
remembering when a branch is closed: check what it was carrying.

### Perspectives in the preview, and two parser fixes (18 September)

**PP-186** — `parallel` in a dynamic view consumed the rest of the view,
because the view body's fallback was a bare `advance()`. It now goes
through `_skip_unknown`, and `parallel` is implemented rather than
skipped: its steps share one number, as upstream numbers them. `paperSize`
is stored instead of silently discarded.

**PP-185** — `!docs` and `!adrs` were stripped before tokenising, so they
always attached to the workspace. The parser handles them now, which is
what makes scoping possible. The path still comes from the raw line: the
tokenizer drops `-` and `/`, so `!docs api-docs/sub` cannot be read back
from tokens at all — a token-level first attempt silently looked for a
directory called `api`.

**PP-183** — `c4 list-perspectives [--json]` feeds a `Show Perspective…`
quick-pick in the VS Code preview, which passes `--perspective` to the
render. Its own command rather than a field on `list-views --json`:
perspectives belong to the model, not to a view, and that JSON is an
array whose shape other tools already read.

---

## Open now

**Nothing.** No open PRs, no open `PP` tickets.

---

## Still needs a human

Neither of these can be closed by an agent, and both are easy to let slide
into "done" if nobody writes them down.

1. **The VS Code extension has never been installed and driven from a real
   VS Code.** PP-156 added Playwright over a copy of the webview shell —
   the iframe, the CSP, and panel width are covered. PP-163 made packaging
   an enforced CI step. Neither is the same as running it: the `vscode`
   host, dragging the panel, and the extension spawning the server are all
   unverified. Install the `.vsix` and use it.
2. **Diagrams and Source are still two pages.** The larger coherence win
   from the layout review, deliberately deferred to its own phase. See the
   "After F1" section of `studio-editor-plan.md`.

---

## Traps worth not rediscovering

Each of these cost time. The first few are from 13 September; the last
four are from the perspectives run, and their fuller context is in the
tickets they name.

- **A check that cannot fail looks exactly like a check that passed.**
  Three happened in one day: a mutation test whose mutation did not compile
  (so the bundle never rebuilt and the *old* one was tested); a
  cross-branch comparison script with the wrong function name and its
  errors going to `/dev/null`, which diffed two empty files and reported
  "identical"; and `uv build` using the locally-installed uv's bundled
  backend, so a PR widening the `uv_build` bound never exercised the new
  range. Make a check go red on purpose before trusting it green.
- **`astral-sh/setup-uv` has no rolling major tag.** It dropped them in v8,
  so `@v10` does not resolve — pin exactly (`v10.1.0`). The other four
  actions still publish `refs/tags/v7`. Verified, not assumed.
- **UP042 is a behaviour change wearing a modernisation costume.**
  Rewriting `(str, Enum)` as `StrEnum` changes `str()` and f-string output
  from `ViewType.SYSTEM_CONTEXT` to the bare value — which is what
  `c4 list-views` prints. JSON is identical either way, which is what would
  let it through review. Ignored in `pyproject.toml`, with the reasoning.
- **Check `../structurizr` before believing a ticket.** Two of the four
  parser tickets described the wrong bug, and one grep settled both.
- **"It builds" is not evidence for a framework bump.** React 19 compiled
  and type-checked cleanly against a React Flow version whose maintainers
  say does not support it. What settled it was driving the canvas and
  watching the console. Equally: when a probe turns up errors, run the same
  probe on the version you are moving *from* before blaming the bump —
  three 409s here were pre-existing.
- **CodeMirror only renders its viewport, and that bites three ways.** A
  token 100 lines down fails with `Received: 0`, indistinguishable from
  the bug being tested for; the editor keeps a scroll position across a
  file switch, so a search that only scrolls *down* never finds a line
  above it; and `scrollTop = 0` does not hold, because CodeMirror restores
  its own scroll a frame later. `e2e/highlight.spec.ts` went red three
  separate times on these. It now presses the editor's `Mod-Home` binding
  and **re-scrolls inside the polling loop**, so a count of zero means
  "not painted" rather than "not on screen" (PP-177).
- **The tokenizer drops `-` and `/`.** `!docs api-docs/sub` reaches the
  parser as three bare identifiers with nothing to say what separated
  them, so a path can never be rebuilt from tokens — read it from the raw
  line. A token-level first attempt silently looked for a directory
  called `api` (PP-185).
- **A skipped construct must not consume its enclosing scope**, and the
  parser broke its own rule: a bare `advance()` on an unknown *block* left
  its closing brace to end the enclosing view, dropping everything after
  it. Reach for `_skip_unknown`, which is brace-balanced (PP-186).
- **Deleting a merged branch closes the PR stacked on it.** GitHub does
  not retarget; it closes, and a closed PR cannot be reopened while its
  base branch is gone. Push the base branch back to reopen, repoint at
  `main`, *then* delete. Retarget the next PR in a stack **before**
  merging the one below it.
- **The `jira` skill is workspace-level**, so `/jira` fails from inside
  this repo. Call `jira_helper.py` directly — CLAUDE.md has the commands.
