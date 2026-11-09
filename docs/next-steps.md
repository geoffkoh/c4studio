# Where things stand, and what to pick up next

The working state of the repo between sessions. `roadmap.md` holds the
long-range plan and `studio-editor-plan.md` is the completed record of the
editor work; this file is the short horizon — what just landed, what is
open right now, and what to do next.

**Keep it current.** It is only worth reading if it is true, so update it
when you finish a run of work, not when you remember.

Last updated: **9 November 2026**, after the 0.4.0 release (PP-216), the
project site (PP-217), handle-free exports (PP-219) and layouts from
workspace JSON (PP-220); before that **30 October 2026**, after the interface run
(PP-195 … PP-208, PP-206) and the October roadmap review: dynamic-view
step ids (PP-198), `routing Orthogonal` (PP-209), `workspace extends`
(PP-210), impact in the Studio (PP-193), the diff as a PR comment
(PP-194), a dependency security scan (PP-213), and the Source page
folded into Diagrams as an editor panel (PP-214).

---

## Current state

| | |
|---|---|
| PyPI | **0.4.0** — published 9 Nov 2026, tagged `v0.4.0` (PP-216). 0.3.0 was 13 Sep 2026 |
| VS Code extension | **0.3.1**, packaged as `.vsix` only. Not on the Marketplace, and versioned independently of the Python package |
| `main` | Green. Four CI jobs: Python gate, bundle + layout, VS Code extension packaging, and the `render` dogfood |
| Open PRs | **None** |
| Open `PP` tickets | PP-192 (drive the `.vsix` for a day — needs a human), PP-213 (npm half), PP-211 (parked) — see *Open now* |
| Site | **[geoffkoh.github.io/c4studio](https://geoffkoh.github.io/c4studio/)**, built by `website/build.py`, deployed by `pages.yml` on merge (PP-217) |
| Frontend runtime | React **19**, TypeScript **7**, Vite **8**, marked **18**. `reactflow` stays on **11** — see below |

---

## Recent work

The last run only. Older entries are in the tickets and in git;
keeping them here turned this file into a changelog, which is not what
it is for — it is the thing you read *first*, so it has to stay short.

### Layouts from workspace JSON (PP-220)

A `.json` that Structurizr laid out is drawn with its own layout in the
Studio, `c4 render` and `c4 publish`: element x/y, line vertices, and
Structurizr's 450×300 boxes (or a style's `width`/`height`). Before,
every JSON view was laid out from scratch: the parser kept only the
element ids, and nothing read a vertex. Two rules came from
`structurizr-diagram.js` and the upstream test data. A view with
`automaticLayout`, or with every element at 0,0, keeps no positions,
because the Java library writes 0,0 for views nobody arranged and taking
those literally stacks every box on one spot. Boundaries carry no
position, so both renderers now fit them around their children
(`needsAutoLayout` in `layout.ts`) instead of re-running auto-layout.
Checked against upstream's `spring-petclinic/workspace.json`.
Unreleased, with an entry in `MIGRATION.md`.

**Not done:** text stays c4studio-sized, so Structurizr's large boxes
read empty, because upstream's default font is 24px. Sizes from a remote
theme are not applied, since the parser never fetches. `c4 render` has
no way to pick a named layout yet; options A–D are in the PP-220
discussion.

### Image parity: `c4 render` against the Studio export

A side-by-side check on hedge_fund found these differences. The first
three have been fixed:

- The export drew connection handles as black dots (PP-219 and PP-221,
  fixed).
- `c4 render` drew two relationships between the same pair on one
  straight line (PP-222, fixed: both renderers now share
  `diagram-core/src/edgePath.ts`).
- `c4 render` drew straight lines whatever the Studio showed, and cut
  long labels to one line (PP-222, fixed). The toolbar's line style is
  now saved per view in the sidecar's `lineStyle` section, and the
  render default is Bezier, matching the Studio.
- Text in a box wraps narrower in `c4 render`.
- The export still carries the Studio's ⊕ drill mark, ＋ expand and
  − collapse controls.

### 0.4.0 on PyPI (PP-216)

Everything from PP-182 to PP-215: lint, diff, impact, publish, `workspace
extends`, text blocks, named layouts, re-routing, the editor panel and
the `anyio` advisory fix. `MIGRATION.md` has a 0.4.0 entry; nothing needs
action. The extension stays at 0.3.1. Verified by an isolated
`uvx --from c4studio==0.4.0` install, tagged `v0.4.0`.

### The project site (PP-217)

`website/` builds a GitHub Pages site: a landing page, guides, a *Beyond
Structurizr* page for the `c4studio.*` extensions and divergences, the
`docs/` reference pages, and a live example from `c4 publish` of
`samples/c4studio`. The point of its design is that it cannot drift. The
CLI reference is generated from click, the shortcuts come from
`shortcuts.ts`, code is painted with `highlight.ts`'s vocabulary, and
`tests/test_website.py` fails when a link or anchor breaks or when a
command, option, `c4studio.*` key or action input is undocumented. The
guide pages' DSL is parsed by `test_docs_examples.py`, and the Python API
examples run. Markdown goes through `c4studio.markdown`, so no
dependency was added. The screenshots in `website/assets/` were taken
from clean copies of the samples (no sidecars) and need retaking when
the Studio's look changes.

---

## Open now

- **PP-213, one advisory left:** `@azure/msal-node` (high, none
  critical) in `editors/vscode`, through `@vscode/vsce` →
  `@azure/identity`, which pins `^6` in every release; the fix is 7.1.0.
  Dev-only — `vsce publish` authenticates with it, `vsce package` does
  not. Wait for `@azure/identity` to move rather than force an
  `overrides` across a major. Everything else was fixed in PR #265.
