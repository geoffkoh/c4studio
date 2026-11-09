# Getting started

c4studio reads Structurizr DSL, draws the C4 diagrams it describes, and gives you a local Studio to edit the model in. This page takes you from nothing to a published architecture site in about five minutes.

## Install

c4studio is on PyPI as `c4studio`, and its command is `c4`. It needs **Python 3.13 or newer**.

```bash
pipx install c4studio        # recommended: an isolated install of the c4 command
pip install c4studio         # or into the current environment
```

To try it without installing anything, let `uvx` fetch it, and a suitable Python, on demand:

```bash
uvx --from c4studio c4 webapp my-architecture.dsl
```

| Needs | For |
| --- | --- |
| Python 3.13+ | Everything |
| Node.js 18+ | Only `c4 render` and `c4 publish`, which draw SVG with a renderer bundled in the package. There is no `npm install`. Set `C4STUDIO_NODE` if `node` is not on your `PATH`. |
| `ANTHROPIC_API_KEY` | Only the optional assistant, which is off by default. See [The Studio](studio.html#the-assistant-optional). |

Check that it worked:

```bash
c4 --version
```

## Start a workspace

`c4 new` writes a starter workspace that is valid DSL as it stands:

```bash
c4 new shop.dsl --template full-c4 --name "Acme Shop"
c4 new --list                 # what is available
```

| Template | What it shows |
| --- | --- |
| `minimal` | One person, one system, one view: the smallest thing that renders. The default. |
| `system-context` | A system in its context: who uses it, and what it depends on. |
| `full-c4` | Context, containers and components, drillable in the Studio. |
| `deployment` | Containers mapped onto the infrastructure that runs them. |

An existing file is never overwritten without `--force`.

## Open the Studio

```bash
c4 webapp shop.dsl
```

Your browser opens at `http://127.0.0.1:8090` with the diagram. Press `e`, or the **Source** button at the top right, to open the editor beside it. Change the DSL, press **⌘S** or **Ctrl+S**, and the diagram redraws. Point `c4 webapp` at a directory instead of a file to browse every workspace in it.

Everything stays on your machine. The Studio listens on `127.0.0.1` only, and has no accounts and no server component.

## Write a model

A Structurizr workspace has a **model**, which holds the people, systems, containers and relationships, and **views**, which pick what to draw. Here is a small, complete one:

```dsl
workspace "Acme Shop" "Online ordering for Acme" {

    model {
        customer = person "Customer" "Buys things from Acme"

        shop = softwareSystem "Acme Shop" "Lets customers browse and order" {
            web = container "Web App" "Product pages and checkout" "TypeScript, React"
            api = container "Orders API" "Takes and tracks orders" "Python, FastAPI"
            db  = container "Orders DB" "Orders and stock" "PostgreSQL" {
                tags "Database"
            }
        }

        payments = softwareSystem "Payment Provider" "Card payments" {
            tags "External"
        }

        customer -> web "Browses and orders using"
        web -> api "Calls" "JSON/HTTPS"
        api -> db "Reads and writes" "SQL"
        api -> payments "Takes payment through" "HTTPS"
    }

    views {
        systemContext shop Context "Acme Shop: System Context" {
            include *
            autoLayout lr
        }

        container shop Containers "Acme Shop: Containers" {
            include *
            autoLayout lr
            default
        }

        styles {
            element "Person" {
                shape Person
                background #08427b
                color #ffffff
            }
            element "Container" {
                background #438dd5
                color #ffffff
            }
            element "Database" {
                shape Cylinder
            }
            element "External" {
                background #999999
                color #ffffff
            }
        }
    }
}
```

The [DSL reference](dsl-reference.html) covers every construct. [Beyond Structurizr](extensions.html) lists what c4studio adds on top.

## Check it

Two commands answer two different questions:

```bash
c4 check shop.dsl    # does it parse? Exit 1 on errors
c4 lint shop.dsl     # is it a good model? Exit 1 on any finding
```

`c4 check` reports anything the parser skipped. c4studio never executes `!script` or `!plugin`, for example: it skips them and tells you so. `c4 lint` reports orphaned elements, missing descriptions and technologies, duplicate relationships and styles that match nothing. Both exit non-zero, so either can gate a CI job.

## Share it

```bash
c4 render shop.dsl -o diagrams/      # one standalone SVG per view
c4 publish shop.dsl -o site/         # a static site: a page per view, plus docs and ADRs
c4 export shop.dsl -o workspace.json # Structurizr JSON, for structurizr.com or Lite
```

`c4 publish` writes a self-contained site that works from `file://` or any static host. The [live example](example/index.html) on this site was made that way, from the model of c4studio itself.

## Where next

- [The Studio](studio.html): editing, arranging diagrams, perspectives, impact analysis and the keyboard shortcuts.
- [Command line](cli.html): every command and option.
- [CI and automation](ci.html): lint, diff, render and publish on every pull request.
- [VS Code](vscode.html): highlighting, problems and a preview in your editor.
