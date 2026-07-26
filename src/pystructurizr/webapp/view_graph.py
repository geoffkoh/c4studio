"""Translate a pystructurizr View into graph data for the web frontend.

Visibility follows Structurizr view semantics: each view type exposes only
the elements at its abstraction level (a system context view never shows
containers), scoped to the view's subject element. Relationships whose
endpoints are not directly visible are "lifted" to their nearest visible
ancestor so, for example, a ``person -> container`` relationship still
produces a ``person -> system`` edge on a context diagram.

For container and component views the scoped element is emitted as a
``boundary`` group node and its direct children carry a ``parentId`` so the
frontend can nest them inside the boundary, matching C4 rendering
conventions.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from pystructurizr.themes import theme_styles
from pystructurizr.models import (
    Component,
    Container,
    CustomElement,
    DeploymentNode,
    Location,
    Person,
    Relationship,
    SoftwareSystem,
    View,
    FilterMode,
    ViewElement,
    ViewType,
    Workspace,
)


GraphNode = dict[str, Any]
GraphEdge = dict[str, Any]
GraphData = dict[str, list[Any]]

_Element = Person | SoftwareSystem | Container | Component | CustomElement


# Element-kind palette. Kept in Python so the JS bridge stays a thin shell
# and so tests can assert against it.
KIND_COLOURS: dict[str, str] = {
    "person": "#0d47a1",
    "person-external": "#546e7a",
    "system": "#1976d2",
    "system-external": "#90a4ae",
    "container": "#43a047",
    "component": "#fb8c00",
    "boundary": "#90a4ae",
    "infrastructure": "#607d8b",
    "container-instance": "#43a047",
    "system-instance": "#1976d2",
}


def _is_external(location: Location, tags: list[str]) -> bool:
    """Whether an element is external, via location or an "external" tag.

    Structurizr models commonly mark externals with a tag such as
    ``External System`` rather than the ``location`` property, so both are
    honoured.
    """
    if location == Location.EXTERNAL:
        return True
    return any("external" in tag.lower() for tag in tags)


def _person_kind(p: Person) -> str:
    return "person-external" if _is_external(p.location, p.tags) else "person"


def _system_kind(s: SoftwareSystem) -> str:
    return "system-external" if _is_external(s.location, s.tags) else "system"


def _parent_ids(workspace: Workspace) -> dict[str, str]:
    """Map each container/component id to its parent element's id."""
    parents: dict[str, str] = {}
    for s in workspace.software_systems:
        for c in s.containers:
            parents[c.id] = s.id
            for comp in c.components:
                parents[comp.id] = c.id
    return parents


def _ancestry(eid: str, parents: dict[str, str]) -> list[str]:
    """Return ``eid`` followed by its ancestors, innermost first."""
    chain = [eid]
    while chain[-1] in parents:
        chain.append(parents[chain[-1]])
    return chain


def _lift_to(eid: str, allowed: set[str], parents: dict[str, str]) -> str | None:
    """Return the most specific ancestor of ``eid`` present in ``allowed``."""
    for ancestor in _ancestry(eid, parents):
        if ancestor in allowed:
            return ancestor
    return None


def _related_peers(
    workspace: Workspace,
    scope_id: str,
    allowed: Iterable[str],
    parents: dict[str, str],
    include_scope_level: bool,
) -> set[str]:
    """Return peers outside the scope that relate to elements inside it.

    For each relationship crossing the scope boundary, the outside endpoint
    is lifted to the most specific allowed element and only that element is
    added — so a relationship declared against a container surfaces that
    container, not additionally its parent system (which would float
    unconnected once edges attach to the container).

    Args:
        workspace: The workspace being rendered.
        scope_id: The view's subject element.
        allowed: Ids of elements permitted to appear as peers in this view.
        parents: Child-to-parent id mapping.
        include_scope_level: Whether relationships declared against the
            scope element itself (rather than a descendant) count. True for
            context views, where the scope is itself a node; False where
            the scope renders as a boundary and such edges cannot attach.
    """
    allowed_set = set(allowed)
    peers: set[str] = set()
    for rel in workspace.relationships:
        endpoints = (
            (rel.source_id, rel.destination_id),
            (rel.destination_id, rel.source_id),
        )
        for inner, outer in endpoints:
            if scope_id not in _ancestry(inner, parents):
                continue
            if not include_scope_level and inner == scope_id:
                continue
            if scope_id in _ancestry(outer, parents):
                continue
            lifted = _lift_to(outer, allowed_set, parents)
            if lifted is not None:
                peers.add(lifted)
    return peers


