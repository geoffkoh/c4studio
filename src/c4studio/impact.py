"""What else is involved when one thing changes (PP-189).

The change-advisory question, asked of the model rather than of whoever
remembers: *if this changes, what else is affected, and which diagrams do
I have to look at?*

Two directions, kept apart because they answer different questions:

- **dependents** — things that reach this element, and so may break when
  it changes. What a CAB wants.
- **dependencies** — things this element reaches, and so may break it.
  What an on-call engineer wants.

Containment counts as involvement in both directions. Changing a software
system changes everything inside it, and a relationship declared against
a container is a relationship its system participates in — which is why
views lift relationships to the nearest visible ancestor, and why an
answer that ignored the hierarchy would disagree with the diagrams it is
about.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass, field

from c4studio.models import Workspace

#: Which way to walk the model.
Direction = str  # "dependents" | "dependencies"


@dataclass(frozen=True)
class Node:
    """One element in the model's containment tree.

    Attributes:
        id: The element's id.
        name: Its name.
        kind: The DSL keyword that declared it.
        parent: Id of the element that contains it, if any.
    """

    id: str
    name: str
    kind: str
    parent: str | None = None


@dataclass(frozen=True)
class Hop:
    """One element reached by the walk.

    Attributes:
        id: The element reached.
        name: Its name.
        kind: Its kind.
        depth: How many relationships away it is — 1 is a direct
            neighbour.
        via: The element it was reached from, which is the readable half
            of a path without carrying whole paths around.
    """

    id: str
    name: str
    kind: str
    depth: int
    via: str


@dataclass
class Impact:
    """The answer for one element.

    Attributes:
        element: The element asked about.
        dependents: What reaches it, nearest first.
        dependencies: What it reaches, nearest first.
        views: Keys of the views that draw the element, in workspace
            order.
    """

    element: Node
    dependents: list[Hop] = field(default_factory=list)
    dependencies: list[Hop] = field(default_factory=list)
    views: list[str] = field(default_factory=list)


def nodes(workspace: Workspace) -> Iterator[Node]:
    """Every person, system, container and component."""
    for person in workspace.model.people:
        yield Node(person.id, person.name, "person")
    for system in workspace.model.software_systems:
        yield Node(system.id, system.name, "softwareSystem")
        for container in system.containers:
            yield Node(container.id, container.name, "container", system.id)
            for component in container.components:
                yield Node(component.id, component.name, "component", container.id)


def _index(workspace: Workspace) -> dict[str, Node]:
    return {node.id: node for node in nodes(workspace)}


def _descendants(index: dict[str, Node], root: str) -> set[str]:
    """``root`` and everything contained in it, at any depth."""
    children: dict[str, list[str]] = {}
    for node in index.values():
        if node.parent:
            children.setdefault(node.parent, []).append(node.id)
    found = {root}
    queue = deque([root])
    while queue:
        for child in children.get(queue.popleft(), []):
            if child not in found:
                found.add(child)
                queue.append(child)
    return found


def _ancestors(index: dict[str, Node], start: str) -> set[str]:
    """Every element that contains ``start``."""
    found: set[str] = set()
    parent = index[start].parent if start in index else None
    while parent:
        found.add(parent)
        parent = index[parent].parent if parent in index else None
    return found


def _edges(workspace: Workspace) -> list[tuple[str, str]]:
    """Declared relationships as (source, destination).

    Implied relationships are skipped: they duplicate what the
    containment rules below already infer, and counting both would report
    the same involvement twice.
    """
    return [
        (relationship.source_id, relationship.destination_id)
        for relationship in workspace.relationships
        if not relationship.linked_relationship_id
    ]


def _walk(
    index: dict[str, Node],
    edges: list[tuple[str, str]],
    start: str,
    direction: Direction,
    depth: int | None,
) -> list[Hop]:
    """Breadth-first from ``start``, nearest first."""
    outgoing: dict[str, list[str]] = {}
    for source, destination in edges:
        if direction == "dependencies":
            outgoing.setdefault(source, []).append(destination)
        else:
            outgoing.setdefault(destination, []).append(source)

    # A relationship touching a child touches its ancestors too, and a
    # change to a parent reaches its children: both are the containment
    # rule the views apply when they lift an edge.
    def related(element_id: str) -> set[str]:
        family = _descendants(index, element_id) | _ancestors(index, element_id)
        reached: set[str] = set()
        for member in family:
            reached.update(outgoing.get(member, ()))
        return {
            ancestor
            for target in reached
            for ancestor in ({target} | _ancestors(index, target))
        } | reached

    seen = {start} | _descendants(index, start) | _ancestors(index, start)
    hops: list[Hop] = []
    frontier = [(start, 0)]
    while frontier:
        current, distance = frontier.pop(0)
        if depth is not None and distance >= depth:
            continue
        for target in sorted(related(current)):
            if target in seen or target not in index:
                continue
            seen.add(target)
            node = index[target]
            hops.append(Hop(node.id, node.name, node.kind, distance + 1, current))
            frontier.append((target, distance + 1))
    return hops


def views_containing(workspace: Workspace, element_id: str) -> list[str]:
    """Keys of the views that draw ``element_id``.

    Asked of the same graph builder the viewer and the renderer use, so
    the answer names the diagrams a person would actually open rather
    than the ones a simpler rule would guess at.
    """
    from c4studio.graph.view_graph import build_view_graph
    from c4studio.webapp.graph import is_supported

    keys: list[str] = []
    for view in workspace.views:
        if not is_supported(view):
            continue
        try:
            data = build_view_graph(workspace, view)
        except Exception:  # noqa: BLE001 - a broken view must not break the answer
            continue
        if any(node["id"] == element_id for node in data["nodes"]):
            keys.append(view.key)
    return keys


def analyse(
    workspace: Workspace,
    element_id: str,
    depth: int | None = None,
) -> Impact:
    """Work out what else is involved when ``element_id`` changes.

    Args:
        workspace: The parsed workspace.
        element_id: The element to ask about, by its DSL identifier.
        depth: Stop after this many relationships; ``None`` walks to the
            end of the graph.

    Returns:
        The dependents, the dependencies and the views that draw it.

    Raises:
        KeyError: If no element has that id.
    """
    index = _index(workspace)
    if element_id not in index:
        raise KeyError(element_id)
    edges = _edges(workspace)
    return Impact(
        element=index[element_id],
        dependents=_walk(index, edges, element_id, "dependents", depth),
        dependencies=_walk(index, edges, element_id, "dependencies", depth),
        views=views_containing(workspace, element_id),
    )


def to_dict(impact: Impact) -> dict[str, object]:
    """The answer as JSON-ready data, for scripts and tickets."""

    def hop(item: Hop) -> dict[str, object]:
        return {
            "id": item.id,
            "name": item.name,
            "kind": item.kind,
            "depth": item.depth,
            "via": item.via,
        }

    return {
        "element": {
            "id": impact.element.id,
            "name": impact.element.name,
            "kind": impact.element.kind,
        },
        "dependents": [hop(h) for h in impact.dependents],
        "dependencies": [hop(h) for h in impact.dependencies],
        "views": list(impact.views),
    }
