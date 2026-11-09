# Beyond Structurizr

c4studio reads the standard Structurizr DSL. This page covers what it adds on top, and the few places where it behaves differently from the Java Structurizr tools.

**Nothing here changes the grammar.** Every addition is either an ordinary Structurizr `properties` entry, which other tools ignore, or a file beside the workspace. A workspace that uses them still opens in structurizr.com, Structurizr Lite or the Structurizr CLI.

## At a glance

| Addition | Kind | What it does |
| --- | --- | --- |
| `c4studio.autolayout` | Element property | Lays out the children of a boundary in their own direction. |
| `c4studio.autolayout.<group>` | View property | The same, for a group inside a view. |
| `c4studio.legend` | Style property | Replaces the legend label for elements or relationships with that style. |
| `c4studio.badge` | Element style property | Colours the properties badge for elements with that tag. |
| Theme files | `theme` with a path | Inlined at parse time, so they work offline. Icons become `data:` URIs. |
| `c4studio.lint.json` | File beside the workspace | Your model standards, read by `c4 lint`. |
| `<workspace>.layout.json` | File beside the workspace | Your arrangement of each view: per-user, never committed. |
| Dynamic perspectives | Behaviour | A perspective's `url` supplies its value live, when you allow it. |

## Layout direction per boundary: `c4studio.autolayout`

A view's `autoLayout` sets one direction for the whole diagram. A software system or container drawn as a boundary can set its own direction for its children with this property: `tb` (top to bottom), `bt`, `lr` (left to right) or `rl`.

Groups have no properties of their own, so a group's direction goes in the **view's** `properties`, keyed by the group's name.

```dsl
workspace "Layout hints" {
    model {
        user = person "User"
        shop = softwareSystem "Shop" {
            properties {
                "c4studio.autolayout" "lr"
            }
            web = container "Web" "Storefront" "React"
            group "Backend" {
                api = container "API" "Orders" "Python"
                worker = container "Worker" "Fulfilment" "Python"
                db = container "Database" "Orders and stock" "PostgreSQL"
            }
        }
        user -> web "Shops using"
        web -> api "Calls"
        api -> db "Reads and writes"
        worker -> db "Polls"
    }
    views {
        container shop Containers {
            include *
            autoLayout tb
            properties {
                "c4studio.autolayout.Backend" "tb"
            }
        }
    }
}
```

The diagram as a whole runs top to bottom, the Shop boundary arranges its children left to right, and the Backend group stacks its three containers vertically.

## Legend labels: `c4studio.legend`

Every diagram c4studio draws carries a legend of the styles it actually uses. By default a row is labelled with the style's tag. `c4studio.legend` replaces that label with a sentence, which helps when a tag such as `Legacy` or `PCI` means something specific to your organisation.

```dsl
// in: views
styles {
    element "Container" {
        background #438dd5
        color #ffffff
        properties {
            "c4studio.legend" "Something we build and run"
        }
    }
    relationship "Relationship" {
        properties {
            "c4studio.legend" "Synchronous call"
        }
    }
}
```

## Badge colour: `c4studio.badge`

In the Studio, an element that has `properties` shows a small ⓘ badge in its corner. Click it to open the element's details. The badge takes the element's text colour by default. `c4studio.badge` on an **element style** sets it per tag, as `#rgb` or `#rrggbb`. The "i" is drawn black or white, whichever is readable on the colour you choose.

```dsl
// in: views
styles {
    element "Database" {
        shape Cylinder
        properties {
            "c4studio.badge" "#ffcc00"
        }
    }
}
```

A value that is not a hex colour is ignored on the diagram, and `c4 lint` reports it as `invalid-badge-colour`.

## Theme files that work offline

Structurizr themes are usually URLs. c4studio fetches and caches those, and also accepts a **path to a theme file**, resolved against the workspace file:

```dsl
// in: views
theme "themes/corporate.json"
```

A theme file is inlined when the workspace is parsed, and every relative `icon` in it becomes a `data:` URI. Icon paths are relative to the *theme* file, so a theme folder can be copied around whole. Nothing is fetched, so a file theme works offline in the Studio, `c4 render`, `c4 publish` and the VS Code preview.

As with fetched themes, the workspace's own styles always win, whatever order the lines are in. A missing or malformed theme file is a warning (`theme-not-found` or `invalid-theme`) and the diagram renders without it. `c4 lint` does not report a theme's unused tags, because a theme is a library.

