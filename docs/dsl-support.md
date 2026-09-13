# Structurizr DSL: language support

Which parts of the Structurizr DSL c4studio understands, keyword by
keyword.

**Reference:** the published language reference at
<https://docs.structurizr.com/dsl/language>, which lists 73 keywords. Where
that page and the Java source disagree, `../structurizr/structurizr-dsl/`
settles it — each parser there declares a literal `GRAMMAR` string.

**How the support column was established:** by parsing a minimal snippet
for each keyword and inspecting the resulting model, not by reading the
parser. Verified August 2026 against the parser in
`src/c4studio/parser/dsl.py`; re-probed September 2026, which corrected
`instanceOf` and caught the `deploymentEnvironment` alias leak, since
fixed (PP-138).

**Living coverage:** `samples/logistics_network.dsl` exercises most ✅
keywords in one workspace — groups, custom elements, `this ->`,
relationship bodies, the bulk `!…` directives, deployment groups, health
checks, view animation, branding, terminology. Every keyword it uses is
pinned to its model effect by `tests/test_samples/test_logistics_network.py`,
so this table cannot silently drift for those rows.

| | Meaning |
| --- | --- |
| ✅ | Parsed, and it changes the model as documented |
| ◐ | Partially supported — see the note |
| ⚠️ | **Parses silently and does nothing.** No warning, no effect. These are defects, not decisions |
| ⛔ | Skipped, and recorded as a diagnostic you can see |
| 🚫 | Deliberately unsupported and staying that way |

**Comments:** `//`, `/* … */` and full-line `#` are all supported. A `#`
only starts a comment when nothing but whitespace precedes it on the line
— mid-line it is a hex colour (`background #1a2b3c`), the same rule as
structurizr-java (`^\s*?(//|#)`).

Anything marked ⛔ follows the parser's fail-soft contract: the construct
and any `{ … }` body are skipped whole, never half-applied, and recorded in
`Workspace.diagnostics` (and `parse_warnings`), which `c4 check`
prints. A skipped construct never consumes its enclosing scope.

## Workspace

| Keyword | Support | Notes |
| --- | --- | --- |
| `workspace [name] [description]` | ✅ | |
| `workspace extends <file\|url>` | ⛔ | Parse error rather than a skip — the whole file fails. Workspace composition is a roadmap item (Phase 4) |
| `!identifiers hierarchical\|flat` | ◐ | Accepted, but identifier resolution is always flat; the requested mode is ignored |
| `!impliedRelationships <true\|false>` | ✅ | |
| `properties { … }` (workspace level) | ⚠️ | Parses, stored nowhere. Element- and view-level `properties` do work |
| `configuration { … }` | ✅ | `scope`, `visibility`, `users` all parse |
| `!include <file\|directory>` | ✅ | Works from a file (`parse_dsl_file`); a string parsed with no file context cannot resolve relative paths |
| `!docs <path>` | ✅ | Needs a file context; raises a clear error when parsed from a string |
| `!adrs <path>` | ✅ | Same |
| `!decisions <path>` | ⛔ | The upstream alias for `!adrs`; not wired up |
| `!script` | 🚫 | **Never executed.** Skipped whole, with a diagnostic. Executing arbitrary Groovy/Kotlin/Ruby from a parsed file is not something this tool will do |
| `!plugin` | 🚫 | Same reasoning — arbitrary JVM classes |
| `!components` | ⛔ | Component discovery by classpath scanning; a JVM feature with no equivalent here |

## Model

| Keyword | Support | Notes |
| --- | --- | --- |
| `model { … }` | ✅ | |
| `group "<name>" { … }` | ✅ | Model level, element bodies, and nested; renders as a boundary |
| `person <name> [description] [tags]` | ✅ | |
| `softwareSystem <name> [description] [tags]` | ✅ | |
| `container <name> [description] [technology] [tags]` | ✅ | |
| `component <name> [description] [technology] [tags]` | ✅ | |
| `element <name> [metadata] [description] [tags]` | ✅ | Custom elements parse and round-trip; not shown in the built-in views |
| `<identifier> -> <identifier> [description] [technology] [tags]` | ✅ | Including `this ->` and implicit-source forms |
| `<identifier> -/> <identifier>` | ⛔ | Relationship removal is not implemented |
| `archetypes { … }` | ⛔ | A newer upstream feature; the whole block is skipped |
| `deploymentEnvironment <name> { … }` | ✅ | Both forms. The aliased form `prod = deploymentEnvironment "Production" { … }` used to be rejected *and* leak its body into model scope; fixed in PP-138, and the alias now resolves in a deployment view's environment slot the way upstream resolves it |
| `deploymentGroup <name>` | ✅ | Declarations and instance membership |
| `deploymentNode <name> […] [instances] { … }` | ✅ | Positional `instances` supported, including ranges like `"0..N"` |
| `infrastructureNode <name> […]` | ✅ | |
| `softwareSystemInstance <identifier> […]` | ✅ | |
| `containerInstance <identifier> […]` | ✅ | |
| `instanceOf <identifier> […]` | ⛔ | Skipped with a diagnostic (`'instanceOf' is not valid inside deploymentnode`). Upstream sugar that picks software-system vs container instance from the referenced element; use `softwareSystemInstance` / `containerInstance` explicitly |
| `healthCheck <name> <url> […]` | ✅ | Parsed and round-tripped; not evaluated — nothing here makes HTTP calls |