def _default_ids(workspace: Workspace, view: View, parents: dict[str, str]) -> set[str]:
    """Return the default visible ids for a view (``include *`` semantics).

    Each view type exposes only the elements at its abstraction level; when
    the view has a scope element, peers are those with a relationship into
    the scope, surfaced at the level the relationship was declared.
    """
    scope = view.element_id
    people = [p.id for p in workspace.people]
    systems = [s.id for s in workspace.software_systems]

    if view.type == ViewType.SYSTEM_LANDSCAPE:
        return set(people) | set(systems)

    if view.type == ViewType.SYSTEM_CONTEXT:
        allowed = people + [sid for sid in systems if sid != scope]
        if not scope:
            return set(allowed)
        ids = _related_peers(
            workspace, scope, allowed, parents, include_scope_level=True
        )
        ids.add(scope)
        return ids

    if view.type == ViewType.CONTAINER:
        ids = set()
        for s in workspace.software_systems:
            if s.id == scope:
                ids.update(c.id for c in s.containers)
        allowed = people + [sid for sid in systems if sid != scope]
        if scope:
            ids |= _related_peers(
                workspace, scope, allowed, parents, include_scope_level=False
            )
        else:
            ids.update(allowed)
        return ids

    if view.type == ViewType.COMPONENT:
        ids = set()
        parent_system_id = parents.get(scope, "")
        allowed = list(people)
        for s in workspace.software_systems:
            if s.id != parent_system_id:
                allowed.append(s.id)
            for c in s.containers:
                if c.id == scope:
                    ids.update(comp.id for comp in c.components)
                else:
                    allowed.append(c.id)
        if scope:
            ids |= _related_peers(
                workspace, scope, allowed, parents, include_scope_level=False
            )
        else:
            ids.update(allowed)
        return ids

    return set()


def _visible_ids(workspace: Workspace, view: View) -> set[str]:
    """Return the ids of elements visible in ``view``.

    Explicitly included ids are honoured as-is; otherwise the view falls back
    to its type-scoped defaults (which is also what ``include *`` means).
    Exclusions always apply last.
    """
    parents = _parent_ids(workspace)
    if view.included_ids:
        visible = set(view.included_ids)
    else:
        visible = _default_ids(workspace, view, parents)
    return visible - set(view.excluded_ids)


def _lift(eid: str, visible: set[str], parents: dict[str, str]) -> str | None:
    """Return the nearest visible ancestor of ``eid`` (or ``eid`` itself)."""
    for ancestor in _ancestry(eid, parents):
        if ancestor in visible:
            return ancestor
    return None


def _node(
    eid: str,
    element: _Element,
    kind: str,
    x: int | None = None,
    y: int | None = None,
    parent_id: str | None = None,
) -> GraphNode:
    """Build a graph node descriptor.

    Positions are stored under ``style.x``/``style.y``; when absent the
    frontend layout engine places the node. ``parentId`` marks the node as a
    child of a boundary group node.
    """
    node: GraphNode = {
        "id": eid,
        "data": {
            "label": element.name,
            "kind": kind,
            "technology": getattr(element, "technology", ""),
            "description": element.description,
            "tags": list(element.tags),
        },
    }
    if parent_id is not None:
        node["parentId"] = parent_id
    if x is not None and y is not None:
        node["style"] = {"x": x, "y": y}
    return node


