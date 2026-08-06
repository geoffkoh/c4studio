# Forge CSP spike (PP-98)

Answers one question: **can a Forge Custom UI iframe instantiate
WebAssembly, and can it run Pyodide?** That decides whether Structurizr
DSL can be parsed inside Confluence at all, and so whether the Confluence
macro in `docs/roadmap.md` is buildable as designed.

**Answered, August 2026: yes.** Deployed to `geoffkoh.atlassian.net` and
run in a Confluence page:

| Step | Result |
| --- | --- |
| Instantiate an 8-byte WebAssembly module | **yes — 2 ms** |
| Load Pyodide 0.28 from jsDelivr | yes — 1,393 ms |
| `micropip` the wheel and parse DSL | yes — 1,972 ms (`{"name": "Spike", "people": 1, "views": 1}`) |

`unsafe-eval` admits WASM inside Custom UI. An author waits ~3.4 s on a
cold macro edit, once — parsing happens at author time and the result is
stored as workspace JSON, so view time stays Python-free.

Throwaway now that it has served its purpose: delete it, or promote it
into the real macro. The full write-up is in `docs/roadmap.md`.

## What it tests, in order

| Step | Why |
| --- | --- |
| 1. `typeof WebAssembly` | Cheap sanity check |
| 2. Instantiate an **8-byte** module | **The actual CSP test.** `WebAssembly.instantiate` is what CSP gates, so this answers PP-98 in milliseconds without downloading ~13 MB of Pyodide |
| 3. Load Pyodide from jsDelivr | Tests `permissions.external`, separately from the CSP question |
| 4. `micropip` the wheel and parse DSL | End-to-end proof, and a real number for what an author waits for |

Step 2 is the point. If it fails, steps 3 and 4 are skipped and the page
says so — no amount of runtime downloading fixes a refused instantiation.

## What the manifest declares, and why

Atlassian documents exactly five values for `permissions.content.scripts`:
`unsafe-inline`, `unsafe-hashes`, `unsafe-eval`, `blob:`, and script
hashes. **`wasm-unsafe-eval` — the permission the roadmap originally named
— is not among them** (checked August 2026). `unsafe-eval` is the CSP
superset that also admits WASM compilation, so that is what this declares.
Whether Forge's CSP actually behaves that way is precisely what is being
measured; do not assume it from the spec.

## Running it

Needs Node 22+, site-admin rights on the target Confluence site, and the
Forge CLI. Everything below runs from this directory.

```bash
npm install -g @forge/cli
forge login                 # Atlassian account + API token

# Register writes a real app id into manifest.yml, replacing the placeholder.
forge register

# The wheel is served from this app's own resources, so build and copy it.
(cd ../.. && uv build --wheel -o dist)
cp ../../dist/pystructurizr_studio-*.whl static/

forge deploy
forge install --site geoffkoh.atlassian.net --product confluence
```

Then add the **pystructurizr CSP spike** macro to any Confluence page and
read the four lines it prints.

## What it cost to get here

Three things bit, none of them the CSP:

- `forge register --personal` is refused ("Personal apps are not allowed
  in this developer space"); plain `forge register` into the space works.
- The manifest schema requires `app.runtime` **even with no functions**.
- Egress permissions want `- address: https://...`; the bare-string form
  deploys but `forge lint` calls it deprecated.

The CLI also warns it supports Node 22.x/24.x; everything here ran fine on
Node 26.

## The commands that worked

```bash
forge register "pystructurizr CSP spike" --accept-terms \
  --developer-space-id <id from: forge developer-spaces list>
(cd ../.. && uv build --wheel -o dist) && cp ../../dist/*.whl static/
forge deploy --non-interactive
forge install --site geoffkoh.atlassian.net --product confluence \
  --environment development --non-interactive
```

Credentials come from `FORGE_EMAIL` / `FORGE_API_TOKEN` in the
environment, so no token reaches `argv` or shell history. Note `forge
login --non-interactive` insists on its own flags, but every other command
honours the environment variables, so logging in is unnecessary.
