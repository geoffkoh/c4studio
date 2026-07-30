"""
Mermaid ``flowchart`` diagram generator.

Mermaid's C4 diagram types (``C4Context`` and friends, see
:mod:`pystructurizr.generators.mermaid`) are experimental upstream, lay out
poorly on dense models, and GitHub pins its own Mermaid version.
``flowchart`` with ``subgraph`` has rendered reliably for years, so this
target takes the same graph model in and emits syntax that works where the
audience already reads.

It also covers every view type the graph builder supports — dynamic
(numbered steps), deployment (nested deployment nodes) and filtered views
included — which the C4 target does not.

Deliberately conservative about syntax, because the renderer is somebody
else's pinned version: ``<br/>`` is the only markup in labels (no ``<b>``,
which needs ``htmlLabels``), styling is plain ``classDef``
fill/stroke/colour, and every node is declared before the first edge so no
edge can create a stray node outside its subgraph.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pystructurizr.generators.mermaid_common import (
    children_by_parent,
    safe_id,
    view_title,
)
from pystructurizr.graph.view_graph import (
    KIND_COLOURS,
    GraphEdge,
    GraphNode,
    build_view_graph,
    rank_direction,
)
from pystructurizr.models import Shape, View, ViewType, Workspace


# Custom and image views hold author-supplied content rather than model
# elements, so there is nothing to lay out.
_UNSUPPORTED: frozenset[ViewType] = frozenset({ViewType.CUSTOM, ViewType.IMAGE})

_Delimiters = tuple[str, str]

_BOX: _Delimiters = ("[", "]")

# Node shape per element kind, before any style-declared shape.
_KIND_SHAPES: dict[str, _Delimiters] = {
    "person": ("([", "])"),
    "person-external": ("([", "])"),
    "infrastructure": ("{{", "}}"),
}

# Structurizr `shape` style property → the nearest flowchart shape. Shapes
# with no reasonable equivalent (terminals, mobile devices) keep the box.
_STYLE_SHAPES: dict[str, _Delimiters] = {
    Shape.CYLINDER.value: ("[(", ")]"),
    Shape.BUCKET.value: ("[(", ")]"),
    Shape.PIPE.value: ("[(", ")]"),
    Shape.CIRCLE.value: ("((", "))"),
    Shape.ELLIPSE.value: ("((", "))"),
    Shape.HEXAGON.value: ("{{", "}}"),
    Shape.DIAMOND.value: ("{", "}"),
    Shape.ROUNDED_BOX.value: ("(", ")"),
    Shape.PERSON.value: ("([", "])"),
    Shape.ROBOT.value: ("([", "])"),
    Shape.FOLDER.value: ("[[", "]]"),
    Shape.WEB_BROWSER.value: ("[[", "]]"),
    Shape.WINDOW.value: ("[[", "]]"),
    Shape.COMPONENT.value: ("[[", "]]"),
}

# The C4 kind shown in an element's metadata line.
_KIND_LABELS: dict[str, str] = {
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

# Flowchart keywords. A DSL alias is free to be `end` or `graph`, and using
# one bare as a node id derails the parser — `end` would close the enclosing
# subgraph — so those ids get a suffix.
_RESERVED_IDS: frozenset[str] = frozenset(
    {
        "end",
        "graph",
        "flowchart",
        "subgraph",
        "class",
        "classdef",
        "click",
        "style",
        "linkstyle",
        "direction",
    }
)

_BOUNDARY_CLASS = "boundary"
_BOUNDARY_COLOUR = "#90a4ae"
_DEFAULT_FILL = "#607d8b"
_DEFAULT_TEXT_COLOUR = "#ffffff"

# Mermaid reads `#nnn;`-style entities inside labels, so `#` is escaped
# first or it would corrupt the entities added after it.
_LABEL_ESCAPES: tuple[tuple[str, str], ...] = (
    ("#", "#35;"),
    ('"', "#quot;"),
    ("<", "#lt;"),
    (">", "#gt;"),
)


def _node_id(raw: str) -> str:
    """Mermaid node id for an element id, avoiding flowchart keywords."""
    identifier = safe_id(raw)
    return f"{identifier}_" if identifier.lower() in _RESERVED_IDS else identifier


def _escape(text: str) -> str:
    """Escape label text for a quoted Mermaid label, collapsing whitespace."""
    for raw, entity in _LABEL_ESCAPES:
        text = text.replace(raw, entity)
    return " ".join(text.split())


def _darken(colour: str, factor: float = 0.72) -> str:
    """Return ``colour`` scaled towards black, for a node's stroke.

    Anything that is not a 3- or 6-digit hex colour passes through
    unchanged — themes are external data and may hold named colours.
    """
    if not colour.startswith("#"):
        return colour
    digits = colour[1:]
    if len(digits) == 3:
        digits = "".join(ch * 2 for ch in digits)
    if len(digits) != 6:
        return colour
    try:
        channels = [int(digits[i : i + 2], 16) for i in (0, 2, 4)]
    except ValueError:
        return colour
    return "#" + "".join(f"{int(channel * factor):02x}" for channel in channels)


@dataclass
class _Palette:
    """The classes one diagram uses, built while its nodes are emitted.

    Kept per render (not on the generator) so nothing leaks between views,
    and ordered by first appearance so output stays byte-stable.
    """

    definitions: dict[str, str] = field(default_factory=dict)
    members: dict[str, list[str]] = field(default_factory=dict)
    _names: dict[tuple[str, str], str] = field(default_factory=dict)

    def assign(self, node_id: str, fill: str, text: str) -> None:
        """Put ``node_id`` in the class for this colour pair, defining it if new."""
        name = self._names.get((fill, text))
        if name is None:
            name = f"c{len(self._names)}"
            self._names[(fill, text)] = name
            self.definitions[name] = f"fill:{fill},stroke:{_darken(fill)},color:{text}"
        self.members.setdefault(name, []).append(node_id)

    def assign_boundary(self, node_id: str) -> None:
        self.definitions.setdefault(
            _BOUNDARY_CLASS,
            f"fill:none,stroke:{_BOUNDARY_COLOUR},color:{_BOUNDARY_COLOUR}",
        )
        self.members.setdefault(_BOUNDARY_CLASS, []).append(node_id)


class FlowchartGenerator:
    """Generate Mermaid ``flowchart`` diagrams from a Workspace."""

    def __init__(self, workspace: Workspace) -> None:
        self.workspace = workspace

    def generate_all(self) -> dict[str, str]:
        """Return a mapping of view key → mermaid diagram string."""
        return {v.key: self.generate_view(v) for v in self.workspace.views}

    def generate_view(self, view: View) -> str:
        """Render one view as a Mermaid flowchart."""
        if view.type in _UNSUPPORTED:
            return f"%%  View type {view.type} is not yet supported\n"

        data = build_view_graph(self.workspace, view)
        nodes: list[GraphNode] = data["nodes"]
        children = children_by_parent(nodes)
        populated = _populated_boundaries(children)
        palette = _Palette()

        title = view_title(self.workspace, view).replace('"', '\\"')
        lines: list[str] = [
            "---",
            f'title: "{title}"',
            "---",
            f"flowchart {rank_direction(self.workspace, view)}",
        ]
        self._emit_nodes(lines, children, None, populated, palette, indent="    ")

        edges: list[GraphEdge] = data["edges"]
        if edges:
            lines.append("")
            lines.extend(self._edge(edge) for edge in edges)

        self._emit_classes(lines, palette)
        return "\n".join(lines) + "\n"

    # ------------------------------------------------------------------
    # Nodes
    # ------------------------------------------------------------------

    def _emit_nodes(
        self,
        lines: list[str],
        children: dict[str | None, list[GraphNode]],
        parent: str | None,
        populated: set[str],
        palette: _Palette,
        indent: str,
    ) -> None:
        """Emit ``parent``'s children, recursing into boundaries as subgraphs."""
        for node in children.get(parent, []):
            node_id = _node_id(node["id"])
            node_data = node["data"]
            if node_data.get("kind") == "boundary":
                # An empty subgraph renders as a stray floating box.
                if node["id"] not in populated:
                    continue
                label = self._boundary_label(node_data)
                lines.append(f'{indent}subgraph {node_id}["{label}"]')
                self._emit_nodes(
                    lines, children, node["id"], populated, palette, indent + "    "
                )
                lines.append(f"{indent}end")
                palette.assign_boundary(node_id)
            else:
                open_delimiter, close_delimiter = _shape(node_data)
                label = self._element_label(node_data)
                lines.append(
                    f'{indent}{node_id}{open_delimiter}"{label}"{close_delimiter}'
                )
                palette.assign(node_id, *_colours(node_data))

    def _boundary_label(self, node_data: dict[str, object]) -> str:
        """Boundary label: its name plus the kind of boundary it is."""
        label = _escape(str(node_data.get("label", "")))
        kind = str(node_data.get("boundaryLabel", ""))
        if not kind or kind == "Group":
            return label
        technology = _escape(str(node_data.get("technology", "")))
        detail = f"{kind}: {technology}" if technology else kind
        return f"{label}<br/>[{detail}]"

    def _element_label(self, node_data: dict[str, object]) -> str:
        """Element label: name, ``[Kind: Technology]``, then description."""
        parts = [_escape(str(node_data.get("label", "")))]
        kind_label = _KIND_LABELS.get(str(node_data.get("kind", "")))
        technology = _escape(str(node_data.get("technology", "")))
        if kind_label:
            detail = f"{kind_label}: {technology}" if technology else kind_label
            parts.append(f"[{detail}]")
        description = _escape(str(node_data.get("description", "")))
        if description:
            parts.append(description)
        return "<br/>".join(parts)

    # ------------------------------------------------------------------
    # Edges
    # ------------------------------------------------------------------

    def _edge(self, edge: GraphEdge) -> str:
        """One relationship as an arrow, technology folded into the label."""
        edge_data = edge["data"]
        label = _escape(str(edge_data.get("label", "")))
        technology = _escape(str(edge_data.get("technology", "")))
        if technology:
            label = f"{label}<br/>[{technology}]" if label else f"[{technology}]"
        source, target = _node_id(edge["source"]), _node_id(edge["target"])
        if not label:
            return f"    {source} --> {target}"
        return f'    {source} -->|"{label}"| {target}'

    # ------------------------------------------------------------------
    # Styling
    # ------------------------------------------------------------------

    def _emit_classes(self, lines: list[str], palette: _Palette) -> None:
        """Declare the classes this diagram used, then assign nodes to them."""
        if not palette.members:
            return
        lines.append("")
        for name, definition in palette.definitions.items():
            lines.append(f"    classDef {name} {definition}")
        for name, node_ids in palette.members.items():
            lines.append(f"    class {','.join(node_ids)} {name}")


