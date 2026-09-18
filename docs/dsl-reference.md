# Structurizr DSL, as c4studio speaks it

**Read this file and you can write DSL for c4studio without reading the
code.** It is the authoring reference: every construct the parser accepts,
what each one does here, the extensions that are ours, and the things that
are silently ignored.

Two companion documents, neither needed to write DSL: `dsl-support.md` maps
this parser against the upstream language reference keyword by keyword, and
`structurizr-parity.md` compares the *application* against Structurizr's.

Every DSL block below is parsed by the test suite
(`tests/test_docs_examples.py`), so nothing here can drift from the parser
without turning a test red. A block that begins with `workspace` is a whole
file; one that starts with `// in: model` or `// in: views` is a fragment,
and the test wraps it before parsing.

---

## 1. The shape of a file

```dsl
workspace "Name" "Description" {

    model {
        // people, software systems, containers, components,
        // relationships, deployment environments
    }

    views {
        // one block per diagram, then styles / themes / branding
    }
}
```

- `workspace`, `model` and `views` are the only top-level blocks. Both
  arguments to `workspace` are optional: `workspace {` parses.
- **Layout is not syntax.** Positions are not written in the DSL; they live
  in a gitignored `*.layout.json` sidecar beside the file (§11).

### Tokens and quoting

| Rule | Detail |
| --- | --- |
| Strings | Double quotes. A value containing a space **must** be quoted. |
| Bare words | Unquoted words work where a value has no spaces: `tags Database`, `shape Cylinder`, `autoLayout lr`. |
| Comments | `//` to end of line, `#` to end of line **only when nothing but whitespace precedes it** (mid-line, `#` starts a colour), and `/* … */` blocks. |
| Colours | `#rrggbb` or `#rgb`. |
| Statements | One per line. A newline ends a statement; there are no semicolons. |
| Keywords | Case-insensitive (`softwareSystem` = `softwaresystem`), and conventionally camelCase. |
| Identifiers | `alias = element …`, then referenced by that alias. Case-sensitive. Optional: an element with no alias simply cannot be referenced. |

### A minimal, complete file

```dsl
workspace "Bookshop" "Selling books online" {

    model {
        customer = person "Customer" "Buys books"
        shop = softwareSystem "Bookshop" "Sells books" {
            web = container "Web App" "Browsing and checkout" "TypeScript, React"
            api = container "API" "Catalogue and orders" "Python, FastAPI"
            db = container "Database" "Books, orders" "PostgreSQL" {
                tags "Datastore"
            }

            web -> api "Calls" "JSON/HTTPS"
            api -> db "Reads from and writes to" "SQL"
        }

        customer -> web "Browses and buys with"
    }

    views {
        systemContext shop "Context" {
            include *
            autoLayout lr
        }

        container shop "Containers" {
            include *
            autoLayout lr
        }

        styles {
            element "Person" {
                shape Person
                background #08427b
                color #ffffff
            }
            element "Datastore" {
                shape Cylinder
            }
        }
    }
}
```

---

## 2. Elements

Every element takes positional arguments, then an optional `{ … }` body.
**Positional order is fixed** — to skip one and set a later one, pass an
empty string.

| Element | Grammar |
| --- | --- |
| Person | `person <name> [description] [tags]` |
| Software system | `softwareSystem <name> [description] [tags]` |
| Container | `container <name> [description] [technology] [tags]` |
| Component | `component <name> [description] [technology] [tags]` |
| Custom element | `element <name> [metadata] [description] [tags]` |

Containers live inside a `softwareSystem` body; components inside a
`container` body. Nothing else nests.

```dsl
// in: model
u = person "User" "Someone with an account" "External"

s = softwareSystem "Platform" "Does the work" {
    api = container "API" "HTTP surface" "Python, FastAPI" "Critical" {
        handler = component "Request Handler" "Routes requests" "FastAPI"
    }
    // Skip description, set technology:
    worker = container "Worker" "" "Python"
}

// A custom element: free metadata instead of a C4 type. Parsed and
// exported, but not drawn in the built-in views.
note = element "Assumption" "Note" "Traffic doubles at peak"
```

