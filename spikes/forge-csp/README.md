# Forge CSP spike (PP-98)

Answers one question: **can a Forge Custom UI iframe instantiate
WebAssembly, and can it run Pyodide?** That decides whether Structurizr
DSL can be parsed inside Confluence at all, and so whether the Confluence
macro in `docs/roadmap.md` is buildable as designed.

Throwaway. Delete it — or promote it into a real macro — once the answer
is recorded in the roadmap.

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

## Recording the answer

Whatever happens, put it in `docs/roadmap.md` — this is the item that can
invalidate the Confluence design rather than merely cost time.

- **If step 2 fails**, capture the CSP violation from the browser console.
  It names the directive that refused, which distinguishes "`unsafe-eval`
  was insufficient for WASM" from "the permission was not applied at all".
  Damage is contained: view and export are already Python-free, so only
  the authoring path needs a different answer.
- **If it passes**, record the step 3 and 4 timings. They are what an
  author waits for on a cold macro edit, and the Node measurements in
  PP-96 (~1.1 s boot) are a floor, not a prediction.
