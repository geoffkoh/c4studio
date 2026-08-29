"""Pieces shared by the Mermaid targets.

Both targets consume the same graph data (:mod:`c4studio.graph.view_graph`)
and differ only in emission, so what they share is small: node id
sanitising, the boundary tree, and the title a view falls back to when it
declares none. Label escaping is *not* shared — the C4 macros and
flowchart labels have different escaping rules.
"""

from __future__ import annotations

import re

from c4studio.graph.view_graph import GraphNode
from c4studio.models import View, ViewType, Workspace


# Title prefix per view type, for views that declare no title of their own.
_TITLE_PREFIXES: dict[ViewType, str] = {
    ViewType.SYSTEM_CONTEXT: "System Context",
    ViewType.CONTAINER: "Container Diagram",
    ViewType.COMPONENT: "Component Diagram",
    ViewType.DYNAMIC: "Dynamic Diagram",
    ViewType.DEPLOYMENT: "Deployment Diagram",
}

_INVALID_ID_CHARS = re.compile(r"[^0-9A-Za-z_]")


def safe_id(raw: str) -> str:
    """Convert an element id into a valid Mermaid node id."""
    return _INVALID_ID_CHARS.sub("_", raw)


def children_by_parent(
    nodes: list[GraphNode],
) -> dict[str | None, list[GraphNode]]:
    """Group nodes by ``parentId``, preserving the graph's ordering.

    Boundary nodes always precede their children in the graph's node list,
    so emitting from the ``None`` key downwards walks the boundary tree in
    declaration order — which is what keeps output deterministic.
    """
    children: dict[str | None, list[GraphNode]] = {}
    for node in nodes:
        children.setdefault(node.get("parentId"), []).append(node)
    return children


def view_title(workspace: Workspace, view: View) -> str:
    """The view's own title, else one derived from its type and subject."""
    if view.title:
        return view.title
    if view.type == ViewType.SYSTEM_LANDSCAPE:
        return "System Landscape"
    if view.type == ViewType.FILTERED:
        return f"Filtered – {view.base_view_key}" if view.base_view_key else "Filtered"

    prefix = _TITLE_PREFIXES.get(view.type, "Diagram")
    subject = workspace.find_element(view.element_id) if view.element_id else None
    if subject is not None:
        return f"{prefix} – {subject.name}"
    # Deployment views may be scoped to an environment rather than an element.
    detail = view.element_id or view.environment
    return f"{prefix} – {detail}" if detail else prefix