### Element body vocabulary

Valid in the body of any element above (and of deployment nodes and
instances):

```dsl
// in: model
s = softwareSystem "Platform" {
    description "Set here instead of positionally"
    tags "Alpha" "Beta"            // repeatable; also "A,B" splits on commas
    url "https://wiki.example/platform"
    properties {
        "owner" "team-a"
        "repo" "github.com/acme/platform"
    }
    perspectives {
        "Security" "PII encrypted at rest" "High"
    }

    api = container "API" {
        // `technology` is valid on containers and components only; on a
        // software system it is skipped with `unexpected-token`.
        technology "Python, FastAPI"
    }
}
```

- `tags` accepts several arguments on one line, and splits comma-separated
  values, so `tags "A,B"` and `tags "A" "B"` are the same.
- `properties` keys and values are free text; `c4studio.*` keys are read by
  this application (§10).
- `perspectives` is covered in §9.

### Groups

`group <name> { … }` wraps elements in a named boundary. Groups nest by
writing a path, and appear in the diagram as a dashed boundary.

```dsl
// in: model
group "Customer facing" {
    portal = softwareSystem "Portal"
}

s = softwareSystem "Platform" {
    group "Core" {
        api = container "API"
    }
    group "Support/Batch" {          // nested: Support > Batch
        reports = container "Reports"
    }
}
```

> **Gotcha.** A group cannot be given an alias. `g = group "X" { … }` is
> skipped whole with an `unsupported-block` diagnostic, taking its contents
> with it. Write `group "X" { … }`.

### Enterprise

`enterprise <name> { … }` marks the elements inside as internal. It is
deprecated upstream but parses here.

```dsl
// in: model
enterprise "Acme" {
    internal = softwareSystem "Internal System"
}
external = softwareSystem "Partner API"
```

---

## 3. Relationships

```
<source> -> <destination> [description] [technology] [tags]
```

```dsl
// in: model
a = softwareSystem "A"
b = softwareSystem "B"

a -> b "Sends orders to" "JSON/HTTPS" "Async,Critical"

// Inside an element body, `this` is that element:
c = softwareSystem "C" {
    this -> a "Depends on"
}

// An alias lets a directive find it later:
r = a -> b "Also notifies"
```

A relationship may take a body, which accepts **exactly four** keywords —
`tags`, `url`, `properties`, `perspectives`:

```dsl
// in: model
a = softwareSystem "A"
b = softwareSystem "B"
a -> b "Publishes events to" "Kafka" {
    tags "Async"
    url "https://wiki.example/events"
    properties {
        "topic" "orders.v2"
    }
    perspectives {
        "Reliability" "At-least-once delivery" "Medium"
    }
}
```

> **Gotcha.** `description` and `technology` are **not** valid in that body
> — they are positional on the `->` line. Writing them there produces an
> `unknown-relationship-property` diagnostic and is ignored.

### Implied relationships

`!impliedRelationships true` (inside `model`) makes a relationship between
two nested elements imply one between their parents.

```dsl
// in: model
!impliedRelationships true
a = softwareSystem "A" {
    ac = container "AC"
}
b = softwareSystem "B" {
    bc = container "BC"
}
ac -> bc "Calls"
```

Even with it off, a view lifts a relationship to the nearest visible
ancestor, so a `container -> container` link still draws between systems on
a context view.

---

## 4. Deployment

```dsl
// in: model
s = softwareSystem "Platform" {
    api = container "API"
    db = container "Database"
}

deploymentEnvironment "Live" {

    // deploymentNode <name> [description] [technology] [tags] [instances]
    aws = deploymentNode "AWS" "Production account" "Amazon Web Services" "Cloud" {

        region = deploymentNode "eu-west-1" {

            // Infrastructure that is not a container instance:
            lb = infrastructureNode "Load Balancer" "Routes traffic" "ALB"

            ecs = deploymentNode "ECS" "" "Fargate" "" "3" {
                // An instance of a container declared in the model:
                apiInstance = containerInstance api {
                    healthCheck "liveness" "https://api.example/health" 60 5
                }
            }

            rds = deploymentNode "RDS" "" "PostgreSQL 16" {
                containerInstance db
            }
        }
    }

    // A whole system, rather than one container:
    partner = deploymentNode "Partner DC" {
        softwareSystemInstance s
    }
}
```

