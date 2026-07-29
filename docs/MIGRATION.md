# pystructurizr Migration Guide

This guide describes the changes introduced by the 4-phase Structurizr Java
compatibility work (PP-31 → PP-35) and how to adapt existing code.

---

## Phase 1 — Critical fixes (PP-32)

### `DeploymentNode.instances`: `str` → `int` *(reverted — see below)*

Before:

```python
DeploymentNode(id="dn", name="EC2", instances="3")
```

After:

```python
DeploymentNode(id="dn", name="EC2", instances=3)
```

JSON parser already casts via `int(...)`; if you constructed `DeploymentNode`
directly with a string literal, update the call.

> **Reverted (PP-87).** This change lost data: Structurizr allows range
> expressions such as `"0..N"` and `"1..3"`, which an `int` cannot hold — the
> parser fell back to `1` and discarded the author's intent without a warning.
> `instances` is a `str` again, defaulting to `"1"`, matching
> structurizr-java. Compare against `"3"` rather than `3`.

### `parent_id` on `Container`, `Component`, `DeploymentNode`, `InfrastructureNode`

New read-only field used for hierarchy reconstruction. The JSON and DSL parsers
populate it automatically. No action required unless you build these elements
by hand and want hierarchy lookup to work — in that case set `parent_id` to the
owning element's id.

### `AutomaticLayout` default separations: 300 → 100

Aligns with Structurizr Java. If you relied on `rank_separation == 300`,
specify it explicitly.

### `Perspective.title`

New optional field. Backwards compatible.

---

## Phase 2 — Important fields (PP-33)

Additive fields with safe defaults — no migration needed:

- **Workspace metadata**: `id`, `version`, `revision`, `last_modified_date`,
  `last_modified_by`, `created_date`, `created_by`
- **ViewElement**: `title`, `description`, `width`, `height`
- **RelationshipView**: `title`, `link`, `link_element`
- **View**: `owner`, `disable_automatic_layout`, `hide_element_metadata`,
  `hide_relationship_metadata`
- **DeploymentNode** / **InfrastructureNode**: `icon`

### `Terminology` defaults changed

Was empty strings, now Java strings:

```python
Terminology()
# enterprise="Enterprise", person="Person", software_system="Software System", ...
```

If you constructed `Terminology()` and relied on `terminology.person == ""`,
pass `Terminology(person="")` explicitly.

---

## Phase 3 — Structural refactor (PP-34)

The biggest change. `Workspace` is composed of `Model` and `ViewSet` instead of
holding flat lists.

### New structure

```python
@dataclass
class Workspace:
    name: str
    description: str = ""
    model: Model = field(default_factory=Model)
    views: ViewSet = field(default_factory=ViewSet)
    # workspace metadata (id, version, revision, ...) unchanged
```

`Model` owns `people`, `software_systems`, `relationships`, `deployment_nodes`,
`deployment_environments`, `enterprise`, plus `find_element()` and
`all_relationships_for()`.

`ViewSet` owns typed view lists (`system_landscape_views`,
`system_context_views`, `container_views`, `component_views`, `dynamic_views`,
`deployment_views`, `custom_views`, `filtered_views`) plus `configuration`.

### What still works (backward-compatible)

All of these continue to function via `@property` delegates on `Workspace`:

```python
ws.people.append(p)              # → ws.model.people
ws.software_systems[0]           # → ws.model.software_systems
ws.relationships                 # → ws.model.relationships
ws.deployment_nodes              # → ws.model.deployment_nodes
ws.deployment_environments       # → ws.model.deployment_environments
ws.enterprise = Enterprise(...)  # ws.model.enterprise = ...
ws.configuration = Configuration(...)  # ws.views.configuration = ...
ws.find_element("id")            # → ws.model.find_element
ws.all_relationships_for(ids)    # → ws.model.all_relationships_for
```

`ws.views` is now a `ViewSet` but supports the list protocol for back-compat:

```python
len(ws.views)
ws.views[0]
for view in ws.views: ...
ws.views.append(View(type=ViewType.SYSTEM_CONTEXT, key="ctx"))
# append() routes to the typed list matching view.type
```

### What stopped working

Constructing `Workspace` with the old flat keyword arguments no longer works:

```python
# Before
Workspace(name="W", deployment_nodes=[dn])
Workspace(name="W", enterprise=Enterprise(name="Acme"))

# After
Workspace(name="W", model=Model(deployment_nodes=[dn]))
Workspace(name="W", model=Model(enterprise=Enterprise(name="Acme")))
```

If you have parsers or fixtures that pass element lists or `enterprise` as
keyword arguments to `Workspace`, wrap them in a `Model`.

### Recommended (new) style

Prefer accessing through the structured fields:

```python
ws.model.people.append(person)
ws.views.system_context_views.append(view)
ws.views.configuration = configuration
```

