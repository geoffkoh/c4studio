# Python API

c4studio is a library as well as an app. The parser, the typed model and the generators are importable, and the Studio and CLI are built on them. Every example on this page is run by the test suite against a real workspace.

## Parse a workspace

```python
from c4studio.parser.dsl import parse_dsl_file

workspace = parse_dsl_file("architecture.dsl")

print(workspace.name)
for system in workspace.model.software_systems:
    print(system.name, [container.name for container in system.containers])
for view in workspace.views:
    print(view.key, view.type.value)
```

`parse_dsl` takes a string instead of a file. Workspace JSON goes through `c4studio.parser.json_parser.parse_json_file`. Parsing never executes anything in the file: a construct the parser does not support is skipped and recorded.

```python
from c4studio.parser.dsl import parse_dsl_file

workspace = parse_dsl_file("architecture.dsl")
for diagnostic in workspace.diagnostics:
    print(diagnostic.code, diagnostic.line, diagnostic.message)
```

## Find things in the model

```python
from c4studio.parser.dsl import parse_dsl_file

workspace = parse_dsl_file("architecture.dsl")
element = workspace.find_element("banking")   # by DSL identifier
print(element.name, element.description)

for relationship in workspace.relationships:
    print(relationship.source_id, "->", relationship.destination_id, relationship.description)
```

## Generate Mermaid

Two Mermaid targets, both drawn from the same view graph the Studio uses:

| Generator | Syntax | Covers |
| --- | --- | --- |
| `MermaidGenerator` | `C4Context`, `C4Container`, `C4Component` | Landscape, context, container and component views |
| `FlowchartGenerator` | `flowchart` with `subgraph` | All of the above, plus dynamic, deployment and filtered views |

```python
from c4studio.generators import FlowchartGenerator, MermaidGenerator
from c4studio.parser.dsl import parse_dsl_file

workspace = parse_dsl_file("architecture.dsl")

for key, mermaid in MermaidGenerator(workspace).generate_all().items():
    print(f"%% {key}\n{mermaid}")

flowcharts = FlowchartGenerator(workspace).generate_all()
```

Mermaid's C4 diagram types are experimental upstream and lay out poorly on dense models, so prefer the flowchart target for anything rendered on GitHub or in a wiki.

## Lint and impact

```python
from c4studio.impact import analyse
from c4studio.lint import lint
from c4studio.parser.dsl import parse_dsl_file

workspace = parse_dsl_file("architecture.dsl")

for finding in lint(workspace):
    print(finding.code, finding.message)

impact = analyse(workspace, "accountsApi")
print("depends on it:", [hop.name for hop in impact.dependents])
print("it depends on:", [hop.name for hop in impact.dependencies])
print("drawn in:", impact.views)
```

`lint` takes an optional `LintConfig`, the same settings as `c4studio.lint.json`. Each `Hop` has the element's `id`, `name`, `kind` and its `depth`, the number of relationships away it is.

## Export JSON

```python
from c4studio.generators.json_export import export_json
from c4studio.parser.dsl import parse_dsl_file

workspace = parse_dsl_file("architecture.dsl")
document = export_json(workspace)   # a str of Structurizr workspace JSON
```

The output round-trips with structurizr.com, Structurizr Lite and c4studio's own JSON parser.

## Render and publish

Both need Node, like their CLI commands:

```python
from pathlib import Path

from c4studio.parser.dsl import parse_dsl_file
from c4studio.publish import publish
from c4studio.render import render_view

workspace = parse_dsl_file("architecture.dsl")
svg = render_view(workspace, workspace.views[0], show_legend=True)
publish(workspace, Path("site"), clean=True)
```

The model classes in `c4studio.models` are typed and documented in the source, which is the reference for their fields.