- **`instances` is the sixth positional argument and a string**, so ranges
  work: `"3"`, `"0..N"`, `"1..*"`.
- `deploymentGroup <name>` declares a group instances can be assigned to:
  `containerInstance api <groupAlias>`.
- `healthCheck <name> <url> [interval] [timeout]` is valid **only inside a
  container or software system instance** — as upstream, which gates it on
  instances too. On a `deploymentNode` or `infrastructureNode` it is
  skipped with `unexpected-token`.
- Health checks are recorded and exported. **Nothing here calls them** —
  see §9 for the one feature that does make HTTP requests.
- Relationships between deployment elements are written the same way;
  model-level relationships are replicated between the instances
  automatically.

---

## 5. Views

One block per diagram. The key is optional — c4studio generates one — but a
stable key is worth writing, because saved layout is keyed by it.

| View | Grammar |
| --- | --- |
| System landscape | `systemLandscape [key] [title] { … }` |
| System context | `systemContext <software system> [key] [title] { … }` |
| Container | `container <software system> [key] [title] { … }` |
| Component | `component <container> [key] [title] { … }` |
| Dynamic | `dynamic <scope\|*> [key] [title] { … }` |
| Deployment | `deployment <scope\|*> <environment> [key] [title] { … }` |
| Filtered | `filtered <baseKey> <include\|exclude> <tags> [key] [title]` |
| Custom | `custom [key] [title] { … }` |
| Image | `image <scope\|*> [key] { … }` |

```dsl
workspace "Views" {
    model {
        u = person "User"
        s = softwareSystem "Platform" {
            web = container "Web"
            api = container "API"
        }
        u -> web "Uses"
        web -> api "Calls"
    }

    views {
        systemLandscape "Landscape" "Everything at a glance" {
            include *
            autoLayout tb
        }

        systemContext s "Context" {
            include *
            description "How the platform sits in its world"
        }

        container s "Containers" {
            include *
            exclude u
            autoLayout lr 200 100      // direction, rank sep, node sep
            default                    // the view that opens first
        }

        dynamic s "Signup" "How a user signs up" {
            u -> web "Opens the signup page"
            web -> api "Creates the account"
        }

        deployment s "Live" "Production" {
            include *
        }

        filtered "Containers" exclude "Deprecated" "CurrentContainers"
    }
}
```

### Inside a view body

| Keyword | Meaning |
| --- | --- |
| `include <expr>` | Add elements or relationships. Repeatable. |
| `exclude <expr>` | Remove them. Repeatable. |
| `autoLayout [tb\|bt\|lr\|rl] [rankSep] [nodeSep]` | Direction and spacing. Honoured by the viewer and by `c4 render`. |
| `title` / `description` | Free text. `title` is drawn; `description` is parsed but not drawn. |
| `properties { … }` | Per-view properties, including `c4studio.autolayout.<group>` (§10). |
| `animation { … }` | Steps, each listing element identifiers. |
| `default` | Open this view first. |

Expressions accepted by `include` / `exclude`:

```dsl
// in: views
container s "Expressions" {
    include *                              // everything in scope
    include u                              // one identifier
    include "element.tag==Datastore"
    include "element.type==Container"
    include "element.parent==s"
    include "relationship.tag==Async"
    exclude "web->api"                     // a specific relationship
    exclude "element.tag==Deprecated"
}
```

A **dynamic view** lists ordered steps rather than includes. Each step is a
relationship, numbered in the order written; the viewer animates them and
`c4 render` draws them numbered.

`parallel { … }` gives every step inside it the **same** step number, so
they read as one moment in the sequence:

```dsl
// in: views
dynamic * "Signup" {
    u -> web "Opens the signup page"
    parallel {
        web -> api "Creates the account"
        web -> api "Sends the welcome email"
    }
    web -> api "Redirects to the dashboard"
}
```

