# Where things stand, and what to pick up next

The working state of the repo between sessions. `roadmap.md` holds the
long-range plan and `studio-editor-plan.md` is the completed record of the
editor work; this file is the short horizon — what just landed, what is
open right now, and what to do next.

**Keep it current.** It is only worth reading if it is true, so update it
when you finish a run of work, not when you remember.

Last updated: **24 October 2026**, after the interface run
(PP-195 … PP-201): animated relationships, segment re-routing with steps
and pinned sides, named layouts, and file-based themes; then multi-line
strings in the parser (PP-202), properties on screen (PP-203, PP-204),
a details card on the Diagrams page (PP-205), and a badge on elements
that have properties (PP-207), coloured by a style if wanted (PP-208),
and the canvas controls stacked top-left so the breadcrumb is never
covered (PP-206).

---

## Current state

| | |
|---|---|
| PyPI | **0.3.0** — published 13 Sep 2026, tagged `v0.3.0`, verified by isolated install |
| VS Code extension | **0.3.1**, packaged as `.vsix` only. Not on the Marketplace, and versioned independently of the Python package |
| `main` | Green. Four CI jobs: Python gate, bundle + layout, VS Code extension packaging, and the `render` dogfood |
| Open PRs | **None** |
| Open `PP` tickets | PP-192 (drive the `.vsix` for a day — needs a human), PP-193, PP-194 — see *Open now* |
| Frontend runtime | React **19**, TypeScript **7**, Vite **8**, marked **18**. `reactflow` stays on **11** — see below |

---

## Recent work

The last run only. Older entries are in the tickets and in git;
keeping them here turned this file into a changelog, which is not what
it is for — it is the thing you read *first*, so it has to stay short.

### Marching ants on hover (PP-195), and a view-switch race (PP-200)

The toolbar's **Animate** toggle (`a`) makes the hovered element's
relationships, and its descendants', march. It is CSS only: a dash
offset animation, with the period derived from the dash so a solid line
gets the default dash while it moves. `prefers-reduced-motion` turns it
off. PP-200 was found while testing it. A position tween still running
from the previous view kept painting its frames after a switch, so the
canvas showed the old view under the new breadcrumb. The fix is
`cancelAnimationFrame` before the new nodes go in.

### Re-routing Step / Smooth step lines (PP-196)

This works like a whiteboard elbow connector. A hovered step line shows a
handle on each straight run, and dragging one slides the run sideways
while its neighbours stretch. Only interior corners are stored, as
`edges` waypoints with the edge flagged in the sidecar's new `routing`
section. The two ends are recomputed against the nodes, so moving a node
slides the attachment along its side. `packages/diagram-core/src/orthogonal.ts`
is the one implementation, used by both the canvas and `svg.ts`, so
`c4 render` draws the same route. A re-routed edge keeps its route in
every line style until **Reset route** is chosen.

### Steps and pinned sides on re-routed lines (PP-201)

The follow-up asked for after PP-196. Double-clicking a run of a step
line, or **Add step here** on right-click, splits it into a 24px jog
whose two new runs have handles. Removing a step needs no action of its
own: drag it flat, and the corner that no longer turns is not stored.
Each end of the line has a round handle. Dragging it onto the element
pins that end to the nearest side, stored in a new `sides` section. The
route leaves a pinned side square-on along a 20px stub, and goes round
the node rather than through it when it has to double back. The stub is
recomputed and never stored, which is why `routeBends` drops it by index
and `insertStep` keeps a new step off it.

### `routing Orthogonal` is drawn (PP-209)

A relationship style's `routing Orthogonal` resolves to the edge's
`styleRouting`, which the canvas and `svg.ts` draw with the PP-196
router whatever the toolbar's line style. It is deliberately not the
`routing` key: that one is the sidecar's record of a user re-route, so a
save would copy the model's choice into per-user state and Reset route
would undo it. `Direct`/`Curved` are not painted; a later rule
overriding an earlier `Orthogonal` clears it.

### Dynamic-view step ids (PP-198)

A step's edge id was `step-<order>-<src>__<dst>`, so inserting a step
renumbered every later one and dropped its saved waypoints, route, sides
and label offset; two `parallel` steps between one pair shared an id.
Ids are now `step-<src>__<dst>__<n>`, by endpoints and occurrence like
static views' unaliased edges. Each step edge lists its old id under
`previousIds`, and `layout_sidecar.saved_for` falls back to it, so an
existing sidecar still applies and the next save rewrites it.

### Canvas controls stacked top-left (PP-206)