def _boundary_scope(
    workspace: Workspace, view: View
) -> tuple[str, SoftwareSystem | Container] | None:
    """Return the (id, element) rendered as this view's boundary, if any."""
    if view.type == ViewType.CONTAINER:
        for s in workspace.software_systems:
            if s.id == view.element_id:
                return s.id, s
    elif view.type == ViewType.COMPONENT:
        for s in workspace.software_systems:
            for c in s.containers:
                if c.id == view.element_id:
                    return c.id, c
    return None


def _edges(
    workspace: Workspace,
    visible: set[str],
    parents: dict[str, str],
    excluded_relationship_ids: set[str] | None = None,
) -> list[GraphEdge]:
    """Build edges between visible nodes, lifting endpoints to ancestors.

    Lifted duplicates collapse into a single implied edge per (source,
    target) pair; distinct direct relationships between the same pair are
    kept (e.g. separate "Reads" and "Writes" relationships).
    """
    excluded = excluded_relationship_ids or set()
    edges: list[GraphEdge] = []
    seen_pairs: set[tuple[str, str]] = set()
    seen_direct: set[tuple[str, str, str]] = set()
    pair_counts: dict[tuple[str, str], int] = {}
    for rel in workspace.relationships:
        # Implied (linked) relationships duplicate what endpoint lifting
        # already infers; rendering both would double the edge.
        if rel.linked_relationship_id:
            continue
        if rel.id and rel.id in excluded:
            continue
        src = _lift(rel.source_id, visible, parents)
        dst = _lift(rel.destination_id, visible, parents)
        if src is None or dst is None or src == dst:
            continue
        lifted = src != rel.source_id or dst != rel.destination_id
        if lifted:
            if (src, dst) in seen_pairs:
                continue
        else:
            key = (src, dst, rel.description)
            if key in seen_direct:
                continue
            seen_direct.add(key)
        seen_pairs.add((src, dst))
        edges.append(
            {
                "id": rel.id or _pair_edge_id(src, dst, pair_counts),
                "source": src,
                "target": dst,
                "data": {"label": rel.description, "technology": rel.technology},
            }
        )
    return edges


def _pair_edge_id(src: str, dst: str, counts: dict[tuple[str, str], int]) -> str:
    """Stable id for an edge that has no relationship id of its own.

    Numbered per endpoint pair rather than by position in the edge list, so
    an unrelated relationship appearing elsewhere in the view does not
    renumber this edge. Persisted layout (waypoints) is keyed by edge id,
    so the id has to survive edits that do not touch this pair.
    """
    index = counts.get((src, dst), 0)
    counts[(src, dst)] = index + 1
    return f"{src}__{dst}__{index}"


def _stored_positions(view: View) -> dict[str, tuple[int, int]]:
    """Positions persisted on the view's ViewElements, keyed by element id."""
    return {
        ve.id: (ve.x, ve.y)
        for ve in view.element_views
        if ve.x is not None and ve.y is not None
    }


# Implicit Structurizr tag per node kind, used for tag-based style matching.
_IMPLICIT_TAGS: dict[str, str] = {
    "person": "Person",
    "person-external": "Person",
    "system": "Software System",
    "system-external": "Software System",
    "container": "Container",
    "component": "Component",
    "infrastructure": "Infrastructure Node",
    "container-instance": "Container Instance",
    "system-instance": "Software System Instance",
}