That is steps 1, 2, 2, 3.

An **image view** carries a reference instead of a graph. The content is
parsed and exported; nothing here renders it.

```dsl
// in: views
image s "Sequence" {
    plantuml "https://example.com/sequence.puml"
}
```

`mermaid`, `kroki` and `image` are accepted in the same position.

---

## 6. Styles

Styles match on **tags**. Every element implicitly carries `Element` plus a
tag for its C4 type (`Person`, `Software System`, `Container`, `Component`,
`Infrastructure Node`, `Container Instance`, `Software System Instance`);
every relationship implicitly carries `Relationship`. Rules apply in
declaration order, and later matches win.

```dsl
// in: views
styles {
    element "Element" {
        // Applies to everything unless overridden below.
        metadata true
        description true
    }

    element "Datastore" {
        shape Cylinder
        background #6b48a8
        color #ffffff
        stroke #4a3276
        strokeWidth 2
        border Solid
        opacity 90
        icon "https://example.com/icon.png"
    }

    element "Deprecated" {
        border Dotted
        background #9e9e9e
        properties {
            "c4studio.legend" "Being retired this quarter"
        }
    }

    relationship "Async" {
        style Dotted
        color #7b1fa2
        thickness 3
    }

    element "Software System" {
        background #1168bd
        dark {
            background #0b3c6e
        }
    }
}
```

**Element style properties.** Painted: `background`, `color`, `shape`,
`icon`, `border`, `stroke`, `strokeWidth`, `opacity`, `metadata`,
`description`. Parsed, exported, but **not drawn**: `width`, `height`,
`fontSize`, `iconPosition` — each warns with `ignored-style-property`. An
unrecognised name warns with `unknown-style-property`.

**Relationship style properties.** Painted: `color`, `style`
(`Solid`/`Dashed`/`Dotted`), `thickness`, `opacity`, `metadata`,
`description`. Parsed but not drawn: `routing`, `position`, `width`,
`fontSize`.

**Shapes:** `Box`, `RoundedBox`, `Circle`, `Ellipse`, `Hexagon`, `Diamond`,
`Cylinder`, `Bucket`, `Pipe`, `Person`, `Robot`, `Folder`, `WebBrowser`,
`Window`, `Terminal`, `Shell`, `MobileDevicePortrait`,
`MobileDeviceLandscape`, `Component`.
**Borders:** `Solid`, `Dashed`, `Dotted`. **Line styles:** `Solid`,
`Dashed`, `Dotted`. **Routing:** `Direct`, `Curved`, `Orthogonal`.

> **Default relationship line:** dashed, 2px, `#707070`. So `style Dashed`
> distinguishes nothing — mark a special relationship with `style Solid`, a
> colour, or a thickness.

### The legend follows the styles

The legend is generated, never written: one row per element style actually
used, one per relationship style used, plus a `Boundary` row where the view
draws one. **The tag is the wording**, so `element "Datastore"` produces a
row saying "Datastore"; `c4studio.legend` overrides that with a sentence
(§10). A style no element uses produces no row.

---

## 7. Themes, branding, terminology

```dsl
// in: views
theme default
themes "https://static.structurizr.com/themes/amazon-web-services-2023.01.31/theme.json"

branding {
    logo "https://example.com/logo.png"
    font "Inter" "https://example.com/inter.css"
}

terminology {
    person "Actor"
    softwareSystem "Service"
    container "Module"
    component "Part"
    deploymentNode "Host"
    infrastructureNode "Appliance"
    relationship "Link"
}
```

Themes are fetched, cached, and merged — workspace styles win over theme
styles. Theme icons are inlined as `data:` URIs when rendering, so an
exported diagram has no external references.

> **Not yet applied:** `branding` and `terminology` are parsed and exported
> faithfully, but nothing in the viewer or the renderer reads them. Element
> metadata lines still say `[Container]`, and no logo is drawn.

---

## 8. Documentation and decisions

```dsl
workspace "Docs" {
    !docs docs
    !adrs adrs

    model {
        a = softwareSystem "A"
    }
    views {
        systemLandscape L {
            include *
        }
    }
}
```

