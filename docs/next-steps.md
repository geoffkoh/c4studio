# Where things stand, and what to pick up next

The working state of the repo between sessions. `roadmap.md` holds the
long-range plan and `studio-editor-plan.md` is the completed record of the
editor work; this file is the short horizon — what just landed, what is
open right now, and what to do next.

**Keep it current.** It is only worth reading if it is true, so update it
when you finish a run of work, not when you remember.

Last updated: **18 November 2026**, after control-free exports (PP-227),
Structurizr's text size in JSON layouts (PP-228), a key to merged lines
(PP-229) and the picomatch advisory on PP-213; before that **9 November 2026**,
after the 0.4.0 release (PP-216), the project site (PP-217), handle-free
exports (PP-219) and layouts from workspace JSON (PP-220); before that **30 October 2026**, after the interface run
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
| Open `PP` tickets | PP-192 (drive the `.vsix` for a day — needs a human), PP-213 (picomatch, no fix published), PP-211 (parked) — see *Open now* |
| Site | **[geoffkoh.github.io/c4studio](https://geoffkoh.github.io/c4studio/)**, built by `website/build.py`, deployed by `pages.yml` on merge (PP-217) |
| Frontend runtime | React **19**, TypeScript **7**, Vite **8**, marked **18**. `reactflow` stays on **11** — see below |

---

## Recent work

The last run only. Older entries are in the tickets and in git;
keeping them here turned this file into a changelog, which is not what
it is for — it is the thing you read *first*, so it has to stay short.

### Icons and the workspace logo (PP-231 … PP-237, PP-242, PP-234)

The details card now edits an element's look as **text edits** to the
`styles` rules (`style_edit.py`, `POST /api/style`, saved through
`PUT /api/source`): colours (PP-231) and the icon (PP-233), picked from
`icons/` beside the workspace (`icon_library.py`). A style's `icon` may
be a file path, resolved against the file the style is in and embedded
as a `data:` URI at parse time, as upstream does (PP-232).

- **Workspace logo (PP-237):** an `element "Workspace:Icon" { icon … }`
  style, upstream's 2026 replacement for `branding { logo }`. Drawn 28 px
  tall before every diagram title (both renderers share
  `diagram-core/logo.ts`), in the top bar and on the published site.
  `icons.image_size` reads PNG/GIF/JPEG/SVG headers because the headless
  renderer has no DOM to measure a wordmark.
- **Icon tint (PP-234):** `"c4studio.iconTint" "true"|"#hex"|"false"`
  draws a one-colour glyph in the text colour. CSS `mask` in the Studio
  (html-to-image copies it into exports), an SVG 1.1 flood filter in
  `svg.ts`. Opt-in because vendors' icons are multi-colour.
  `samples/icons/outline/` holds one-colour glyphs drawn for the repo.
- **Title click (PP-242):** React Flow's default `nodeDragThreshold` of 0
  made a click on the title a zero-length drag, which pinned it in the
  sidecar and cleared the selection. Now 3 px.

**Licensing, settled 20 Nov:** AWS, Azure and Google Cloud icons may be
used in diagrams but **not bundled**: their terms grant diagram and
documentation use, not redistribution. Tabler (MIT) can ship; Simple
Icons is CC0 artwork of other companies' trademarks, so only a curated,
checked subset with its disclaimer.

---

## Open now

- **The icon queue, in order:** PP-238 (logo selector), PP-239 (bundle
  Tabler), PP-240 (curated Simple Icons), PP-241 (`c4 icons import` for a
  downloaded cloud pack), PP-236 (remove `branding`), PP-235
  (`iconPosition`). PP-238's design was reviewed by ux-reviewer on
  20 Nov and revised: the empty-selection card's Workspace row is the
  way in (plus a click on an existing title logo, `nodrag`), a ranked
  list of *suggested* workspace images rather than a grid of every
  image (it counted 7,624 under `../structurizr`), its own preview
  strip, no bundled packs, and a one-line confirmation before "Choose a
  file…" copies into `brand/`. Match an upload to an existing file by
  hash first; the browser does not reveal a picked file's path.
- **PP-220 leftovers (parked 18 Nov):** sizes from a remote theme are
  not applied, and `c4 render` cannot pick a named layout.
- **PP-213, waiting on picomatch:** the `@azure/msal-node` advisory
  this was held open for cleared with PP-226. A new one has landed
  since: GHSA-fc5q-39xc-vjpf, a high ReDoS in `picomatch`, reported
  against **every** version, so there is nothing to upgrade to yet. It
  reaches the root install through `vite` → `tinyglobby`/`fdir` (5
  findings) and `editors/vscode` (4). Build tooling only; nothing
  ships it. `npm audit fix --force` offers to *downgrade* `vite` to
  6.2.7, which is not a fix. Bump once picomatch publishes one.
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
- **`export-edge-handles.spec.ts` "a bend point's handle" is flaky**,
  on `main` too: 5 of 20 repeats failed locally on 18 Nov, with the
  export holding no waypoint (`Received: 0`) although the canvas had
  one. Not yet investigated. Its sibling "a Step line's end and run
  handles" fails the same way now and then.
- **`line-style.spec.ts` "a view's saved style outranks this browser's
  default" is flaky**, on a clean `main` too: 2 of 3 repeats failed
  locally on 19 Nov (`Expected: > 0, Received: 0`).
- **A style rule in a fragment included *inside* `styles { }` is invisible
  to the card.** `style_locations` and `style_edit._rules` only look inside a
  `styles` block in the same file, so a fragment holding bare
  `element "X" { … }` rules is never found: the jump-to-style link misses it,
  and an edit adds a new rule in the root file (which then wins) instead of
  editing the fragment. A fragment with its own `styles { }` works. Found
  writing PP-233's tests; not yet ticketed.
- **`style-sources.spec.ts` "a style chip opens the editor…" failed once**
  in a full local run on 20 Nov and passed 16 of 16 repeats on its own.
- **`route-steps.spec.ts` "right-click offers Add step here" is flaky in
  CI**: it failed once on PR #290 ("no uncovered horizontal handle") and
  passed on re-run and locally. Like `merged-notes` before PP-229's fix,
  it samples for an uncovered point; pick the target by a stable handle
  instead of geometry if it recurs.
- **Your own sample sidecars break Studio tests.** The suite runs over
  `samples/`, so a group you collapsed in `logistics_network.layout.json`
  hides boxes the tests click, and about 15 specs time out. Move the
  sidecar aside for the run and put it back (check `shasum` before and
  after) rather than reading those failures as a regression.
- **The `jira` skill is workspace-level**, so `/jira` fails from inside
  this repo. Call `jira_helper.py` directly — CLAUDE.md has the commands.
- **Stock runners' Python is older than 3.13.** A bare `pipx install
  c4studio` in a workflow fails resolution. The README's CI snippets did
  exactly that until PP-217; set up Python first, as the action does.
- **A new `c4studio.*` key, CLI option or action input fails
  `tests/test_website.py`** until the site documents it. That is the
  design, not a flaky test: add it to the matching page in
  `website/content/`.