---

## Phase 4 — Complete features (PP-35)

Additive fields with safe defaults:

- **`CustomElement.icon`**: optional icon name/URL
- **`Configuration.branding`**: optional `Branding(color, font, logo)`
- **`Configuration.generators_and_exporters`**: `dict[str, str]`
- **`Workspace.documentation`**: `list[Documentation]` (each
  `Documentation(content, format="Markdown")`)
- **`Workspace.decisions`**: `list[str]` for architecture decision references

### `Workspace.validate()`

New method that returns a list of validation issues. Empty list means the
workspace is well-formed.

```python
issues = ws.validate()
if issues:
    for issue in issues:
        print(issue)
```

Currently checks that view keys are non-empty and unique across all view
types. Extend as needed.

---

## Field mapping reference

| Phase | Class | Field | Type | Default |
|---|---|---|---|---|
| 1 | DeploymentNode | instances | `int` | `1` |
| 1 | Container/Component/DeploymentNode/InfrastructureNode | parent_id | `str` | `""` |
| 1 | AutomaticLayout | rank_separation | `int` | `100` |
| 1 | AutomaticLayout | node_separation | `int` | `100` |
| 1 | Perspective | title | `str` | `""` |
| 2 | Workspace | id | `str` | `""` |
| 2 | Workspace | version | `int` | `1` |
| 2 | Workspace | revision | `int` | `1` |
| 2 | Workspace | last_modified_date | `str` | `""` |
| 2 | Workspace | last_modified_by | `str` | `""` |
| 2 | Workspace | created_date | `str` | `""` |
| 2 | Workspace | created_by | `str` | `""` |
| 2 | ViewElement | title, description | `str` | `""` |
| 2 | ViewElement | width, height | `Optional[int]` | `None` |
| 2 | RelationshipView | title | `str` | `""` |
| 2 | RelationshipView | link, link_element | `Optional[bool]`/`Optional[int]` | `None` |
| 2 | View | owner | `str` | `""` |
| 2 | View | disable_automatic_layout | `bool` | `False` |
| 2 | View | hide_element_metadata | `bool` | `False` |
| 2 | View | hide_relationship_metadata | `bool` | `False` |
| 2 | DeploymentNode/InfrastructureNode | icon | `str` | `""` |
| 2 | Terminology | (all) | `str` | Java defaults |
| 3 | Workspace | model | `Model` | `Model()` |
| 3 | Workspace | views | `ViewSet` | `ViewSet()` |
| 4 | CustomElement | icon | `str` | `""` |
| 4 | Configuration | branding | `Optional[Branding]` | `None` |
| 4 | Configuration | generators_and_exporters | `dict[str, str]` | `{}` |
| 4 | Workspace | documentation | `list[Documentation]` | `[]` |
| 4 | Workspace | decisions | `list[str]` | `[]` |

---

## Deliberate divergences from structurizr-java

These fields exist in pystructurizr but not in structurizr-java, or differ
from it. They are **intentional and supported**, not oversights, and were
reviewed against the Java model in July 2026. Recorded here because a
periodic "align with Java" pass keeps proposing their removal.

| Field | Why it stays |
| --- | --- |
| `parent_id` on `Container`, `Component`, `DeploymentNode`, `InfrastructureNode` | Load-bearing. The webapp reconstructs element hierarchy from it, and `view_graph` lifts relationships to their nearest visible ancestor through it — that is what makes a `person -> container` relationship render as `person -> system` on a context diagram. Java uses transient back-references instead; pystructurizr's model is serialised and re-read, so it needs the explicit id. |
| `Person.location`, `SoftwareSystem.location` | Java deprecated `location`, but the DSL keyword still exists and this is how external elements get their distinct styling: `view_graph._person_kind` / `_system_kind` consult it (falling back to an `external` tag). Removing it would silently flatten internal and external elements to the same colour. |
| `Perspective.url`, `Perspective.title` | Additive metadata, parsed from the DSL and round-tripped through workspace JSON. `title` was added deliberately by the PP-31 compatibility work; a later ticket proposed removing it, which would have undone that. Check the Java model directly before revisiting. |
| `icon` on `CustomElement`, `DeploymentNode`, `InfrastructureNode` | Java carries `icon` only on `ElementStyle`. Per-element icons are a convenience the renderer honours. |

By contrast, these **are** worth aligning and are tracked as bugs rather
than parity items, because the current behaviour loses data:
`DeploymentNode.instances` cannot express Structurizr's `"0..N"` range
syntax, and `Branding.font` drops the font URL.

`Terminology` defaults are **not** a divergence in practice: they are
populated in the dataclass, but `generators/json_export._terminology`
compares against those defaults and emits only values the workspace
actually set, so an undeclared terminology exports as `null`.