- Paths are relative to the DSL file. `!docs` reads Markdown files in
  order; `!adrs` reads architecture decision records.
- Both need a **file** — parsing a string containing them raises
  `!docs '<path>' requires a file context`.
- `!decisions` (the upstream alias for `!adrs`) is **not** wired up.

Both are scoped to where they are written: at workspace level they
document the workspace, and inside an element body they document that
element.

```dsl
// in: model
s = softwareSystem "Platform" {
    !docs api-docs
    api = container "API"
}
```

---

## 9. Perspectives

A perspective is a named annotation on an element or a relationship. Two
forms, both upstream:

```dsl
// in: model
s = softwareSystem "Platform" {
    perspectives {
        // <name> <description> [value]
        "Security" "TLS 1.3 everywhere, mTLS internally" "High"

        // the block form, which also allows a url
        perspective "Ownership" {
            description "Owned by Team Payments"
            value "payments"
            url "https://wiki.example/teams/payments"
        }
    }
}
```

- The **value** is what the viewer badges the element with, and what the
  legend lists while that perspective is shown.
- A name may appear once per item; a duplicate is reported
  (`duplicate-perspective`) and skipped.
- Container and software system instances inherit the perspectives of what
  they instantiate.

**Showing one.** The Studio's diagram toolbar has a *Perspective* picker
when the model has any: choosing one fades everything without it and badges
what has it. `c4 render --perspective "Security"` draws the same thing into
an SVG.

**Colouring by value.** `Perspective:` style tags are resolved the way
upstream resolves them:

```dsl
// in: views
styles {
    element "Perspective:Security" {
        background #ffcc00
    }
    element "Perspective:Security[value==High]" {
        background #d32f2f
        color #ffffff
    }
    relationship "Perspective:Security[value==High]" {
        color #d32f2f
    }
}
```

**Dynamic perspectives.** A perspective carrying a `url` has its value read
from that URL rather than written in the DSL. This is **off by default**:
the server only fetches when started as `c4 webapp <file>
--dynamic-perspectives`, because the addresses come from the workspace
file. Only `http`/`https` are followed, at most 50 distinct URLs per
refresh, 10s timeout, refreshed every 60s. An empty body or a failed
request shows the HTTP status, so a badge reads `503` rather than going
stale. `c4 render` never fetches.

---

## 10. c4studio's own extensions

All of these are ordinary Structurizr `properties`, so a workspace using
them still parses in any other Structurizr tool, which ignores keys it does
not know. Nothing here changes the grammar.

| Property | Where | Effect |
| --- | --- | --- |
| `c4studio.autolayout` | On an element with children (a system or container drawn as a boundary) | Lays that boundary's children out in its own direction: `tb`, `bt`, `lr`, `rl`. |
| `c4studio.autolayout.<group name>` | In a **view's** `properties` | The same, for a group — groups have no properties of their own, so the hint lives on the view. |
| `c4studio.legend` | In a style's `properties` | Replaces that style's legend row label with a sentence. |

```dsl
workspace "Extensions" {
    model {
        s = softwareSystem "Platform" {
            properties {
                "c4studio.autolayout" "lr"
            }
            group "Backend" {
                api = container "API"
                worker = container "Worker"
            }
            web = container "Web"
        }
    }

    views {
        container s "Containers" {
            include *
            properties {
                "c4studio.autolayout.Backend" "tb"
            }
        }

        styles {
            element "Element" {
                properties {
                    "c4studio.legend" "Everything on this diagram"
                }
            }
        }
    }
}
```

---

## 11. What is *not* in the DSL

**Layout.** Positions, sizes, edge waypoints, dragged labels, collapsed
groups and a moved title/legend live in `<workspace>.layout.json` beside
the file. It is per-user UI state, gitignored, and written by the Studio
when you arrange a diagram. `c4 render` honours it, so a rendered SVG
matches what you arranged; `c4 render --no-layout` ignores it, which is
what makes output identical on a machine that has no sidecar.

