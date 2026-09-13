# Where things stand, and what to pick up next

The working state of the repo between sessions. `roadmap.md` holds the
long-range plan and `studio-editor-plan.md` is the completed record of the
editor work; this file is the short horizon — what just landed, what is
open right now, and what to do next.

**Keep it current.** It is only worth reading if it is true, so update it
when you finish a run of work, not when you remember.

Last updated: **13 September 2026**, after the 0.3.0 release.

---

## Current state

| | |
|---|---|
| PyPI | **0.3.0** — published 13 Sep 2026, tagged `v0.3.0`, verified by isolated install |
| VS Code extension | **0.3.1**, packaged as `.vsix` only. Not on the Marketplace, and versioned independently of the Python package |
| `main` | Green. Four CI jobs: Python gate, bundle + layout, VS Code extension packaging, and the `render` dogfood |
| Open PRs | Seven Dependabot **majors** — see below. Nothing else |
| Open `PP` tickets | None |

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

---

## Open now: seven Dependabot majors

These arrived on the Monday schedule after the release. Dependabot is
configured to keep majors out of the grouped PRs so they get read — so
read them. **Every one needs the manual bundle rebuild** (CLAUDE.md), and
a bundler or framework swap is exactly where a green build and a broken
app diverge.

Ordered by what I would do first:

| PR | Bump | Assessment |
|---|---|---|
| #186 | `@types/node` 18 → 26 (root) | `packages/diagram-core` is bundled into the **headless Node renderer** that ships in the wheel. Typing against Node 26 while users may run older is the same mistake as PP-163. Check what the renderer actually requires before taking it |
| #188 | `@types/node` 18 → 26 (`editors/vscode`) | **Probably decline.** `engines.vscode` is `^1.85.0`, and that VS Code ships Node 18. This is PP-163 again in a different package — types must not exceed the host floor. If declined, add it to the `ignore` list beside `@types/vscode` with the reason |
| #184 | `marked` 15 → 18 | Three majors. Used in exactly one place, `frontend/src/components/DocsPane.tsx`, to render workspace documentation. Small blast radius, but check the API and render `samples/hedge_fund` docs before and after |
| #185 / #187 | `typescript` 5.9 → 7.0 (root + extension) | A major compiler bump across a workspace with strict settings. Do the two together or the two trees disagree. Expect real work |
| #183 / #182 | `react` + `react-dom` 18 → 19 | **The large one, and last.** Must be done as a pair. The real question is React Flow: check its peer range before starting, because `packages/diagram-core` is consumed by both the SPA *and* the headless renderer, and the renderer must keep working without a DOM |

Suggested shape: one ticket each, `@types/node` decisions first (cheap,
and one of them is likely a decline with a `dependabot.yml` entry), then
`marked`, then TypeScript, then React as its own piece of work.

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
- **The `jira` skill is workspace-level**, so `/jira` fails from inside
  this repo. Call `jira_helper.py` directly — CLAUDE.md has the commands.