def _apply_styles(workspace: Workspace, nodes: list[GraphNode]) -> None:
    """Overlay tag-based element styles onto node data, in place.

    Mirrors Structurizr style resolution: every element implicitly carries
    the ``Element`` tag plus a tag for its kind, then its own tags; element
    style rules are applied in declaration order, later matches overriding
    earlier ones. Remote theme styles come first, so the workspace's own
    styles win. Applied properties land in node data as ``background``,
    ``textColor``, ``shape`` and ``icon``.
    """
    styles = [
        *theme_styles(workspace).element_styles,
        *workspace.views.configuration.styles.element_styles,
    ]
    if not styles:
        return
    for node in nodes:
        data = node["data"]
        implicit = _IMPLICIT_TAGS.get(data.get("kind", ""))
        if implicit is None:
            continue
        tags = {"Element", implicit, *data.get("tags", [])}
        for style in styles:
            if style.tag not in tags:
                continue
            if style.background:
                data["background"] = style.background
            if style.color:
                data["textColor"] = style.color
            if style.shape is not None:
                data["shape"] = style.shape.value
            if style.icon:
                data["icon"] = style.icon


def _deployment_data(workspace: Workspace, view: View) -> GraphData:
    """Build graph data for a deployment view.

    Deployment nodes render as (arbitrarily) nested boundary group nodes;
    infrastructure nodes and container/system instances are their leaves.
    Branches containing no instance relevant to the view's scope/environment
    are pruned. Edges come from relationships declared directly between
    deployment elements plus relationships derived from the model: when two
    deployed elements' underlying model elements are related, their
    instances are too.
    """
    env = view.environment
    scope = view.element_id
    parents = _parent_ids(workspace)
    systems = {s.id: s for s in workspace.software_systems}
    container_system: dict[str, SoftwareSystem] = {}
    containers: dict[str, Container] = {}
    for s in workspace.software_systems:
        for c in s.containers:
            containers[c.id] = c
            container_system[c.id] = s

    def relevant_container(inst_container_id: str) -> bool:
        if not scope:
            return True
        s = container_system.get(inst_container_id)
        return s is not None and s.id == scope

    def relevant_system(system_id: str) -> bool:
        return not scope or system_id == scope

    def subtree_relevant(dn: DeploymentNode) -> bool:
        if any(relevant_container(i.container_id) for i in dn.container_instances):
            return True
        if any(
            relevant_system(i.software_system_id) for i in dn.software_system_instances
        ):
            return True
        return any(subtree_relevant(child) for child in dn.children)

    nodes: list[GraphNode] = []
    instance_refs: dict[str, str] = {}  # leaf id -> underlying model element id
    leaf_ids: set[str] = set()
    positions = _stored_positions(view)

    def place(node: GraphNode) -> GraphNode:
        xy = positions.get(node["id"])
        if xy is not None:
            node["style"] = {"x": xy[0], "y": xy[1]}
        return node

    def leaf(
        eid: str,
        label: str,
        kind: str,
        technology: str,
        description: str,
        tags: list[str],
        parent_id: str,
    ) -> None:
        nodes.append(
            place(
                {
                    "id": eid,
                    "parentId": parent_id,
                    "data": {
                        "label": label,
                        "kind": kind,
                        "technology": technology,
                        "description": description,
                        "tags": tags,
                    },
                }
            )
        )
        leaf_ids.add(eid)

    def emit(dn: DeploymentNode, parent_id: str | None) -> None:
        if env and dn.environment and dn.environment != env:
            return
        if not subtree_relevant(dn):
            return
        boundary: GraphNode = {
            "id": dn.id,
            "data": {
                "label": dn.name,
                "kind": "boundary",
                "technology": dn.technology,
                "description": dn.description,
                "tags": list(dn.tags),
                "boundaryLabel": "Deployment Node",
            },
        }
        if parent_id is not None:
            boundary["parentId"] = parent_id
        nodes.append(place(boundary))
        for infra in dn.infrastructure_nodes:
            leaf(
                infra.id,
                infra.name,
                "infrastructure",
                infra.technology,
                infra.description,
                list(infra.tags),
                dn.id,
            )
        for ssi in dn.software_system_instances:
            if relevant_system(ssi.software_system_id):
                s = systems.get(ssi.software_system_id)
                leaf(
                    ssi.id,
                    s.name if s else ssi.software_system_id,
                    "system-instance",
                    "",
                    s.description if s else "",
                    list(ssi.tags) + (list(s.tags) if s else []),
                    dn.id,
                )
                instance_refs[ssi.id] = ssi.software_system_id
        for ci in dn.container_instances:
            if relevant_container(ci.container_id):
                c = containers.get(ci.container_id)
                leaf(
                    ci.id,
                    c.name if c else ci.container_id,
                    "container-instance",
                    c.technology if c else "",
                    c.description if c else "",
                    list(ci.tags) + (list(c.tags) if c else []),
                    dn.id,
                )
                instance_refs[ci.id] = ci.container_id
        for child in dn.children:
            emit(child, dn.id)

    for dn in workspace.deployment_nodes:
        emit(dn, None)

    # Invert instance refs for deriving instance-level edges from the model.
    ref_instances: dict[str, list[str]] = {}
    for inst_id, ref_id in instance_refs.items():
        ref_instances.setdefault(ref_id, []).append(inst_id)
    ref_ids = set(ref_instances)

    edges: list[GraphEdge] = []
    seen: set[tuple[str, str]] = set()

    pair_counts: dict[tuple[str, str], int] = {}

    def add_edge(src: str, dst: str, rel: Relationship) -> None:
        if src == dst or (src, dst) in seen:
            return
        seen.add((src, dst))
        edges.append(
            {
                "id": _pair_edge_id(src, dst, pair_counts),
                "source": src,
                "target": dst,
                "data": {"label": rel.description, "technology": rel.technology},
            }
        )

    for rel in workspace.relationships:
        # Relationships declared directly between deployment elements.
        if rel.source_id in leaf_ids and rel.destination_id in leaf_ids:
            add_edge(rel.source_id, rel.destination_id, rel)
            continue
        # Model relationships replicated onto every pair of instances.
        src_ref = _lift(rel.source_id, ref_ids, parents)
        dst_ref = _lift(rel.destination_id, ref_ids, parents)
        if src_ref is None or dst_ref is None or src_ref == dst_ref:
            continue
        for src_inst in ref_instances[src_ref]:
            for dst_inst in ref_instances[dst_ref]:
                add_edge(src_inst, dst_inst, rel)

    _apply_styles(workspace, nodes)
    return {"nodes": nodes, "edges": edges}


