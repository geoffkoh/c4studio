"""Adapt pystructurizr views into React Flow-shaped graph data.

The heavy lifting (deciding which elements are visible and collecting the
relationships between them) lives in
:mod:`pystructurizr.graph.view_graph`. This module re-shapes that graph output
into the node/edge structure the React Flow frontend expects.
"""

from __future__ import annotations

from typing import Any

from pystructurizr.models import View, ViewType, Workspace
from pystructurizr.graph.view_graph import (
    KIND_COLOURS,
    build_view_graph,
    effective_layout,
    rank_direction,
)


ReactFlowNode = dict[str, Any]
ReactFlowEdge = dict[str, Any]
ReactFlowData = dict[str, Any]


_SUPPORTED_TYPES = frozenset(
    {
        ViewType.SYSTEM_LANDSCAPE,
        ViewType.SYSTEM_CONTEXT,
        ViewType.CONTAINER,
        ViewType.COMPONENT,
        ViewType.DYNAMIC,
        ViewType.DEPLOYMENT,
        ViewType.FILTERED,
    }
)


def is_supported(view: View) -> bool:
    """Return whether a view type produces a meaningful React Flow graph.

    Args:
        view: The view to check.

    Returns:
        ``True`` for ``systemLandscape``, ``systemContext``, ``container``,
        ``component``, ``dynamic``, ``deployment`` and ``filtered`` views;
        ``False`` otherwise.
    """
    return view.type in _SUPPORTED_TYPES


def react_flow_graph(
    workspace: Workspace, view: View, expand: set[str] | None = None
) -> ReactFlowData:
    """Build React Flow ``{nodes, edges}`` data for ``view``.

    Node ``data`` carries everything the graph builder emitted (label, kind,
    technology, description, tags, boundary/expansion flags) plus the kind's
    palette ``color``. Nodes nested inside a boundary group node carry a
    top-level ``parentId``. A ``position`` is included only when the
    underlying view element has stored coordinates; otherwise it is omitted
    so the frontend can run its own auto-layout.

    Args:
        workspace: The workspace the view belongs to.
        view: The view to render.
        expand: For container views, ids of containers to expand in place.

    Returns:
        A dict with ``nodes`` and ``edges`` lists in React Flow shape.
    """
    graph_data = build_view_graph(workspace, view, expand)

    nodes: list[ReactFlowNode] = []
    for graph_node in graph_data["nodes"]:
        data = dict(graph_node.get("data", {}))
        # Tag-based style backgrounds win over the built-in kind palette.
        data["color"] = data.get("background") or KIND_COLOURS.get(data.get("kind", ""))
        node: ReactFlowNode = {"id": graph_node["id"], "data": data}
        if "parentId" in graph_node:
            node["parentId"] = graph_node["parentId"]
        style = graph_node.get("style")
        if style is not None and "x" in style and "y" in style:
            node["position"] = {"x": style["x"], "y": style["y"]}
        if style is not None and "width" in style and "height" in style:
            node["size"] = {"width": style["width"], "height": style["height"]}
        nodes.append(node)

    edges: list[ReactFlowEdge] = []
    for graph_edge in graph_data["edges"]:
        edge_data = graph_edge.get("data", {})
        edge: ReactFlowEdge = {
            "id": graph_edge["id"],
            "source": graph_edge["source"],
            "target": graph_edge["target"],
            "label": edge_data.get("label", ""),
        }
        if "order" in edge_data:
            edge["order"] = edge_data["order"]
        edges.append(edge)

    # Filtered views carry no layout of their own; inherit the base view's.
    layout = effective_layout(workspace, view)
    direction = rank_direction(workspace, view)
    rank_separation = layout.rank_separation if layout is not None else 100
    node_separation = layout.node_separation if layout is not None else 100

    return {
        "nodes": nodes,
        "edges": edges,
        "rankDirection": direction,
        "rankSeparation": rank_separation,
        "nodeSeparation": node_separation,
    }
