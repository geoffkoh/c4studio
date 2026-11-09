# Command line

Everything c4studio does is available from the `c4` command. Every command takes a `.dsl` or workspace `.json` file. The commands that report on a model exit non-zero on a problem, so any of them can gate a CI job.

```bash
c4 --help
c4 <command> --help
```

| I want to… | Command |
| --- | --- |
| Start a new workspace | `c4 new` |
| Edit a model and see it | `c4 webapp` |
| Know whether a file parses | `c4 check` |
| Hold a model to standards | `c4 lint` |
| See what a change did to the model | `c4 diff` |
| Know what a change to one element touches | `c4 impact` |
| Get SVG files | `c4 render` |
| Get a website | `c4 publish` |
| Get Mermaid | `c4 generate` |
| Get Structurizr JSON | `c4 export` |
| List views or perspectives, for scripts | `c4 list-views`, `c4 list-perspectives` |

## Lint rules

`c4 lint` asks whether a model is a *good* model, where `c4 check` only asks whether it parses. Every finding is a warning, because a model that breaks a house style still renders, so the exit code is what gates CI: 1 on any finding, or 0 with `--exit-zero`.

| Rule | What it reports |
| --- | --- |
| `orphan-element` | An element with no relationships. A system whose containers have relationships is not an orphan, because a view lifts those relationships to it. |
| `missing-description` | An element with no description. |
| `missing-technology` | A container or component with no technology. People and systems have none by design. |
| `duplicate-relationship` | The same relationship declared twice. |
| `unused-style` | A style whose tag nothing carries. It is invisible otherwise, because the legend only lists the styles in use. Tags that come from a theme are not reported. |
| `invalid-badge-colour` | A `c4studio.badge` value that is not a hex colour. |
| `naming-convention` | A name that does not match the pattern configured for its element type. Off until you configure a pattern. |

Configure the rules in `c4studio.lint.json` beside the workspace, or pass `--config`:

```json
{
  "ignore": ["missing-technology"],
  "naming": {"container": "^[A-Z]", "softwareSystem": "^[A-Z]"}
}
```

`ignore` skips rules and `select` runs only the rules listed. `naming` maps an element type to a regular expression its names must match. `--json` emits the same diagnostic shape the editors read, so findings land in the Studio's problems list and in the VS Code Problems panel.

## Diffs between revisions

`c4 diff` compares the model at two git revisions, and resolves `!include` fragments at the older revision too:

```bash
c4 diff architecture.dsl                          # working tree against HEAD
c4 diff architecture.dsl --from main --to HEAD    # two revisions
c4 diff architecture.dsl --from v1.0 --json       # for a script or PR comment
```

It reports elements and relationships added, removed and changed, and **the views a reviewer has to look at again**. A comment-only edit produces nothing. An element's identity comes from its DSL identifier, so renaming an element that has one is a change. Renaming an element *without* one reads as a removal plus an addition, and when the two share a name the pair is flagged as a **possible** rename rather than assumed: a diff that invents a rename can hide a deletion.

## Environment

| Variable | Used by | Purpose |
| --- | --- | --- |
| `C4STUDIO_NODE` | `render`, `publish` | Path to a `node` binary when it is not on `PATH`, for example under nvm or conda. |
| `ANTHROPIC_API_KEY` | `webapp --assistant` | The key for the optional assistant. Read when it is used, never stored. |

## Reference

Generated from the commands themselves, so it always matches the installed version.

{{cli-reference}}