def _colours(node_data: dict[str, object]) -> tuple[str, str]:
    """Fill and text colour for a node.

    The same resolution the web app uses: a tag-based style's
    ``background``/``color`` when the workspace or a theme declares one,
    else the element-kind palette.
    """
    kind = str(node_data.get("kind", ""))
    fill = str(node_data.get("background") or KIND_COLOURS.get(kind, _DEFAULT_FILL))
    text = str(node_data.get("textColor") or _DEFAULT_TEXT_COLOUR)
    return fill, text


def _populated_boundaries(children: dict[str | None, list[GraphNode]]) -> set[str]:
    """Boundary ids that (transitively) contain at least one element."""
    populated: set[str] = set()

    def walk(parent: str | None) -> bool:
        holds_element = False
        for node in children.get(parent, []):
            if node["data"].get("kind") == "boundary":
                if walk(node["id"]):
                    populated.add(node["id"])
                    holds_element = True
            else:
                holds_element = True
        return holds_element

    walk(None)
    return populated


def _shape(node_data: dict[str, object]) -> _Delimiters:
    """Node delimiters: a style-declared shape wins over the kind default."""
    shape = node_data.get("shape")
    if isinstance(shape, str) and shape in _STYLE_SHAPES:
        return _STYLE_SHAPES[shape]
    return _KIND_SHAPES.get(str(node_data.get("kind", "")), _BOX)