## Element and relationship bodies

| Keyword | Support | Notes |
| --- | --- | --- |
| `tags "<a,b>"` | ✅ | |
| `description "<text>"` | ✅ | |
| `technology "<text>"` | ✅ | |
| `url "<url>"` | ✅ | |
| `properties { … }` | ✅ | |
| `perspectives { … }` | ✅ | Parsed and round-tripped; not rendered |
| `instances "<n>"` as a body keyword | ⛔ | Only the positional form on `deploymentNode` is understood |
| `tag` (archetype-related) | ◐ | Accepted without error; no archetype support behind it |

## Bulk operations and references

| Keyword | Support | Notes |
| --- | --- | --- |
| `!element <identifier> { … }` | ✅ | |
| `!elements <expression> { … }` | ✅ | Applies the body to every matching element |
| `!relationship <alias> { … }` | ⚠️ | Parses silently and changes nothing |
| `!relationships <expression> { … }` | ◐ | Works with tag and property expressions (`relationship.tag==X`); the wildcard forms `*` and `"*->*"` match nothing, silently |
| `!extend <identifier> { … }` | ⛔ | |
| `!ref <identifier> { … }` | ⛔ | |

## Views

| Keyword | Support | Notes |
| --- | --- | --- |
| `systemLandscape [key] { … }` | ✅ | Enterprise boundary included |
| `systemContext <system> [key] { … }` | ✅ | |
| `container <system> [key] { … }` | ✅ | |
| `component <container> [key] { … }` | ✅ | |
| `dynamic <scope> [key] { … }` | ✅ | Ordered steps, animated in the viewer |
| `deployment <scope> <environment> [key] { … }` | ✅ | |
| `custom [key] [title] { … }` | ◐ | Parses and round-trips; **not rendered** in the viewer or by `render` |
| `image <scope> [key] { … }` | ◐ | Same |
| `filtered <baseKey> <include\|exclude> <tags>` | ✅ | |
| `include` / `exclude` | ✅ | Wildcards, identifiers, relationship expressions and `element.tag==` predicates |
| `autoLayout [rankDirection] [rankSep] [nodeSep]` | ✅ | Direction *and* separations are honoured by the viewer and by `render` |
| `default` | ✅ | The default view opens first |
| `animation { … }` | ✅ | |
| `title` / `description` / `properties` | ✅ | |

## Styles, themes and terminology

| Keyword | Support | Notes |
| --- | --- | --- |
| `styles { element … }` | ◐ | Every property parses. Painted: `background`, `color`, `shape`, `icon`, `border`, `stroke`, `strokeWidth`, `opacity`, `metadata`, `description`. Parsed and exported but **not** painted: `width`, `height`, `fontSize`, `iconPosition` — each warns (`ignored-style-property`), as does an unrecognised property name (`unknown-style-property`). `height` matters less than it looks: a node is already sized to fit its own text (see below) |
| `styles { relationship … }` | ◐ | Every property parses and exports. Painted: `color`, `style` / `dashed` (solid/dashed/dotted; `style` wins when both are set), `thickness`, `opacity`, `metadata`, `description`. Parsed and exported but **not** painted: `routing`, `jump`, `position`, `width`, `fontSize`. Unstyled relationships render dashed, 2px, `#444444` — upstream Structurizr's default — so mark special edges with `style dotted`/`style solid` or a colour, not `dashed true` |
| `light { … }` / `dark { … }` | ◐ | Colour-scheme variants parse; the viewer renders one scheme |
| `theme <url\|default>` | ✅ | Fetched, cached and merged; workspace styles win |
| `themes <url> <url…>` | ✅ | |
| `branding { … }` | ✅ | Logo and font, including the font URL |
| `terminology { … }` | ✅ | |

