# Where things stand, and what to pick up next

The working state of the repo between sessions. `roadmap.md` holds the
long-range plan and `studio-editor-plan.md` is the completed record of the
editor work; this file is the short horizon — what just landed, what is
open right now, and what to do next.

**Keep it current.** It is only worth reading if it is true, so update it
when you finish a run of work, not when you remember.

Last updated: **14 September 2026**, after clearing the Dependabot majors.

---

## Current state

| | |
|---|---|
| PyPI | **0.3.0** — published 13 Sep 2026, tagged `v0.3.0`, verified by isolated install |
| VS Code extension | **0.3.1**, packaged as `.vsix` only. Not on the Marketplace, and versioned independently of the Python package |
| `main` | Green. Four CI jobs: Python gate, bundle + layout, VS Code extension packaging, and the `render` dogfood |
| Open PRs | **None** |
| Open `PP` tickets | **None** |
| Frontend runtime | React **19**, TypeScript **7**, Vite **8**, marked **18**. `reactflow` stays on **11** — see below |

---

## What landed on 13 September

Twenty-three PRs. Grouped by what they were actually about, because the
ticket numbers do not group themselves.

### The lint contract (PP-157, PP-158)

ruff's rule selection was never written down, so it came from ruff's
defaults — which meant the **version was the contract**. 0.15's default is
`E4, E7, E9, F`; 0.16's is a far broader curated set, and the same tree
went from 0 findings to 116 without a line changing. Dependabot proposed
that as a routine patch bump (#167) and the whole group failed.

`[tool.ruff.lint] select` now states the rules outright, and PP-158 worked
through the 116 on merit. **The reasoning for every declined family is in
`pyproject.toml`** — read it there before re-litigating; it has the counts.

### Four parser tickets, two of which described the wrong bug (PP-103…PP-105, PP-110)

- **PP-103** said `!relationship <alias>` was a silent no-op. It was not.
  It applies `tags`, `url`, `properties` and `perspectives` — the whole
  vocabulary a relationship block has, here *and* upstream, because it is a
  `ModelItemDslContext`. The report was written against a `technology`
  line, which is not valid there in either implementation. The real defect
  was the silence, now two diagnostics.
- **PP-104** wildcard `!relationships` had **three separate causes**, not
  one. Fixed, including half-wildcards nobody asked for, plus the same bug
  one statement away in view `exclude "a->b"`.
- **PP-105** said workspace `properties` were stored nowhere. They were
  stored on the *views configuration*, under a comment asserting that is
  what structurizr-java does. It is not — and `views { properties … }`,
  which genuinely belongs there, was skipped entirely. The two were the
  wrong way round, and a test had pinned the bug rather than the behaviour.
- **PP-110** was already fixed under PP-112. Closed as a duplicate.

### Dependency and CI debt (PP-159 … PP-163)

Five stale Dependabot PRs, open up to two weeks, all resolved. Three of
them were hiding real problems rather than being routine:

- **click 8.5** deprecates `get_text_stream` for removal in 9.0 (PP-160).
  Replaced — and deliberately *not* with `sys.stdin.read()`, which decodes
  by locale while every DSL file is read as UTF-8.
- **Frontend Dependabot PRs are structurally unmergeable** (PP-159). See
  CLAUDE.md, "Dependabot cannot merge a frontend bump on its own".
- **`vsce package` broke** (PP-163) because `@types/vscode` was bumped
  above `engines.vscode`, and **nothing in CI built the extension**. There
  is a job for it now.

### After 0.3.0 (14 September)

**PP-164 — the editor did not highlight `#` comments.** The CodeMirror
tokenizer had no `#` rule at all: `highlight.ts` matched only `//` for
comments and `/^#[0-9A-Fa-f]{3,8}/` for colours, so a `#` was recognised
solely as a hex colour. Worse than the missing colour, words *inside* the
comment were still classified — `# description of the container` painted
`container` as a keyword.

The parser had been right since PP-112. Only the editor was out of step,
which is why files parsed cleanly and merely looked wrong. **That gap is
the thing to watch for**: `dsl.py` and `frontend/src/highlight.ts` are two
implementations of one language, and nothing forces them to agree. Any
future change to comment, string or colour rules needs both.

The fix needed a guard, not just a pattern — mid-line a `#` is a colour, so
an unguarded rule swallows the rest of every `background #08427b` line.

### Perspectives (15 September): PP-172, PP-173

**PP-172: the parser misread the block form.** Upstream accepts
`perspective <name> { description … value … url … }` as well as the
one-line form. c4studio read the block as perspectives named `description`,
`value` and `url`, with no warning. The block form needs the `perspective`
keyword: a bare `Name { … }` is invalid upstream too. A
first answer given in-session said otherwise, and reading
`StructurizrDslParser` settled it.

**PP-173: static perspective overlay.** A picker in the diagram toolbar,
shown only when the model has perspectives. Upstream's "static vs
dynamic" split is about where the **value** comes from, not the view
type: a perspective with a `url` is polled for a live value, and that
part is not built. Style resolution happens in `graph/view_graph.py`, so
the SPA only paints what the server sends. The live view's legend still
shows the unperspectived colours while a perspective is active.

### Relationship rows in the legend (16 September): PP-174

The legend was built from element styles only, so a tagged and styled
relationship was painted and never explained. Upstream's diagram key has
always had these rows. **No DSL change** — `relationship "<tag>" { … }`
was already parsed and painted; only the row was missing.

Two things worth knowing if you touch this again:

- **Swatch dashes are drawn at swatch scale, not the edge's.** The real
  ratios are width-scaled (`10 6` at width 2), which fits a single dash in
  an 18px line and reads as *solid* — so the default dashed relationship
  looked identical to a solid one in the first cut. Caught by looking at
  the rendered SVG, not by any test.
- **An element row is still labelled by the last matching tag**, while the
  new relationship rows join every matched tag as upstream does. That
  inconsistency is deliberate: element labels are pinned by
  `tests/test_samples/test_delta_release.py` and changing them would churn
  every committed diagram.

Legend entries now carry `kind` (`"element"` / `"relationship"`), which
changed the shape pinned by `tests/test_legend.py` and
`tests/test_generators/test_outline_styles.py`.

### Legend captions and style properties (16 September): PP-175

Two things in one change, the first a parity fix that stood on its own:
`properties { … }` inside a style block is valid upstream DSL
(`StructurizrDslParser.java:675-679`) and c4studio dropped it silently,
losing it from JSON round-trips too. `ElementStyle` and
`RelationshipStyle` now carry it.

On top of that, `c4studio.legend` on a style names that style's legend
row — the way to get wording into a legend that a tag name cannot carry,
without leaving Structurizr's grammar. **The namespaced-property escape
hatch is the pattern to reach for** whenever c4studio needs to express
something the DSL has no keyword for: upstream ignores the key, the file
still parses everywhere, and `c4studio.autolayout` was already doing this.

Captions are prose, so legend rows now wrap to a second line (all rows, to
keep the grid aligned) and `.legend__label` lost its `nowrap`.

### The legend under a perspective (17 September): PP-176

The overlay repaints the diagram but the legend kept explaining element
styles, so it named colours the diagram was no longer using. Its rows are
now rebuilt from what is on screen: one per distinct perspective value,
plus a `Not in <name>` row for what faded. `frontend/src/perspectiveLegend.ts`
holds the rule, pure and apart from the pane.

A value that no `Perspective:` style painted gets a neutral swatch —
those items keep their own colours, so no single colour would be telling
the truth, and the row says *which items carry the value* instead.

First e2e coverage of the overlay is in `e2e/perspectives.spec.ts`, and
the legend assertion was **checked red** against the previous bundle
before being trusted green.

### Editor vocabulary for perspectives (17 September): PP-177

`highlight.ts` is the SPA's only copy of the DSL vocabulary, and it
carried neither `perspectives` nor `perspective` — nor, it turned out,
`description`, `technology`, `tags`, `url`, `value`, `properties` or
`metadata`. A perspective block would have lit half way even after adding
just its own two words, so the model-item body properties went in with
them. Completion comes free: `dslComplete.ts` builds its list from these
same sets.

**The e2e spec ordering trap.** The new highlighting test passed alone and
failed in the full run: switching files swaps the buffer under the same
CodeMirror instance, and the first paint can be the new text with no
tokens yet. `openSource` now waits for a line unique to the file before
anything asserts, and every line locator is scoped to `.editor__surface`.
Worth remembering the next time a spec here is green on its own — these
specs share one backend and one `AppState`.

### Perspectives in `c4 render` (17 September): PP-178

`c4 render --perspective <name>` now draws the overlay the viewer has
shown since PP-173. Written as `applyPerspective` in
`packages/diagram-core/src/perspective.ts` — a **transform of the payload**
rather than painting rules, so `svg.ts` needs no notion of perspectives:
fading is the `opacity` it already honours and recolouring the
`background` it already reads. The legend rule moved into `diagram-core`
with it, so the viewer and the file cannot disagree.

An unknown name is refused, with the available ones listed, **before**
Node is needed: the viewer can afford to fade the whole diagram because
its picker shows what exists, but at a command line that result is
indistinguishable from a bug.

Two things the first render showed that no test would have: edge labels
stayed crisp over faded lines (a label floating over nothing reads as
belonging to something else), and the badge had to sit outside the
measured box or it would cost a node's own text a line.

### Dynamic perspectives (17 September): PP-179

`c4 webapp --dynamic-perspectives` lets the **server** read a
perspective's `url` and hand the value to the page, which badges it and
lists it in the legend; it refreshes every 60s, as upstream does.

**Off by default, and the reasoning is the point.** The assistant is
opt-in because it sends the workspace out; this is opt-in for a sharper
reason — the addresses come from the *workspace file*, so opening
someone else's model would otherwise make this machine call their hosts.
The capability is reported by `/api/capabilities` and the route refuses
with 403 when off, so the guarantee holds against a crafted request
rather than living in a hidden button. Only `http`/`https` are followed
(a `file://` URL in a model must not turn a diagram into a way to read
this disk), at most 50 distinct URLs per refresh, 10s timeout.

**Values are keyed by URL, not by item.** A relationship declared in DSL
has no id of its own — the graph layer names its edge after its
endpoints, per view — so keying by URL is both what the client can match
and what makes two items watching one endpoint cost one request. This
was found by a test asserting `values["rel"]`, which is the sort of thing
that only surfaces against a real workspace.

The tests run a real `http.server` on localhost rather than patching
`urlopen`: what is worth pinning is that the route *reaches* a URL and
falls back the way upstream does, and a stub would assert none of it.

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

---

## Open now

**Nothing.** No open PRs, no open `PP` tickets.

---

## The Dependabot majors, and how they went

All seven, resolved 14 September. Kept because the *reasoning* is the
reusable part — the next framework bump will ask the same questions.

| Bump | Outcome | |
|---|---|---|
| `@types/node` 18 → 26, both trees | **Declined** | PP-165, #197 |
| `marked` 15 → 18 | Taken | PP-166, #198 |
| `typescript` 5 → 7 | Taken | PP-167, #199 |
| `react` + `react-dom` 18 → 19 | Taken | PP-168, #200 |

**The `@types/node` decline is the one to remember.** Types must not exceed
the runtime floor, and the floor here is Node 18 — promised in `README.md`
and in the error `render.py` raises when it cannot find a node binary.
`packages/diagram-core` is bundled into the committed renderer that ships
in the wheel and runs on the *user's* Node, so nothing in this repo would
have caught the mismatch: CI runs Node 20 and the failure lands on someone
else's machine. Both are now in `dependabot.yml`'s ignore list beside
`@types/vscode`, which was pinned for the same reason in PP-163. Raising
any of them means raising the stated floor — a release decision.

**TypeScript 7 is the Go rewrite**, not an increment, and it broke exactly
one thing: TS 5 auto-included every `@types/*` it could find by walking up
from the tsconfig, and TS 7 does not. The two Node-facing files — the
renderer CLI and the extension's resolver — lost `process`, `Buffer`,
`fetch` and the `node:` builtins. Fixed by naming them in `types`. The
evidence it was safe is that the committed bundle came out **byte-identical**.

**React 19 looked like it should fail, and didn't.** `reactflow@11.11.4`
is the frozen final v11, and xyflow's tracker says v11 does not support
React 19 because of `zustand ^4.4.1` — which really is what is installed
(4.5.7). It builds regardless, which proves nothing, so the canvas was
driven directly: load a view, select a node, drag it, zoom, capture every
console message. 7 nodes before and after, node moved by (35, 23), no
React warnings. The tracker is aimed at older zustand; 4.5.7 is a late 4.x.

Cost, stated rather than buried: **React 19 adds ~8% gzipped payload**
(281.47 → 304.28 kB).

### Two things found on the way

- **`e2e/docs.spec.ts` now exists.** The Docs page had *no* coverage, which
  is how a three-major bump to its only dependency (`marked`) could have
  landed on a green build alone.
- **Three 409s appear when dragging a node**, from layout-sidecar saves
  racing. Confirmed pre-existing — the same probe on React 18 produces the
  same three — so they were not caused by any of this, and nobody has
  looked at them. Worth a ticket if they ever become noise.

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

Each of these cost time on 13 September.

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
- **CodeMirror only renders its viewport.** A Playwright assertion about a
  token 100 lines down fails with `Received: 0`, which is indistinguishable
  from the bug it was meant to catch. Scroll until the line exists.
- **The `jira` skill is workspace-level**, so `/jira` fails from inside
  this repo. Call `jira_helper.py` directly — CLAUDE.md has the commands.