def _element_kind(element: object) -> str:
    """Node kind for any static-structure element instance."""
    if isinstance(element, Person):
        return _person_kind(element)
    if isinstance(element, SoftwareSystem):
        return _system_kind(element)
    if isinstance(element, Container):
        return "container"
    return "component"


def _dynamic_data(workspace: Workspace, view: View) -> GraphData:
    """Build graph data for a dynamic view.

    Steps come from the view's ordered RelationshipViews; each becomes an
    edge labelled "<order>. <description>" carrying its numeric order so
    the frontend can animate the sequence. Nodes are the elements the
    steps reference, rendered flat (no boundaries). Step ids encode their
    endpoints as ``src__dst`` (see the DSL parser); ids that instead match
    a model relationship are resolved through it.
    """
    rel_by_id = {rel.id: rel for rel in workspace.relationships if rel.id}
    rel_by_pair: dict[tuple[str, str], Relationship] = {}
    for rel in workspace.relationships:
        rel_by_pair.setdefault((rel.source_id, rel.destination_id), rel)

    nodes: list[GraphNode] = []
    seen_nodes: set[str] = set()
    edges: list[GraphEdge] = []

    positions = _stored_positions(view)

    def add_node(eid: str) -> bool:
        if eid in seen_nodes:
            return True
        element = workspace.find_element(eid)
        if element is None or not isinstance(
            element, Person | SoftwareSystem | Container | Component
        ):
            return False
        seen_nodes.add(eid)
        x, y = positions.get(eid, (None, None))
        nodes.append(_node(eid, element, _element_kind(element), x, y))
        return True

    steps = sorted(
        view.relationship_views,
        key=lambda rv: int(rv.order) if rv.order.isdigit() else 0,
    )
    for index, rv in enumerate(steps, start=1):
        if rv.id in rel_by_id:
            rel = rel_by_id[rv.id]
            src, dst = rel.source_id, rel.destination_id
        elif "__" in rv.id:
            src, _, dst = rv.id.partition("__")
        else:
            continue
        if not add_node(src) or not add_node(dst):
            continue
        order = int(rv.order) if rv.order.isdigit() else index
        model_rel = rel_by_pair.get((src, dst))
        description = rv.description or (model_rel.description if model_rel else "")
        edges.append(
            {
                "id": f"step-{order}-{src}__{dst}",
                "source": src,
                "target": dst,
                "data": {
                    "label": f"{order}. {description}" if description else str(order),
                    "technology": model_rel.technology if model_rel else "",
                    "order": order,
                },
            }
        )

    _apply_styles(workspace, nodes)
    _attach_stored_sizes(view, nodes)
    return {"nodes": nodes, "edges": edges}


