"""Full-model explorer: the whole static model as one React Flow graph.

Unlike a view graph, the explorer is not driven by a curated view. It shows
every person, custom element and software system in the workspace — with
containers and components nested inside boundary group nodes when the
requested abstraction level asks for them — plus every relationship,
attached at the level each endpoint is rendered at. Alongside the graph it
carries a flat search index over *all* static elements (regardless of the
rendered level), the raw declared relationships, and a map of which views
each element appears in, so the frontend can search the model and jump
from an element to the curated views that feature it.
"""

from __future__ import annotations

from typing import Any

from c4studio.models import Workspace
from c4studio.webapp import graph
from c4studio.graph.view_graph import (
    KIND_COLOURS,
    GraphNode,
    _ancestry,
    _apply_styles,
    _edges,
    _node,
    _parent_ids,
    _person_kind,
    _system_kind,
    build_view_graph,
)

# Custom elements never appear in curated view graphs, so the shared kind
# palette has no entry for them; the explorer gives them their own colour.
_CUSTOM_COLOUR = "#7b1fa2"

# Abstraction levels the explorer can render the model at. Each level shows
# everything the previous one does, exploding elements that have children
# at the new level into boundary group nodes.
LEVELS = ("systems", "containers", "components")


def _element_index(workspace: Workspace) -> list[dict[str, Any]]:
    """Flat search index over every static element in the model.

    Each entry carries the element's identity and metadata plus ``parent``
    (a human-readable ancestry path such as ``"Internet Banking › API"``)
    and ``level``, the shallowest explorer level at which the element gets
    its own node.
    """
    entries: list[dict[str, Any]] = []

    def add(element: Any, kind: str, level: str, parent_path: list[str]) -> None:
        entries.append(
            {
                "id": element.id,
                "name": element.name,
                "kind": kind,
                "technology": getattr(element, "technology", ""),
                "description": element.description,
                "tags": list(element.tags),
                "parent": " › ".join(parent_path),
                "level": level,
            }
        )

    for person in workspace.people:
        add(person, _person_kind(person), "systems", [])
    for custom in workspace.custom_elements:
        add(custom, "custom", "systems", [])
    for system in workspace.software_systems:
        add(system, _system_kind(system), "systems", [])
        for container in system.containers:
            add(container, "container", "containers", [system.name])
            for component in container.components:
                add(
                    component,
                    "component",
                    "components",
                    [system.name, container.name],
                )
    return entries


def _relationship_index(workspace: Workspace) -> list[dict[str, Any]]:
    """Declared relationships, for the frontend's element details panel.

    Implied (linked) relationships are skipped: they duplicate a declared
    relationship at an ancestor level and would double-list connections.
    """
    return [
        {
            "id": rel.id,
            "source_id": rel.source_id,
            "destination_id": rel.destination_id,
            "description": rel.description,
            "technology": rel.technology,
        }
        for rel in workspace.relationships
        if not rel.linked_relationship_id
    ]


def _views_by_element(workspace: Workspace) -> dict[str, list[str]]:
    """Map element ids to the keys of the views they appear in.

    Membership comes from each supported view's rendered graph, so it
    matches exactly what the user would see when jumping to the view.
    Synthetic nodes (enterprise/group boundaries, deployment instances)
    are dropped by intersecting with the model's element ids.
    """
    element_ids = {entry["id"] for entry in _element_index(workspace)}
    membership: dict[str, list[str]] = {}
    for view in workspace.views:
        if not graph.is_supported(view):
            continue
        data = build_view_graph(workspace, view)
        for node in data["nodes"]:
            eid = node["id"]
            if eid in element_ids:
                membership.setdefault(eid, []).append(view.key)
    return membership


def model_graph(workspace: Workspace, level: str = "containers") -> dict[str, Any]:
    """Build the explorer payload for the whole model at ``level``.

    Args:
        workspace: The workspace to render.
        level: One of :data:`LEVELS` — how deep to explode the hierarchy.
            Elements with children at the requested level render as
            boundary group nodes; leaves render as regular element nodes.

    Returns:
        A dict with React Flow ``nodes`` and ``edges``, the flat
        ``elements`` search index, declared ``relationships`` and the
        ``views_by_element`` membership map.

    Raises:
        ValueError: If ``level`` is not one of :data:`LEVELS`.
    """
    if level not in LEVELS:
        raise ValueError(f"Unknown explorer level: {level!r}")
    show_containers = level in ("containers", "components")
    show_components = level == "components"

    parents = _parent_ids(workspace)
    nodes: list[GraphNode] = []

    for person in workspace.people:
        nodes.append(_node(person.id, person, _person_kind(person)))

    for custom in workspace.custom_elements:
        custom_node = _node(custom.id, custom, "custom")
        if custom.metadata:
            custom_node["data"]["technology"] = custom.metadata
        nodes.append(custom_node)

    for system in workspace.software_systems:
        if show_containers and system.containers:
            boundary = _node(system.id, system, "boundary")
            boundary["data"]["boundaryLabel"] = "Software System"
            nodes.append(boundary)
            for container in system.containers:
                if show_components and container.components:
                    group = _node(
                        container.id, container, "boundary", parent_id=system.id
                    )
                    group["data"]["boundaryLabel"] = "Container"
                    nodes.append(group)
                    for component in container.components:
                        nodes.append(
                            _node(
                                component.id,
                                component,
                                "component",
                                parent_id=container.id,
                            )
                        )
                else:
                    nodes.append(
                        _node(container.id, container, "container", parent_id=system.id)
                    )
        else:
            nodes.append(_node(system.id, system, _system_kind(system)))

    _apply_styles(workspace, nodes)

    # Reshape into the same React Flow contract as /api/views/{key}/graph:
    # tag-based style backgrounds win over the built-in kind palette.
    rf_nodes: list[dict[str, Any]] = []
    for graph_node in nodes:
        data = dict(graph_node["data"])
        kind = data.get("kind", "")
        fallback = _CUSTOM_COLOUR if kind == "custom" else KIND_COLOURS.get(kind)
        data["color"] = data.get("background") or fallback
        rf_node: dict[str, Any] = {"id": graph_node["id"], "data": data}
        if "parentId" in graph_node:
            rf_node["parentId"] = graph_node["parentId"]
        rf_nodes.append(rf_node)

    # Every rendered node (boundaries included) can carry edges, so each
    # relationship attaches at exactly the level it was declared at; no
    # endpoint lifting happens. Edges between an element and its own
    # ancestor would draw from a child to its enclosing boundary, so they
    # are dropped.
    visible = {node["id"] for node in nodes}
    rf_edges = [
        {
            "id": edge["id"],
            "source": edge["source"],
            "target": edge["target"],
            "label": edge["data"].get("label", ""),
        }
        for edge in _edges(workspace, visible, parents)
        if edge["source"] not in _ancestry(edge["target"], parents)[1:]
        and edge["target"] not in _ancestry(edge["source"], parents)[1:]
    ]

    return {
        "nodes": rf_nodes,
        "edges": rf_edges,
        "rankDirection": "TB",
        "elements": _element_index(workspace),
        "relationships": _relationship_index(workspace),
        "views_by_element": _views_by_element(workspace),
    }