## Model standards: `c4studio.lint.json`

`c4 lint` reads this file from beside the workspace, if it is there:

```json
{
  "ignore": ["missing-technology"],
  "select": [],
  "naming": {
    "softwareSystem": "^[A-Z]",
    "container": "^[A-Z][A-Za-z ]+$"
  }
}
```

| Key | Meaning |
| --- | --- |
| `ignore` | Rule codes to skip. |
| `select` | When not empty, run only these rules. |
| `naming` | Element type to a regular expression its names must match. The `naming-convention` rule is off until this has an entry. |

The rules are listed in [Lint rules](cli.html#lint-rules).

## Layout files: `<workspace>.layout.json`

The DSL describes the model. It does not describe where you dragged each box. When you arrange a view in the Studio, the positions go in a sidecar file beside the workspace, `shop.layout.json` for `shop.dsl`, together with each view's line style, line routes, label offsets, collapsed and expanded elements, moved titles and legends, and named layouts.

- The file is **per-user UI state**, so add `*.layout.json` to `.gitignore`.
- `c4 render`, `c4 publish` and the VS Code preview honour it, so your exports match what you arranged. `--no-layout` ignores it, which gives the same output on any machine.
- It is keyed by view key, so give every view an explicit key.

Structurizr keeps layout inside workspace JSON instead. c4studio keeps your DSL free of coordinates, which keeps diffs readable.

A workspace `.json` file that Structurizr has laid out is drawn the way Structurizr drew it, in the Studio, `c4 render` and `c4 publish`. That covers element positions, line bend points, and box sizes, which are 450×300 unless an element style sets `width` or `height`. Boundaries are fitted around their contents, because Structurizr stores no position for them. A view with `automaticLayout`, or with every element at 0,0, which is what Structurizr writes for a view nobody arranged, is laid out afresh, as Structurizr itself does. A sidecar beside the JSON still wins over the layout inside it. `c4 export` writes element positions and bend points back out.

## Dynamic perspectives

A [perspective](dsl-reference.html#9-perspectives) can carry a `url`. In c4studio, a perspective with a `url` has its value **read from that URL**, so a badge can show live data such as an on-call team or a security rating.

```dsl
// in: model
api = softwareSystem "Payments API" {
    perspectives {
        perspective "On call" {
            description "The team paged for this service"
            url "https://status.example.com/oncall/payments"
        }
    }
}
```

This is **off by default**. Start the Studio with `c4 webapp <path> --dynamic-perspectives` to allow it. Only `http` and `https` are followed, at most 50 distinct URLs per refresh, with a 10-second timeout, refreshed every 60 seconds. A failed request shows its HTTP status, so a badge reads `503` rather than going stale. `c4 render` and `c4 publish` never fetch.

## Where c4studio differs from Structurizr

| Construct | Structurizr | c4studio |
| --- | --- | --- |
| `!script`, `!plugin`, `!components` | Executed | **Never executed.** Skipped whole and reported as `unsupported-directive`. |
| Unknown blocks and directives | A parse error | Skipped, brace-balanced, and reported, so the rest of the file still loads. |
| `workspace extends` | Local file or URL; an argument left out resets the value | **Local DSL file only.** An argument left out keeps the base's value. |
| `!identifiers hierarchical` | Hierarchical identifiers | Accepted, but identifiers always resolve flat. |
| `archetypes { … }` | Supported | Skipped with `unsupported-block`. |
| `!decisions` | An alias for `!adrs` | Not supported; use `!adrs`. |
| `branding`, `terminology` | Applied to diagrams | Parsed and exported, but not drawn. |
| `routing Orthogonal` | Orthogonal lines | Drawn with c4studio's own step router. `Direct` and `Curved` are not painted. |
| Layout | Stored in workspace JSON | Stored in a per-user `.layout.json` sidecar. A layout inside workspace JSON is drawn too. |

Every skipped construct is recorded as a diagnostic with a file, line and column. `c4 check` prints them, the Studio and VS Code show them as problems, and the rest of the model still renders. The full list of codes is in [Diagnostic codes](dsl-reference.html#diagnostic-codes), and [Keyword coverage](dsl-support.html) maps every keyword in the Structurizr language reference to what c4studio does with it.