def base_view(workspace: Workspace, view: View) -> View | None:
    """Resolve a filtered view's base view by key.

    A base can be any non-filtered view; chaining filtered views is not
    supported (as in Structurizr).
    """
    for candidate in workspace.views:
        if candidate.key == view.base_view_key and candidate.type != ViewType.FILTERED:
            return candidate
    return None


def _filtered_data(
    workspace: Workspace, view: View, expand: set[str] | None
) -> GraphData:
    """Build graph data for a filtered view: the base view minus/plus tags.

    ``include`` mode keeps elements carrying at least one of the filter
    tags, ``exclude`` mode removes them; implicit tags (``Element``,
    ``Person``, ``Software System``, ...) participate, matching Structurizr
    semantics. Boundaries survive the tag filter but are pruned once they
    contain nothing; edges survive only if both endpoints do.
    """
    base = base_view(workspace, view)
    if base is None:
        return {"nodes": [], "edges": []}
    data = build_view_graph(workspace, base, expand)
    include = view.filter_mode != FilterMode.EXCLUDE
    wanted = set(view.filter_tags)

    def matches(node_data: dict[str, Any]) -> bool:
        implicit = _IMPLICIT_TAGS.get(node_data.get("kind", ""))
        tags = {
            "Element",
            *((implicit,) if implicit else ()),
            *node_data.get("tags", []),
        }
        return bool(tags & wanted)

    kept = [
        node
        for node in data["nodes"]
        if node["data"].get("kind") == "boundary" or matches(node["data"]) == include
    ]

    # Boundaries left with no children (transitively) disappear too.
    while True:
        occupied = {node.get("parentId") for node in kept}
        empties = {
            node["id"]
            for node in kept
            if node["data"].get("kind") == "boundary" and node["id"] not in occupied
        }
        if not empties:
            break
        kept = [node for node in kept if node["id"] not in empties]

    ids = {node["id"] for node in kept}
    edges = [
        edge
        for edge in data["edges"]
        if edge["source"] in ids and edge["target"] in ids
    ]
    return {"nodes": kept, "edges": edges}


