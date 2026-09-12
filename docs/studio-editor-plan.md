# Studio: the in-app DSL editor

The staged plan for turning c4studio from a viewer into an authoring
tool — in-app DSL editing, file navigation that survives growth, and a
designed seam for an AI assistant.

**Status: in progress.** See [Progress](#progress) for what has landed.
Ticket numbers are Jira `PP`.

---

## Why

c4studio is read-only today. You edit DSL in an external editor and a
2-second mtime heartbeat re-parses and re-renders — which is why the
in-browser editor sat parked in `roadmap.md` Phase 4 as "convenience
rather than capability".

Three things changed that judgement:

1. **Authoring is the job.** The tool is called c4studio; a studio you
   cannot type in is a viewer with a good name.
2. **Scale.** Workspaces are growing in both directions — nested folders
   *and* more workspaces. The flat file picker and the eager directory
   walk do not survive that.
3. **An assistant needs somewhere to write.** AI help with DSL is only
   useful if there is an editor for it to write into.

---

## Principles

These settle most of the design; the rest follows.

### 1. Text-first, never model-first

The editor edits DSL *text*. It never generates DSL from the model.

This is forced, not preferred. `parse_dsl` textually rewrites the source
before tokenising — `_expand_includes` flattens every `!include` into one
string, `_strip_scripts` deletes `!script` blocks, `_apply_constants`
substitutes `${NAME}` away — and the tokeniser then discards comments and
all whitespace. No CST is retained and no serialiser exists. A model→DSL
writer would have to reconstruct includes, constants and scripts from
information that no longer exists, and would destroy the user's comments
and formatting on every save.

So **the diagram is a preview of the text**, and the existing live-reload
pipeline is the render loop.

### 2. Reuse the reload loop; don't build a second one

Saving bumps mtime, which already drives re-parse, cache invalidation,
layout re-application and `generation++`. Save *is* the render trigger.
The work is making that loop safe against the editor's own writes.

### 3. Capability lives on the server

Viewer mode is not hidden buttons — write routes 403, so the guarantee
holds against a crafted request.

### 4. No fourth copy of the DSL vocabulary

The keyword and property sets already exist three times: `parser/dsl.py`'s
tokeniser, `frontend/src/highlight.ts`, and
`editors/vscode/syntaxes/structurizr-dsl.tmLanguage.json` (whose header
already documents the sync burden). The CodeMirror layer reuses
`highlight.ts`'s vocabulary and classifier rather than adding a grammar.

A real grammar is explicitly off the table — `roadmap.md` lists
ANTLR/tree-sitter under "Rejected options — do not re-litigate".

---

## Modes

| | Command | Behaviour |
| --- | --- | --- |
| **Studio** | `c4 webapp <path>` | Full app: browse, edit, save, create. **Default.** |
| **Viewer** | `c4 webapp <path> --viewer` | No DSL writes (403). Layout dragging, group collapse and title moves **still persist** — you cannot change the model, but you can arrange the view. |

Viewer keeps its sidecar writes because arranging a diagram is part of
reading it, and the sidecar is gitignored per-user UI state either way.

This flipped the previous default: `c4 webapp` used to be read-only.
Anyone using it for a kiosk or an embed should add `--viewer`.

---

## Tickets

One Jira ticket each, branch per ticket, PR-first, per the delivery
conventions in `roadmap.md`.

### Phase A — Foundations (no editing yet)

| # | Ticket | Scope | Deps |
|---|---|---|---|
| A1 | `feat(webapp): Studio and Viewer modes` | Frozen `AppConfig` on `AppState`; `create_app(..., *, read_only=False)` keyword-only so existing callers are untouched; `c4 webapp --viewer`; `_require_writable` as a **FastAPI dependency** (a route that writes cannot forget to depend on it the way it could forget a call); `GET /api/capabilities`. | — |
| A2 | `fix(webapp): keep watching includes after a failed reload` | Extract `_reload_now(state)` so the poll path and the save path are one implementation; fix the stale `watch_files` bug. | — |
| A3 | `feat(parser): in-memory source overlay for !include` | `overlay: Mapping[Path, str] \| None` on `parse_dsl` → `_expand_includes`, consulted **before** `is_file()` so a not-yet-saved fragment also resolves. Default `None` is a no-op. First increment of the `SourceResolver` roadmap row. | — |
| A3b | `fix(parser): carry the position of an unsupported directive` | Found while building A3, see [Diagnostic attribution](#diagnostic-attribution). Smaller than first thought — one call site, not a systemic failure. | A3 |
| A4 | `feat(webapp): POST /api/check for unsaved buffers` | Structured diagnostics for arbitrary text; no disk writes, no `AppState` mutation. Also surface `workspace.diagnostics` on `/api/status` so **Viewer gains warning display** — useful independent of editing. | A3b |

### Phase B — The editor

| # | Ticket | Scope | Deps |
|---|---|---|---|
| B1 | `feat(webapp): PUT /api/source` | Atomic write, content-hash fingerprints, 409 conflict flow, synchronous reload, **and the UTF-8 fix** (see Risks). | A1, A2 |
| B2 | `feat(frontend): CodeMirror 6 DSL editor` | Dependency in `frontend/package.json` — **never** `packages/diagram-core`, which is bundled into the headless Node renderer and must never need a DOM. `dslLanguage.ts` as a `StreamLanguage` built from a refactored `highlight.ts`. Debounced `/api/check` → `@codemirror/lint` squiggles. | A1, A4, B1 |
| B3 | `feat(frontend): split authoring view` | Source page becomes editor-left / diagram-right. `GraphPane` is reused as-is — already prop-injected for exactly this. | B2 |
| B4 | `feat(frontend): DSL autocomplete` | Keywords from the shared vocabulary; element ids and aliases from the loaded workspace; view keys after `filtered` (**not** in `include`/`exclude` — see [Completion needs no endpoint](#completion-needs-no-endpoint)). | B2 |

### Phase C — Scale

Editing files *within* a loaded workspace needs **no new discovery
endpoint** — `GET /api/source` already enumerates the root plus every
`!include` fragment with root-relative paths. Phase C is about browsing
*across* workspaces.

| # | Ticket | Scope |
|---|---|---|
| C1 | `perf(webapp): cache source discovery` | `/api/files` does a full recursive walk **and reads the first 8 KB of every candidate DSL file** on every call, uncached. Stat-revalidated cache — see [What discovery actually cost](#what-discovery-actually-cost). |
| C2 | `feat(webapp): file tree with fragments` | `_is_workspace_root` hid `!include` fragments, so they were invisible to the picker while being valid edit targets. `/api/files` now returns `{path, kind}`; `GET /api/file` closes the read asymmetry — see [Reading was the asymmetric one](#reading-was-the-asymmetric-one). |
| C3 | `feat(frontend): searchable file tree` | Replace the flat, unfiltered, unvirtualised `FilePicker`. Logic in a pure `fileTree.ts`; windowed without a dependency — see [A tree flattens to uniform rows](#a-tree-flattens-to-uniform-rows). |
| C4 | `perf(webapp): cache hygiene` | `/api/workspace` runs `dataclasses.asdict` over the whole model on every call — on mount *and* every reload. Bound the unbounded per-view graph cache. |
| C5 | `feat(webapp): file operations` | New file, new folder, rename, delete — capability-guarded and `_safe_resolve`d. |

### Phase D — Creating workspaces

| # | Ticket | Scope |
|---|---|---|
| D1 | `feat(cli): c4 new and starter templates` | Starter DSLs in the package (minimal, system-context, full C4, deployment), reusing the write path. |
| D2 | `feat(frontend): new workspace in-app` | Template picker, target folder, open in the editor. |

### Phase E — Assistant (designed now, built last)

| # | Ticket | Scope |
|---|---|---|
| E1 | `feat(webapp): assistant endpoint` | Opt-in behind a flag, key from the environment, clearly marked as the one feature that leaves the machine. Context is already available: buffer text, `/api/check` diagnostics, the model summary, and the keyword table in `dsl-support.md`. |
| E2 | `feat(frontend): propose-a-diff UX` | The assistant returns DSL text; the editor shows it as a diff against the buffer; the user applies or rejects. Nothing AI-specific touches the editor core — it is just another producer of text, which is why Principle 1 matters. |

### Phase F — VS Code

| # | Ticket | Scope |
|---|---|---|
| F1 | `feat(vscode): read-only preview` | **Feature-detect `GET /api/capabilities`** rather than passing `--viewer`: `preview.ts` spawns whatever `c4` resolves on the user's machine, which may be an older release that would exit non-zero on an unknown flag. Absent endpoint → old backend → hide editing client-side. Only after A1 is *released*. |

---

## Key designs

### `POST /api/check`

Most of this already exists. `c4 check - --path X` does the job for the
VS Code extension in ~10 lines: `parse_dsl(text, base_dir=path.parent,
path=path)`, then `workspace.diagnostics`, or `error.diagnostics` on
`ParseError` — which carries *every* recovered problem, not just the
first.

The hard case is an unsaved **fragment**, which is not a valid standalone
workspace. It must be checked in the context of its root with the buffer
substituted — hence the overlay in A3. Root inference needs no extra
client state: if the target is `state.current_path` or in
`state.watch_files`, the root is the loaded workspace; otherwise the
target is its own root. One code path covers both:

```python
overlay = {target: body.content}
root_text = overlay.get(root) or root.read_text(encoding="utf-8")
workspace = parse_dsl(root_text, base_dir=root.parent, path=root, overlay=overlay)
```

Diagnostics must be relativised to the root for the client, and — once
A3b lands — will carry the fragment they came from. Keep
`Diagnostic.to_dict()` as the single source of key names so the webapp
and `c4 check --json` never drift.

### Diagnostic attribution

**Measured during A3, and the first reading of it was wrong** — recorded
here because the correction is the useful part.

`!include` is flattened before tokenising, so every position the parser
sees is a line of one synthetic source. `SourceMap` maps those back, and
both `_warn` and `_record_error` run positions through it. That machinery
is correct, and errors inside a fragment *do* name the fragment. The
plan previously claimed otherwise, on the strength of one example.

That example was misread. A relationship missing its destination reported
against the root, but only because the parser consumes forward looking for
the destination and the token it finally rejects genuinely *is* past the
end of the fragment. Resolution was right; the position was just later
than the mistake.

The one real defect, fixed in A3b: a single `_warn` call site formatted
the line into the message (`"Line 4: unsupported directive ..."`) rather
than passing it as a field, so the diagnostic came out with no path and
no line — and the number in the prose was a *flattened* line, belonging
to no file the user has open. Unplaceable as a squiggle. It now carries
`path`, `line`, and a column range spanning the `!` and the directive
name.

Residual, not worth fixing pre-emptively: an error's position is the token
where the parser noticed, which for a construct spanning lines can be
later than where a human would point. `_guard` already captures the
statement's start line for recovery, so if the editor's squiggles land
awkwardly in practice, that is where to look.

### The editor's buffer model

Settled in B2. The Source page keeps one buffer per file — `{disk, text,
fingerprint, editable, staleOnDisk}` — where `text !== disk` *is* the
definition of dirty, so switching files never loses typing and needs no
prompt.

The rules that matter are what happens when a reload lands under an open
buffer:

- **Clean buffer** — adopt the new text and fingerprint silently. This is
  the ordinary case: someone edited the file in VS Code.
- **Dirty buffer** — keep the user's text and **keep the old
  fingerprint**. Dropping typing to show a file the user did not change is
  the worse failure, and the stale fingerprint is what turns the next save
  into a 409 instead of a silent overwrite. The buffer is flagged
  `staleOnDisk` so the banner can say so before the save is attempted.

A 409 offers three ways out — overwrite with mine, discard mine and take
disk, or keep editing — because the conflicting content arrives in the
409 body and needs no second round trip.

`PUT` returns the generation its own reload produced; the app adopts it,
so the 2-second poll does not then treat the save as someone else's edit
and refresh a second time.

### The split is a layout component, not a feature

B3 added no wiring between the editor and the diagram, and that is the
point. `SplitPane` takes two nodes and knows nothing about either; App
composes `SourcePane` and `GraphPane` into it. The diagram follows the
text through the loop that already existed — save → reload → `refresh()`
hands the view a new identity → the graph refetches — which is Principle 2
paying out a second time.

Two layout facts worth keeping, because both fail invisibly in a headless
check and produce a zero-height pane:

- **CodeMirror and React Flow both measure their container.** Neither may
  depend on a percentage height resolving inside a flex item; both get
  their height from an explicit `flex` rule instead.
- **Fixed chrome adds up.** Sidebar (300px) + file list means the editor
  and the diagram split what is left, so the file list is narrower on this
  page and the diagram half collapses to a rail. A real file tree with
  search is C3's job, not something to solve by widening this column.

### Completion needs no endpoint

Two findings from B4, both of which removed work rather than adding it.

**Element ids are already the aliases.** `dsl.py` computes
`elem_id = alias or name.replace(" ", "_").lower()`, so an element's `id`
in `/api/workspace` *is* the identifier you type in the DSL whenever one
was declared. The completion list needed no new endpoint and no parser
change — the data has been on the wire since the model was first served.

**The plan was wrong about view keys.** This table used to say "view keys
in `include`/`exclude`". `FilteredViewParser` upstream declares
`filtered <baseKey> <include|exclude> <tags>`: the view key is the
argument to `filtered`, and what follows `include|exclude` *there* is
tags. Inside a view, `include`/`exclude` take element expressions. So
completion offers view keys after `filtered`, identifiers and expressions
after a view's `include`/`exclude`, and nothing after a filtered view's —
those tags are the user's own vocabulary. Checking `../structurizr/`
settled it in seconds, which is what that checkout is for.

Context comes from a look at the current line, not a parse tree: after
`->`, at the head of a statement, after `include`/`exclude`, after
`filtered`. Directive lines are suppressed the way the highlighter
suppresses keyword colouring on them, except the four that take an
identifier (`!element`, `!elements`, `!relationship`, `!relationships`).
Directive *names* are deliberately not offered — that would be a second
vocabulary to keep in step with `dsl-support.md`.

**Dependencies added** (frontend only, per the ticket): `@codemirror/state`,
`view`, `commands`, `language`, `lint` and `@lezer/highlight`, plus
`@codemirror/autocomplete` in B4. Not the `codemirror` meta-package, which
would also pull search. The committed bundle grows ~370 KB raw (~110 KB
gzipped) across B2 and B4; acceptable for a local-first app served from
`127.0.0.1`.

The three-way keyword duplication is now a *two*-way one plus a consumer:
`highlight.ts` became the vocabulary module and `dslLanguage.ts` builds the
`StreamLanguage` from it, so the SPA has one copy, not two. See
[Deferred decision](#deferred-decision).

### What discovery actually cost

Measured before designing the C1 cache, on a synthetic 220-file tree (20
workspaces, 10 `!include` fragments each, nested two deep):

| | per call |
|---|---|
| `_iter_source_files`, uncached | 16.0 ms |
| …of which the 8 KB reads | 12.1 ms (**79%**) |
| stat-ing the same files instead | 0.4 ms |

That settled the shape. The plan had said "directory-mtime-keyed", which
would have been **wrong on its own**: a directory's mtime does not move
when a file's *contents* change, so a fragment edited to add a `workspace`
block would never appear in the picker. The cache therefore records a
signature for both — mtime for each directory walked (catching adds,
removes and renames) and mtime+size for each candidate file (catching an
edit that changes the answer) — and a file whose signature is unchanged
keeps its previous answer instead of being reopened.

Warm calls land at 0.48 ms, 34× faster, with identical output. The
regression test that matters asserts no candidate file is opened a second
time when nothing changed; it was checked against a deliberately
un-cached build to confirm it actually fails there.

### Reading was the asymmetric one

C2 set out to stop hiding `!include` fragments from `/api/files`, and
turning them up exposed a gap nobody had noticed: **`PUT /api/source` and
`POST /api/check` both take any path under the root, and reading took
none.** A fragment belonging to some other workspace could be written and
checked, but never opened. `GET /api/file?path=` closes that, with the
same `_safe_resolve` guard and the same `editable` contract the loaded
workspace's files already carry.

The classification is free: C1's discovery walk already computed
workspace-or-not per candidate and threw the answer away. Keeping it is
the whole of the backend change.

One thing that had to become deliberate: layout sidecars used to drop out
of the listing by *failing* the workspace-root test. Now that failing it
merely means "fragment", `_classify` has to exclude `*.layout.json`
explicitly — they are gitignored per-user UI state and must never be
offered for editing. A test pins it.

The shape change to `/api/files` is safe because the SPA is its only
consumer and ships in the same wheel; the VS Code extension probes
`/api/status` alone. That was checked rather than assumed.

### A tree flattens to uniform rows

Which is what let C3 virtualise without adding a windowing dependency —
the constraint in `CLAUDE.md` shaping the solution rather than blocking
it. Every row is one line of fixed height, so row *N* sits at
`N * ROW_HEIGHT` and the visible slice is arithmetic, not measurement.
Roughly 25 rows are in the DOM regardless of the tree's size.

The other deliberate choice is where the thinking lives. `fileTree.ts`
holds it as pure functions — build, filter, order, flatten — and the
component only draws what they return. That is what made it checkable:
the ordering, the counts, the force-expansion during search and the
2000-file behaviour were all exercised directly, which a tree of DOM
nodes could not have been in this environment.

Two behaviours worth keeping if this is ever rewritten:

- **Search force-expands, but does not *change*, the expansion.** A match
  hidden inside a collapsed folder is a search that found nothing;
  clearing the box returns the tree exactly as the user had it.
- **Folders start shut**, except those leading to the loaded file. A tree
  that opens itself completely is the flat list it replaced, which stops
  being usable at exactly the scale the tree exists for.

---

## Risks

**High — lossy reads corrupt files.** `get_source` reads with
`errors="replace"`. Fine for a viewer; **silent data loss for an editor** —
a file with one invalid UTF-8 byte round-trips with that byte permanently
replaced by U+FFFD. Fix in B1: try a strict decode first; on
`UnicodeDecodeError` keep serving replaced text for display but mark the
entry `editable: false`, and have `PUT` refuse that path. **Do not ship
the editor without this.**

**High — version skew in VS Code.** Covered by F1's feature detection.

**Medium — `/api/check` cost on large workspaces.** A full re-parse per
400 ms debounce. Measure on `samples/hedge_fund/workspace.dsl` during A4;
memoise on `(root, sha256(content))` only if it bites.

**Low — case-insensitive filesystems.** `Path.resolve()` does not
case-normalise on macOS, so `!include Model/foo.dsl` against an overlay
keyed `model/foo.dsl` misses and falls back to disk. Symptom is "my
fragment edits aren't reflected", not corruption.

**Low — no undo across a save.** CodeMirror's history is client-only; a
destructive save is recoverable only through git. A `.bak` sidecar was
considered and rejected — it would collide with the sidecar conventions
in `CLAUDE.md`.

---

## Verification

Standing gate per PR: `uv run pytest`, `ruff check`,
`ruff format --check`, `mypy`, plus a rebuilt and committed frontend
bundle for any frontend change.

The test cases that carry weight:

- **403 in Viewer** — `PUT /api/source` refused **and the file on disk is
  byte-identical afterwards**; layout routes still 200.
- **`/api/check` is pure** — post broken text, then assert all four: file
  unchanged, `/api/workspace` still good, `generation` unchanged, `error`
  null.
- **Unsaved fragment names the fragment** — using
  `tests/fixtures/split_workspace/`, a diagnostic's `path` is the
  fragment, not the flattened root. The single most important test: it
  exercises overlay + `SourceMap` + relativisation together.
- **One save, one reload** — after a successful `PUT`, the *next*
  `/api/status` returns the same `generation`.
- **Conflict** — stale fingerprint → 409 carrying the external content,
  and the file still holds the external text.
- **Broken save** — 200 with diagnostics, file written, previous workspace
  still served, and `GET /api/source` returns the **new** text.
- No `.tmp` files left behind.

Live verification against `samples/hedge_fund/workspace.dsl` — the one
sample combining `!include` fragments, docs and ADRs, so it exercises
fragment editing, per-fragment diagnostics and the reload loop together.

---

## Non-goals

State these in the tickets so they don't creep in.

- **Model → DSL generation** (Principle 1).
- **Multi-user, locking, branches** — ruled out by `CLAUDE.md`. Upstream's
  DSL editor takes a workspace lock precisely because it is multi-user;
  ours is not. Worth knowing: upstream's editor is also gated behind a
  feature flag that defaults off, and Structurizr **Lite** — the closest
  analogue to c4studio — has no DSL editor at all. This work puts
  c4studio ahead of its nearest comparator, not behind it.
- **A real grammar** (ANTLR/tree-sitter) — see `roadmap.md`.
- **Editing `!docs`/`!adrs` markdown** — `_safe_resolve`'s suffix
  allowlist rejects `.md`; widening it needs its own design.
- **`fsync` on write** — unnecessary durability cost for a local
  single-user editor on a journalling filesystem.

---

## Progress

| Ticket | Status | PR |
|---|---|---|
| A1 — Studio/Viewer modes, `GET /api/capabilities` | ✅ Done | #128 (PP-119) |
| A2 — Keep watching includes after a failed reload | ✅ Done | #129 (PP-120) |
| A3 — Parser source overlay | ✅ Done | #131 (PP-121) |
| A3b — Fragment diagnostic attribution | ✅ Done | PP-123 |
| A4 — `POST /api/check` | ✅ Done | PP-122 |
| B1 — `PUT /api/source` | ✅ Done | PP-124 |
| B2 — CodeMirror editor | ✅ Done | PP-125 |
| B3 — Split authoring view | ✅ Done | PP-128 |
| B4 — DSL autocomplete | ✅ Done | PP-129 |
| C1 — Cache source discovery | ✅ Done | PP-130 |
| C2 — Fragments in the file listing | ✅ Done | PP-131 |
| C3 — Searchable file tree | ✅ Done | PP-132 |
| C4–C5, D1–D2, E1–E2, F1 | ⬜ Not started | not yet ticketed |

Update this table as tickets land, and file the next phase's tickets when
the current one is done rather than all at once.

## Deferred decision

Whether to kill the three-way keyword duplication by generating the
frontend sets from `dsl.py` at build time. Worth its own ticket *after*
B2, when there is a concrete fourth consumer to justify it — not as scope
creep inside the editor work.