The breadcrumb, the toolbar and the alignment tools are now one column
in the canvas's top-left corner, in that order, and the details card has
the top-right corner to itself. The toolbar used to sit on the right
with no width limit, and at about 1110px it covered the breadcrumb on any
drilled-down view. To keep it to one row, the export formats are under
**Export ▾** and the Hover/Animate/Snap toggles under **View ▾**
(`ToolbarMenu.tsx`); their keyboard shortcuts are unchanged. Beside an
open card the column stops 8px short of it. Below 640px the card is a
full-width sheet, so it starts under the column, whose height GraphPane
measures into `--controls-height`. `e2e/graph-controls.spec.ts` checks
the deepest trail a sample has, a component view, at three widths.

### Badge colours (PP-208)

The badge is now a solid chip in the element's text colour, which
already contrasts with the box. A `c4studio.badge` element-style
property overrides that per tag, as a hex colour; `_apply_styles` passes
it through as `badgeColor`. The "i" is black or white by the chip's
luminance (`readableOn` in `ElementNode.tsx`), so no chosen colour can
hide its own glyph. A colour that is not hex is ignored on the diagram
and reported by the new `invalid-badge-colour` lint rule.

### A properties badge on elements (PP-207)

An element with properties shows a small ⓘ in its bottom-right corner,
the one corner nothing else uses. Hovering gives the count; clicking
selects the element and opens the details card. Only a surface with a
card wires `onShowDetails`, so the Source page, the Explorer, embeds and
`c4 render` show no badge. PNG/SVG export drops anything marked
`export-hidden` through `html-to-image`'s `filter`, and an e2e test
reads the exported file to check that.

### A details card on the Diagrams page (PP-205)

The toolbar's **Details** button (or `i`) opens a 320px card under the
toolbar that follows the selection: one element, one relationship line,
or a placeholder for nothing or several. It overlays the canvas rather
than narrowing it, and opens on request rather than on click, because
selecting is how a drag starts; a one-time "Press i for details" hint
makes it findable. The layout was reviewed by `ux-reviewer` first.
`ElementDetails` is now the one copy of the details content, used by the
Explorer too. The view graph gained `properties` on nodes and a
`relationship` on edges that draw exactly one (by endpoints, then label).
The toolbar now wraps instead of running off the canvas's left edge.

### Properties on screen (PP-203), and the site's link URLs (PP-204)

Element and relationship `properties` now show in the Explorer's details
panel and in a Properties section on each published view page. One rule
on both sides: `shown_properties` in `graph/view_graph.py` drops the
`c4studio.*` settings, a multi-line value is Markdown, a one-line value
is as written, a bare URL is a link. In the SPA the Markdown goes
through its own `marked` instance that escapes raw HTML and allows the
same URL schemes as the site, because a value is model data, unlike
`!docs`. On the site a relationship is listed only when the view draws
an edge between its own endpoints: unaliased relationships have no id,
and a lifted edge is not its relationship. PP-204 was found on the way:
the site's Markdown let a `"` in a link URL close the attribute, and
took any scheme.

### Multi-line strings: text blocks and continuation (PP-202)

`"""` text blocks and a trailing `\` now parse as structurizr-java's
`preProcessLines` reads them, in the tokenizer: a text block becomes an
ordinary `STRING`, and a joined statement's tokens keep the line it
started on, because the parser pairs arguments by `token.line`. Before
this a text block silently read as `""`, with its content as stray
tokens — found while answering how a property could hold Markdown.
`!const`/`!var` accept one as their value, and the editor paints a
block as a string to its closing quotes.

### Named layouts (PP-197)

The toolbar's **Layouts** menu keeps a view's current arrangement under a
name, loads one back after asking, and deletes one. A named layout is a
snapshot of every per-view sidecar section, stored in a new `snapshots`
section. Loading copies it into the working layout, which is still what
autosave writes and `c4 render` reads. The client flushes the working
layout before saving a snapshot, because the server copies what is on
disk. `_write_layout_sidecar` now keeps `snapshots` from disk unless it
is given, rather than every writer threading it through. That is the
better pattern for the next section too (CLAUDE.md says so).

### No more static.structurizr.com in tests (PP-199)

`themes` now accepts a file path as well as a URL. The theme is inlined
at parse time and relative icons become `data:` URIs. The SVG preview
e2e test uses an offline fixture, because CI cannot resolve
`static.structurizr.com`. Samples that name upstream themes by URL still
try to fetch them, and print `Skipping theme …` when offline. That is
expected, not a failure.

---

## Open now

- **PP-193 / PP-194:** impact analysis in the Studio, and the diagram
  diff as a PR comment with a visual overlay. Both are carried over from
  the September run.
- **PP-210:** `workspace extends <file>`, which is a parse error today.

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
