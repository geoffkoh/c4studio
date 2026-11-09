# CI and automation

An architecture model is only useful while it is true. Checking it on every pull request is how it stays true. Everything below runs on a stock GitHub-hosted runner.

## Lint the model on every pull request

`c4 check` fails on DSL that does not parse. `c4 lint` fails on a model that breaks your standards. Neither needs Node.

```yaml
name: Architecture

on:
  pull_request:
    paths: ["architecture/**"]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v7
        with:
          python-version: "3.13"
      - run: pip install c4studio
      - run: c4 check architecture/workspace.dsl
      - run: c4 lint architecture/workspace.dsl
```

c4studio needs Python 3.13, newer than the runners' default, hence `setup-python`. On a model nobody has linted before, start with `c4 lint --exit-zero` to see the findings without failing the build. Then add the rules you do not want to `ignore` in `c4studio.lint.json` (see [Lint rules](cli.html#lint-rules)).

## Render diagrams with the GitHub Action

The repository is itself a GitHub Action. It installs c4studio, checks the workspace, and renders every view as SVG:

```yaml
name: Diagrams

on: [push, pull_request]

jobs:
  render:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: geoffkoh/c4studio@v0.4.0
        id: diagrams
        with:
          workspace: docs/architecture.dsl
      - uses: actions/upload-artifact@v7
        with:
          name: diagrams
          path: ${{ steps.diagrams.outputs.diagrams-path }}
```

| Input | Default | What it does |
| --- | --- | --- |
| `workspace` | *required* | The `.dsl` or `.json` file to render. |
| `output` | `diagrams` | Directory for the SVG files, one per view. |
| `view` | *all views* | Render only this view key. |
| `mode` | `render` | `render` writes the files. `commit` pushes them back when they changed. `comment` comments on the pull request with the diagrams that changed. |
| `version` | `c4studio` | The pip requirement to install, such as `c4studio==0.4.0`. `local` installs the checked-out repository. |
| `python-version` | `3.13` | Python to set up first. An empty string skips the step. |
| `commit-message` | `chore: update rendered diagrams` | Commit message for `mode: commit`. |
| `token` | `github.token` | Token for `mode: comment`. Needs `pull-requests: write`. |

The action has two outputs: `diagrams-path` and `changed` (`true` when the rendered files differ from what is committed). A parse error fails the job with diagnostics, not a traceback. Rendering is deterministic, so `mode: commit` produces no commit when the model has not changed.

## Post the model diff on every pull request

`c4 diff` tells a reviewer what the change did to the model, and which views to look at again. This workflow posts the result as a comment and updates that same comment on each push:

```yaml
name: Architecture diff

on:
  pull_request:
    paths: ["architecture/**"]

permissions:
  contents: read
  pull-requests: write

jobs:
  diff:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
        with:
          fetch-depth: 0   # c4 diff reads the base revision from git history
      - uses: actions/setup-python@v7
        with:
          python-version: "3.13"
      - run: pip install c4studio   # no Node needed: diff compares models
      - name: Diff the model against the target branch
        env:
          BASE: origin/${{ github.base_ref }}
        run: |
          {
            echo "### Architecture changes"
            echo
            echo '```text'
            c4 diff architecture/workspace.dsl --from "$BASE" --to HEAD 2>&1 \
              || echo "c4 diff could not compare these revisions (exit $?)"
            echo '```'
          } > architecture-diff.md
          cat architecture-diff.md >> "$GITHUB_STEP_SUMMARY"
      - name: Comment on the pull request
        env:
          GH_TOKEN: ${{ github.token }}
          PR: ${{ github.event.pull_request.number }}
        run: gh pr comment "$PR" --body-file architecture-diff.md --edit-last --create-if-none
```

A workspace that the base branch does not have yet cannot be compared, so the comment says so instead of failing the job. The job summary works even for pull requests from forks, which get a read-only token and cannot comment.

## Publish the model to GitHub Pages

`c4 publish` writes a static site: one page per view, so a link to a diagram survives being pasted into a ticket, with the `!docs` prose and ADRs beside them. Publish it on every merge:

```yaml
name: Architecture site

on:
  push:
    branches: [main]

permissions:
  contents: read
  pages: write
  id-token: write

jobs:
  publish:
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-node@v7   # c4 publish draws SVG with Node
        with:
          node-version: 20
      - uses: actions/setup-python@v7
        with:
          python-version: "3.13"
      - run: pip install c4studio
      - run: c4 publish architecture/workspace.dsl -o site/ --no-layout
      - uses: actions/upload-pages-artifact@v5
        with:
          path: site/
      - id: deployment
        uses: actions/deploy-pages@v5
```

In the repository's **Settings › Pages**, set **Source** to **GitHub Actions** once. The [live example](example/index.html) on this site is published this way.

## Other places to use the CLI

- **Mermaid in a README or wiki.** `c4 generate -f flowchart -o docs/diagrams` writes one `.mmd` file per view. The flowchart target renders more reliably on GitHub than Mermaid's experimental C4 diagram types.
- **Structurizr cloud or Lite.** `c4 export -o workspace.json` writes workspace JSON that round-trips.
- **Change advisory.** `c4 impact architecture.dsl paymentsApi --json` lists everything that depends on an element, everything it depends on, and the views that draw it.
