---
name: release
description: Cut a c4studio release — bump the version, rebuild the committed frontend bundle, build and publish the wheel to PyPI as c4studio, and package the VS Code extension as a .vsix. Use when the user wants to release, publish, or ship a new version.
disable-model-invocation: false
argument-hint: "[patch|minor|major] [--python-only|--vscode-only]"
---

# Cut a c4studio Release

Two artifacts ship independently and carry **separate version numbers**:

| Artifact | Version lives in | Published to |
| --- | --- | --- |
| Python package `c4studio` | `pyproject.toml` → `project.version` | PyPI |
| VS Code extension | `editors/vscode/package.json` → `version` | local `.vsix` (not the Marketplace) |

Confirm with the user which of the two they mean before bumping anything.

## Credentials — read this first

The PyPI token must come from the environment or the user at release time. **Never
write a token into a file, a settings allowlist, a commit, or a command you leave
behind in the transcript.** A previous release leaked a live token into a
permission allowlist; do not repeat it.

```bash
read -rs UV_PUBLISH_TOKEN && export UV_PUBLISH_TOKEN   # or source it from a secret store
```

## 1. Pre-flight

Release from `main`, after the PR for the last ticket has merged.

```bash
git checkout main && git pull
uv sync
uv run pytest
uv run ruff check .
uv run mypy .
```

All green, working tree clean. Then live-check the app against a sample — see the
`run-webapp` skill. A broken viewer is the failure mode users hit first.

## 2. Rebuild the committed frontend bundle

The wheel ships `src/c4studio/webapp/static/` so end users never need Node.
A stale bundle silently ships an old UI, so rebuild it for every Python release:

```bash
# node/npm exist ONLY in the conda env "pystructurizr"
conda run -n pystructurizr --no-capture-output npm install
conda run -n pystructurizr --no-capture-output npm run build
git status --short src/c4studio/webapp/static   # commit any change
```

## 3. Bump and build the Python package

Edit `project.version` in `pyproject.toml`, then:

```bash
rm -rf dist/
uv build
ls dist/                    # expect a .whl and a .tar.gz at the new version
```

Sanity-check the wheel actually contains the SPA before publishing:

```bash
python3 -c "import zipfile,glob; z=zipfile.ZipFile(glob.glob('dist/*.whl')[0]); \
print([n for n in z.namelist() if 'webapp/static' in n][:5])"
```

## 4. Publish

```bash
uv publish                  # reads UV_PUBLISH_TOKEN from the environment
```

Verify from the outside, not from the build output:

```bash
curl -s https://pypi.org/pypi/c4studio/json | \
  python3 -c "import json,sys; d=json.load(sys.stdin)['info']; print(d['name'], d['version'])"

uvx --isolated --from c4studio==<version> c4 --version
```

## 5. VS Code extension

```bash
conda run -n pystructurizr --no-capture-output npm --prefix editors/vscode install
conda run -n pystructurizr --no-capture-output npm --prefix editors/vscode run package
```

`npm run package` runs `typecheck` → `esbuild` → `vsce package`, producing
`editors/vscode/c4studio-vscode-<version>.vsix`. Install it locally to
verify:

```bash
"/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code" \
  --install-extension editors/vscode/c4studio-vscode-<version>.vsix
```

The extension resolves its Python backend automatically, bootstrapping via `uv`
when c4studio isn't already importable (PP-68) — check that path works from
a clean shell, not just from this repo's `.venv`.

## 6. Record it

- Commit the bump and the rebuilt bundle: `chore: release <version>`.
- Follow the normal flow — branch, push, PR, merge. **No local merges to `main`.**
- Tag the release commit on `main` once merged.
- Note the released version on the Jira ticket that drove the release.