def build_view_graph(
    workspace: Workspace, view: View, expand: set[str] | None = None
) -> GraphData:
    """Return graph data ``{nodes, edges}`` for the given view.

    Boundary group nodes always precede their children in the node list so
    the frontend can render parents behind children. Stored ViewElement
    positions are applied when available so previously persisted layouts
    survive a re-render.

    Args:
        workspace: The workspace to render from.
        view: The view to render.
        expand: Ids of elements to expand in place — a software system
            becomes a nested boundary holding its containers, a container
            one holding its components. Expansion cascades, so a container
            inside an expanded system can itself be expanded.
    """
    if view.type == ViewType.DEPLOYMENT:
        return _deployment_data(workspace, view)
    if view.type == ViewType.DYNAMIC:
        return _dynamic_data(workspace, view)
    if view.type == ViewType.FILTERED:
        return _filtered_data(workspace, view, expand)

    parents = _parent_ids(workspace)
    visible = _visible_ids(workspace, view)
    positions = _stored_positions(view)

    def pos(eid: str) -> tuple[int | None, int | None]:
        xy = positions.get(eid)
        return xy if xy is not None else (None, None)

    # Any requested element with children expands into a nested boundary:
    # systems into their containers, containers into their components.
    # Expansion cascades (fixpoint) so children of an expanded element can
    # themselves be expanded, nesting arbitrarily deep.
    systems_by_id = {s.id: s for s in workspace.software_systems}
    containers_by_id = {
        c.id: c for s in workspace.software_systems for c in s.containers
    }

    def children_of(eid: str) -> list[str]:
        if eid in systems_by_id:
            return [c.id for c in systems_by_id[eid].containers]
        if eid in containers_by_id:
            return [comp.id for comp in containers_by_id[eid].components]
        return []

    expanded: set[str] = set()
    if expand:
        changed = True
        while changed:
            changed = False
            for eid in expand:
                if eid in expanded or not children_of(eid):
                    continue
                if eid in visible or parents.get(eid) in expanded:
                    expanded.add(eid)
                    changed = True
        visible -= expanded
        for eid in expanded:
            visible.update(child for child in children_of(eid) if child not in expanded)

    nodes: list[GraphNode] = []

    # Landscape views group internal elements inside the enterprise
    # boundary when one is defined.
    enterprise_id: str | None = None
    if view.type == ViewType.SYSTEM_LANDSCAPE and workspace.enterprise is not None:
        enterprise_id = "__enterprise__"
        enterprise_node: GraphNode = {
            "id": enterprise_id,
            "data": {
                "label": workspace.enterprise.name,
                "kind": "boundary",
                "technology": "",
                "description": "",
                "tags": [],
                "boundaryLabel": "Enterprise",
            },
        }
        xy = positions.get(enterprise_id)
        if xy is not None:
            enterprise_node["style"] = {"x": xy[0], "y": xy[1]}
        nodes.append(enterprise_node)

    boundary_id: str | None = None
    scope = _boundary_scope(workspace, view)
    if scope is not None:
        boundary_id, boundary_element = scope
        # The scoped element is the boundary, never a leaf peer.
        visible.discard(boundary_id)
        x, y = pos(boundary_id)
        boundary_node = _node(boundary_id, boundary_element, "boundary", x, y)
        boundary_node["data"]["boundaryLabel"] = (
            "Container" if view.type == ViewType.COMPONENT else "Software System"
        )
        nodes.append(boundary_node)

    def child_of(eid: str) -> str | None:
        parent = parents.get(eid)
        if parent == boundary_id:
            return boundary_id
        if parent in expanded:
            return parent
        return None

    def enterprise_parent(kind: str) -> str | None:
        if enterprise_id is not None and not kind.endswith("-external"):
            return enterprise_id
        return None

    for p in workspace.people:
        if p.id in visible:
            x, y = pos(p.id)
            kind = _person_kind(p)
            nodes.append(_node(p.id, p, kind, x, y, enterprise_parent(kind)))

    for s in workspace.software_systems:
        if s.id in expanded:
            x, y = pos(s.id)
            kind = _system_kind(s)
            group = _node(s.id, s, "boundary", x, y, enterprise_parent(kind))
            group["data"]["boundaryLabel"] = "Software System"
            group["data"]["expanded"] = True
            nodes.append(group)
        elif s.id in visible:
            x, y = pos(s.id)
            kind = _system_kind(s)
            node = _node(s.id, s, kind, x, y, enterprise_parent(kind))
            if s.containers:
                node["data"]["expandable"] = True
            nodes.append(node)
        for c in s.containers:
            if c.id in expanded:
                x, y = pos(c.id)
                group = _node(c.id, c, "boundary", x, y, child_of(c.id))
                group["data"]["boundaryLabel"] = "Container"
                group["data"]["expanded"] = True
                nodes.append(group)
            elif c.id in visible:
                x, y = pos(c.id)
                node = _node(c.id, c, "container", x, y, child_of(c.id))
                if c.components:
                    node["data"]["expandable"] = True
                nodes.append(node)
            for comp in c.components:
                if comp.id in visible:
                    x, y = pos(comp.id)
                    nodes.append(
                        _node(comp.id, comp, "component", x, y, child_of(comp.id))
                    )

    nodes = _insert_group_boundaries(workspace, nodes)
    _apply_styles(workspace, nodes)
    _attach_stored_sizes(view, nodes)
    return {
        "nodes": nodes,
        "edges": _edges(
            workspace, visible, parents, set(view.excluded_relationship_ids)
        ),
    }