- **PP-211 (parked):** the diagram diff's visual overlay, split from
  PP-194. Worth it once a team reviews diagrams in PRs.

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
2. **The merged Diagrams page (PP-214) wants a human eye.** The source
   editor is now a panel beside the diagram. The `ux-reviewer` left three
   questions only use can answer — two still open: whether the details card stacked over a
   ~480px diagram at 1280px reads as an inspector or as clutter, and how a
   ~330px editor feels at 1280 with the sidebar open. (The third, whether
   the right-edge rail would be found, was answered by use: it was not, and
   PP-215 added a Source button to the top bar.)
3. **Tell Google the site exists.** Add `geoffkoh.github.io/c4studio` to
   Google Search Console (ownership is verified by a file or meta tag, so
   only the owner can do it) and submit `sitemap.xml`. Without it, the
   site waits for a crawler to find a link to it.

---

## Traps worth not rediscovering

Each of these cost time. The first few are from 13 September, the next
from the perspectives run, and the e2e ones near the end from the October
interface run; fuller context is in the tickets they name.

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
- **e2e tests write to the developer's `samples/`.** The Playwright
  server serves `samples/`, so any test that drags, expands or saves
  rewrites a real sidecar. Answer layout, expansion and named-layout
  writes with `page.route` (see `rerouting.spec.ts` and
  `named-layouts.spec.ts`), and check `shasum samples/*.layout.json`
  before and after a run. A full-suite run used to rewrite
  `logistics_network.layout.json` with identical content. No single spec
  does it, and it is harmless, but it makes `git status` lie about who
  touched it. The reverse also bites: those sidecars are gitignored, so
  CI has none. A test that passes locally because a view has saved
  positions fails in CI, where the view auto-lays out (PP-197's load
  test did exactly that). To reproduce CI, move the sidecar aside for
  the run.
- **Wait for the view, not for *a* legend.** The default landscape view
  also has a legend, so an opener that waits for any legend races the
  view switch. Wait for the view's own title node:
  `.react-flow__node` with `hasText: /^Delivery Platform – Containers$/`.
- **Hover emphasis remounts the hovered edge.** It raises the edge into
  another layer, and React Flow remounts it. A drag whose window
  listeners were removed on unmount died after a few pixels. Listeners
  that must outlive a hover must not be torn down by the edge's unmount
  (PP-196).
- **The edge label layer sits above the edges**, so a label over a drag
  handle makes it ungrabbable. `handlePoint` moves the handle clear of
  the measured label. Tests pick a handle that `elementFromPoint`
  confirms is on top.
- **`highlight.spec.ts` "perspective vocabulary" fails locally**, on
  `main` too, and passes in CI. It is not caused by your change.
  Investigating it is still open.
- **The `jira` skill is workspace-level**, so `/jira` fails from inside
  this repo. Call `jira_helper.py` directly — CLAUDE.md has the commands.
- **Stock runners' Python is older than 3.13.** A bare `pipx install
  c4studio` in a workflow fails resolution. The README's CI snippets did
  exactly that until PP-217; set up Python first, as the action does.
- **A new `c4studio.*` key, CLI option or action input fails
  `tests/test_website.py`** until the site documents it. That is the
  design, not a flaky test: add it to the matching page in
  `website/content/`.
## Traps worth not rediscovering

Each of these cost time. The first few are from 13 September, the next
from the perspectives run, and the e2e ones near the end from the October
interface run; fuller context is in the tickets they name.

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
- **e2e tests write to the developer's `samples/`.** The Playwright
  server serves `samples/`, so any test that drags, expands or saves
  rewrites a real sidecar. Answer layout, expansion and named-layout
  writes with `page.route` (see `rerouting.spec.ts` and
  `named-layouts.spec.ts`), and check `shasum samples/*.layout.json`
  before and after a run. A full-suite run used to rewrite
  `logistics_network.layout.json` with identical content. No single spec
  does it, and it is harmless, but it makes `git status` lie about who
  touched it. The reverse also bites: those sidecars are gitignored, so
  CI has none. A test that passes locally because a view has saved
  positions fails in CI, where the view auto-lays out (PP-197's load
  test did exactly that). To reproduce CI, move the sidecar aside for
  the run.
- **Wait for the view, not for *a* legend.** The default landscape view
  also has a legend, so an opener that waits for any legend races the
  view switch. Wait for the view's own title node:
  `.react-flow__node` with `hasText: /^Delivery Platform – Containers$/`.
- **Hover emphasis remounts the hovered edge.** It raises the edge into
  another layer, and React Flow remounts it. A drag whose window
  listeners were removed on unmount died after a few pixels. Listeners
  that must outlive a hover must not be torn down by the edge's unmount
  (PP-196).
- **The edge label layer sits above the edges**, so a label over a drag
  handle makes it ungrabbable. `handlePoint` moves the handle clear of
  the measured label. Tests pick a handle that `elementFromPoint`
  confirms is on top.
- **`highlight.spec.ts` "perspective vocabulary" fails locally**, on
  `main` too, and passes in CI. It is not caused by your change.
  Investigating it is still open.
- **The `jira` skill is workspace-level**, so `/jira` fails from inside
  this repo. Call `jira_helper.py` directly — CLAUDE.md has the commands.
- **Stock runners' Python is older than 3.13.** A bare `pipx install
  c4studio` in a workflow fails resolution. The README's CI snippets did
  exactly that until PP-217; set up Python first, as the action does.
- **A new `c4studio.*` key, CLI option or action input fails
  `tests/test_website.py`** until the site documents it. That is the
  design, not a flaky test: add it to the matching page in
  `website/content/`.
