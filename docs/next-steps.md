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