def _insert_group_boundaries(
    workspace: Workspace, nodes: list[GraphNode]
) -> list[GraphNode]:
    """Wrap grouped elements in synthetic group boundary nodes.

    Elements whose model ``group`` is set are re-parented into a chain of
    boundary nodes, one per group path segment. Group node ids embed the
    original parent id so identically named groups under different parents
    stay separate, and stay stable across renders so persisted layout
    sizes/positions keyed by id survive.
    """
    group_paths: dict[str, str] = {}
    for node in nodes:
        if node["data"].get("kind") == "boundary":
            continue
        element = workspace.find_element(node["id"])
        group = getattr(element, "group", "") if element is not None else ""
        if group:
            group_paths[node["id"]] = group
    if not group_paths:
        return nodes

    result: list[GraphNode] = []
    created: set[str] = set()
    for node in nodes:
        path = group_paths.get(node["id"])
        if path is None:
            result.append(node)
            continue
        parent = node.get("parentId")
        for segment in path.split("/"):
            gid = f"__group__{parent or ''}__{segment}"
            if gid not in created:
                group_node: GraphNode = {
                    "id": gid,
                    "data": {
                        "label": segment,
                        "kind": "boundary",
                        "technology": "",
                        "description": "",
                        "tags": [],
                        "boundaryLabel": "Group",
                    },
                }
                if parent is not None:
                    group_node["parentId"] = parent
                created.add(gid)
                result.append(group_node)
            parent = gid
        node["parentId"] = parent
        result.append(node)
    return result


def apply_sizes(view: View, sizes: dict[str, tuple[int, int]]) -> None:
    """Update view.element_views with the given id → (width, height) sizes.

    Adds a ViewElement for any id not already present; used for resizable
    boundary nodes whose dimensions are persisted alongside positions.
    """
    existing = {ve.id: ve for ve in view.element_views}
    for eid, (width, height) in sizes.items():
        ve = existing.get(eid)
        if ve is None:
            ve = ViewElement(id=eid, width=width, height=height)
            view.element_views.append(ve)
            existing[eid] = ve
        else:
            ve.width = width
            ve.height = height


def _attach_stored_sizes(view: View, nodes: list[GraphNode]) -> None:
    """Overlay persisted width/height onto boundary nodes, in place."""
    sizes = {
        ve.id: (ve.width, ve.height)
        for ve in view.element_views
        if ve.width is not None and ve.height is not None
    }
    if not sizes:
        return
    for node in nodes:
        if node["data"].get("kind") != "boundary":
            continue
        size = sizes.get(node["id"])
        if size is not None:
            style = node.setdefault("style", {})
            style["width"], style["height"] = size


def apply_positions(view: View, positions: dict[str, tuple[int, int]]) -> None:
    """Update view.element_views with the given id → (x, y) positions.

    Adds a ViewElement for any id not already present. Existing entries
    are updated in place to preserve any other fields the user set.
    """
    existing = {ve.id: ve for ve in view.element_views}
    for eid, (x, y) in positions.items():
        ve = existing.get(eid)
        if ve is None:
            view.element_views.append(ViewElement(id=eid, x=x, y=y))
        else:
            ve.x = x
            ve.y = y
