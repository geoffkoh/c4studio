"""
Mermaid C4 diagram generator.

Renders from the shared view graph (:mod:`c4studio.graph.view_graph`)
rather than re-deriving C4 semantics: abstraction level per view type,
boundary nesting, group boundaries, and — the part this module used to get
wrong — relationship endpoints lifted to their nearest visible ancestor, so
every alias a ``Rel()`` references is an entity the same diagram declares.

Supported view types:
  - C4Context   (system landscape, system context views)
  - C4Container (container views)
  - C4Component (component views)

Dynamic, deployment, filtered and custom/image views emit a comment; use
:mod:`c4studio.generators.flowchart`, which renders every view type.
"""

from __future__ import annotations

from c4studio.generators.mermaid_common import (
    children_by_parent,
    safe_id,
    view_title,
)
from c4studio.graph.view_graph import GraphEdge, GraphNode, build_view_graph
from c4studio.models import (
    View,
    ViewType,
    Workspace,
)


# Mermaid diagram type per view type; absent means "not yet supported".
_DIAGRAM_TYPES: dict[ViewType, str] = {
    ViewType.SYSTEM_LANDSCAPE: "C4Context",
    ViewType.SYSTEM_CONTEXT: "C4Context",
    ViewType.CONTAINER: "C4Container",
    ViewType.COMPONENT: "C4Component",
}

# Boundary macro per the graph's ``boundaryLabel``. Group boundaries and
# anything unrecognised fall back to the generic ``Boundary``.
_BOUNDARY_MACROS: dict[str, str] = {
    "Enterprise": "Enterprise_Boundary",
    "Software System": "System_Boundary",
    "Container": "Container_Boundary",
}


def _q(text: str) -> str:
    return text.replace('"', '\\"')


def _scope_members(nodes: list[GraphNode], scope_id: str) -> set[str]:
    """Ids nested (at any depth) inside the view's scope boundary.

    Containers and components inside the scope are the diagram's subject and
    render as ``Container``/``Component``; the same kinds surfaced from
    elsewhere in the model are peers and render as ``*_Ext``.
    """
    if not scope_id:
        return set()
    parents = {node["id"]: node.get("parentId") for node in nodes}
    members: set[str] = set()
    for nid in parents:
        ancestor = parents.get(nid)
        while ancestor is not None:
            if ancestor == scope_id:
                members.add(nid)
                break
            ancestor = parents.get(ancestor)
    return members


class MermaidGenerator:
    """Generate Mermaid C4 diagrams from a Workspace."""

    def __init__(self, workspace: Workspace) -> None:
        self.workspace = workspace

    def generate_all(self) -> dict[str, str]:
        """Return a mapping of view key → mermaid diagram string."""
        return {v.key: self.generate_view(v) for v in self.workspace.views}

    def generate_view(self, view: View) -> str:
        """Render one view as a Mermaid C4 diagram."""
        diagram_type = _DIAGRAM_TYPES.get(view.type)
        if diagram_type is None:
            return f"%%  View type {view.type} is not yet supported\n"

        data = build_view_graph(self.workspace, view)
        nodes: list[GraphNode] = data["nodes"]

        # Boundaries hold their children via parentId; emit the tree.
        children = children_by_parent(nodes)
        inside = _scope_members(nodes, view.element_id)

        title = _q(view_title(self.workspace, view))
        lines: list[str] = [diagram_type, f"    title {title}", ""]
        self._emit_nodes(lines, children, None, inside, indent="    ")

        lines.append("")
        for edge in data["edges"]:
            lines.append(self._rel(edge))

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Emission
    # ------------------------------------------------------------------

    def _emit_nodes(
        self,
        lines: list[str],
        children: dict[str | None, list[GraphNode]],
        parent: str | None,
        inside: set[str],
        indent: str,
    ) -> None:
        """Append entity lines for ``parent``'s children, recursing into boundaries."""
        for node in children.get(parent, []):
            node_data = node["data"]
            if node_data.get("kind") == "boundary":
                macro = _BOUNDARY_MACROS.get(
                    node_data.get("boundaryLabel", ""), "Boundary"
                )
                label = _q(node_data["label"])
                lines.append(f'{indent}{macro}({safe_id(node["id"])}, "{label}") {{')
                self._emit_nodes(lines, children, node["id"], inside, indent + "    ")
                lines.append(f"{indent}}}")
            else:
                lines.append(indent + self._entity(node, inside))

    def _entity(self, node: GraphNode, inside: set[str]) -> str:
        """Render one leaf node as a C4 entity macro call.

        Externality for people and systems comes from the node kind (which
        the graph derives from ``location`` or an ``external`` tag); for
        containers and components it is whether they sit inside the view's
        scope boundary.
        """
        node_data = node["data"]
        kind = node_data["kind"]
        eid = safe_id(node["id"])
        name = _q(node_data["label"])
        description = _q(node_data.get("description", ""))

        if kind.startswith("person"):
            macro = "Person_Ext" if kind == "person-external" else "Person"
            return f'{macro}({eid}, "{name}", "{description}")'
        if kind in ("container", "component"):
            macro = kind.capitalize()
            if node["id"] not in inside:
                macro += "_Ext"
            technology = _q(node_data.get("technology", ""))
            return f'{macro}({eid}, "{name}", "{technology}", "{description}")'
        macro = "System_Ext" if kind == "system-external" else "System"
        return f'{macro}({eid}, "{name}", "{description}")'

    def _rel(self, edge: GraphEdge) -> str:
        edge_data = edge["data"]
        technology = edge_data.get("technology", "")
        tech = f', "{_q(technology)}"' if technology else ""
        label = _q(edge_data.get("label", ""))
        return (
            f"    Rel({safe_id(edge['source'])}, "
            f'{safe_id(edge["target"])}, "{label}"{tech})'
        )
