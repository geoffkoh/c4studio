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
`src/c4studio/parser/dsl.py`.

| | Meaning |
| --- | --- |
| ✅ | Parsed, and it changes the model as documented |
| ◐ | Partially supported — see the note |
| ⚠️ | **Parses silently and does nothing.** No warning, no effect. These are defects, not decisions |
| ⛔ | Skipped, and recorded as a diagnostic you can see |
| 🚫 | Deliberately unsupported and staying that way |

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
| `deploymentEnvironment <name> { … }` | ✅ | |
| `deploymentGroup <name>` | ✅ | Declarations and instance membership |
| `deploymentNode <name> […] [instances] { … }` | ✅ | Positional `instances` supported, including ranges like `"0..N"` |
| `infrastructureNode <name> […]` | ✅ | |
| `softwareSystemInstance <identifier> […]` | ✅ | |
| `containerInstance <identifier> […]` | ✅ | |
| `instanceOf` | ✅ | |
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
| `styles { element … }` | ◐ | Every property parses. Painted: `background`, `color`, `shape`, `icon`, `border`, `stroke`, `strokeWidth`, `opacity`, `metadata`, `description`. Parsed and exported but **not** painted: `width`, `height`, `fontSize`, `iconPosition` — each warns (`ignored-style-property`), as does an unrecognised property name (`unknown-style-property`) |
| `styles { relationship … }` | ◐ | Parsed and exported in full; the viewer does not yet paint edge styling beyond `metadata`/`description` |
| `light { … }` / `dark { … }` | ◐ | Colour-scheme variants parse; the viewer renders one scheme |
| `theme <url\|default>` | ✅ | Fetched, cached and merged; workspace styles win |
| `themes <url> <url…>` | ✅ | |
| `branding { … }` | ✅ | Logo and font, including the font URL |
| `terminology { … }` | ✅ | |

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

Everything else that is unsupported announces itself: `c4 check`
lists it, and the webapp surfaces it. If a construct you rely on is missing
here and does *not* appear in `check` output, that is a bug worth filing.

## What will not be supported

`!script` and `!plugin` execute arbitrary code — Groovy, Kotlin, Ruby or a
JVM class — named by the file being parsed. c4studio parses untrusted
DSL in a CLI, a web app and (potentially) a browser, so it skips both and
says so. This is a deliberate boundary, not a missing feature.