### How much text a node shows

Nodes are a fixed 200px wide and **as tall as their own text needs**, so a
wordy element grows downward rather than clipping. The measurement lives in
`packages/diagram-core/src/nodeMetrics.ts` and is shared by the layout
engine, the SVG emitter and the web app's CSS clamps — one number, so the
box that is drawn is the box the layout reserved.

Each field still has a ceiling, past which text is ellipsised and shown in
full on hover: **4 lines** for the name, **2** for the `[Kind: technology]`
line, **4** for the description. Those are generous enough that no node in
any bundled sample clips, but a diagram is a poor place for prose — put the
long version in `!docs` and keep the description to a sentence.

Width is deliberately not part of this: equal-width boxes are most of what
makes ranks scannable. Upstream's `width`/`height` element-style properties
remain unsupported.

### Per-boundary layout hints (`c4studio.autolayout`)

`autoLayout` sets one rank direction for the whole view. To lay a single
boundary's interior out differently, c4studio reads a **property** — not a
DSL extension, so the file stays valid for every Structurizr tool, which
simply carries the property through untouched:

```
softwareSystem "Platform" {
    properties {
        "c4studio.autolayout" "lr"    // this boundary's children flow left-to-right
    }
    ...
}

views {
    container platform Containers {
        include *
        autoLayout tb                  // the view itself stays top-to-bottom
        properties {
            // groups have no properties of their own, so a group
            // boundary's hint is keyed by group name on the view
            "c4studio.autolayout.Core Services" "lr"
        }
    }
}
```

Values are `tb`, `bt`, `lr`, `rl` (case-insensitive); anything else is
ignored. The hint applies wherever that element renders as a boundary — the
view's own scope, an element expanded in place, a deployment node — and is
purely local: the boundary still sits in its parent's flow. It steers
auto-layout only; positions saved in a layout sidecar still win.
`samples/logistics_network.dsl` shows both forms.

### Marking elements as new, existing or deprecated

There is no lifecycle keyword in the DSL. The only styling axis is the
**tag**: tag the elements, style the tag, and the legend follows — c4studio
derives one row per visually distinct combination of colour, shape and
border, labelled by the most specific style tag that matched.

```
container "Fraud Check" "" "Go" { tags "New" }
...
styles {
    element "Existing"   { background #4b7bb5 }
    element "New"        { background #2e7d32 border dashed strokeWidth 3 }
    element "Deprecated" { background #90a4ae border dotted opacity 55 }
}
```

Three things that are easy to get wrong:

- **Tag the unchanged elements too.** An untagged element falls back to its
  C4 kind, so you get "New" vs "Container" rather than "New" vs "Existing".
- **The last matching rule names the row.** Every matching rule contributes
  its own properties, but the legend label comes from the one declared last.
  Put the rule you want as the label after the others.
- **The swatch carries colour, shape and border — not opacity.** Two greys
  separated only by a fade are one row apart in the diagram and
  indistinguishable in the legend; give one of them a border.

`samples/delta_release.dsl` is a complete worked example, including tag
composition and the ordering rule.

## Configuration

| Keyword | Support | Notes |
| --- | --- | --- |
| `scope` | ✅ | |
| `visibility` | ✅ | |
| `users { … }` | ✅ | Parsed and round-tripped. c4studio is local-first: there is no auth to apply it to |

## The gaps worth knowing about

Three constructs **parse silently and do nothing** — no warning, no effect.
They are the worst kind of gap, because nothing tells you:

- workspace-level `properties`
- `!relationship <alias> { … }`
- `!relationships` with wildcard expressions

And one construct half-announces itself: an aliased
`prod = deploymentEnvironment … { … }` produces a diagnostic for the
statement, but its body still leaks into the enclosing `model` scope (see
the Model table above).

Everything else that is unsupported announces itself: `c4 check`
lists it, and the webapp surfaces it. If a construct you rely on is missing
here and does *not* appear in `check` output, that is a bug worth filing.

## What will not be supported

`!script` and `!plugin` execute arbitrary code — Groovy, Kotlin, Ruby or a
JVM class — named by the file being parsed. c4studio parses untrusted
DSL in a CLI, a web app and (potentially) a browser, so it skips both and
says so. This is a deliberate boundary, not a missing feature.