**Notes and captions.** Structurizr has no note, annotation or caption
keyword. The nearest options are a view `title`, an element `description`,
a custom `element` used as a callout (parsed but not drawn here), or
`!docs` prose.

---

## 12. Constructs that are accepted and ignored

Nothing below stops a parse. Each is skipped whole, recorded in
`workspace.diagnostics`, and printed to stderr by `c4 check`.

| Construct | What happens |
| --- | --- |
| `!script`, `!plugin`, `!components` | Skipped with `unsupported-directive` — never executed. |
| `!const`, `!var`, `!decisions`, any unknown `!directive` | Skipped with `unsupported-directive`. |
| `archetypes { … }` | Skipped with `unsupported-block`. |
| `!identifiers hierarchical` | Accepted, but identifiers are always resolved flat. |
| `paperSize <size>` | Stored and exported; nothing here draws to a page size. An unrecognised value warns with `unknown-paper-size`. |
| `branding`, `terminology` | Parsed and exported, but nothing reads them (§7). |
| Any unrecognised block | Skipped brace-balanced with `unsupported-block`, so its contents cannot leak into the enclosing scope. |

### Diagnostic codes

`c4 check <file>` prints these; the API returns them; every one carries a
file, line and column.

| Code | Meaning |
| --- | --- |
| `unsupported-directive` | A `!directive` this parser does not implement. |
| `unsupported-block` | An unrecognised block, skipped whole. |
| `unexpected-token` / `unexpected-keyword` | A keyword in a place it is not valid. |
| `unexpected-element` | A child element type its parent cannot hold. |
| `missing-name` / `missing-destination` | A required argument was absent. |
| `unclosed-block` | A `{` with no matching `}`. |
| `unknown-style-property` / `ignored-style-property` | Unknown, or known but not drawn. |
| `unknown-relationship-property` | Something other than tags/url/properties/perspectives in a relationship body. |
| `unknown-relationship-alias` / `no-relationships-matched` | A `!relationship(s)` target that resolved to nothing. |
| `invalid-perspective` / `duplicate-perspective` | A malformed or repeated perspective. |
| `unknown-theme` | A theme that could not be fetched. |

---

## 13. Splitting a workspace across files

```dsl
workspace "Split" {
    model {
        !include model/people.dsl
        !include model/systems.dsl
    }
    views {
        !include views/context.dsl
    }
}
```

Paths are relative to the including file, and nest. Diagnostics are
reported against the fragment that contains the problem, not the file that
included it. `samples/c4studio/` is a worked example.

---

## 14. Working with the result

| Command | What it does |
| --- | --- |
| `c4 check <file>` | Parse and print problems. Exit code is non-zero on errors. |
| `c4 webapp <file-or-dir>` | The Studio on `127.0.0.1:8090`; add `--viewer` for read-only, `--dynamic-perspectives` to allow perspective URL fetches. |
| `c4 render <file> -o out/` | Standalone SVGs. `--view <key>`, `--perspective <name>`, `--no-layout`, `--no-title`, `--no-legend`. Needs Node. |
| `c4 generate <file>` | Mermaid C4 diagrams. |
| `c4 export <file>` | Structurizr workspace JSON, which round-trips with structurizr.com and Lite. |
| `c4 list-views <file> --json` | The views, default first — the shape `/api/views` returns. |
| `c4 list-perspectives <file> --json` | Every perspective name in the model, sorted — what `--perspective` accepts. |
| `c4 new <file> --template …` | A starter workspace: `minimal`, `system-context`, `full-c4`, `deployment`. |

---

## 15. Checklist before you hand over a file

1. `c4 check` is clean — diagnostics mean something was **skipped**, and a
   skipped block is usually not what was intended.
2. Every view has a stable `key`, because layout is saved against it.
3. Tags used by styles exist on elements, and styles exist for the tags
   used — an unused style is invisible, and an unstyled tag is silent.
4. `description` and `technology` on relationships are positional, not body
   keywords.
5. Groups are unaliased.
6. `healthCheck` sits inside an instance.
7. One view is marked `default`, so the Studio opens on something useful.
