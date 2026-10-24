"""Reading the layout sidecar (PP-180).

``<workspace>.layout.json`` holds the arrangement a person made of their
diagrams: dragged positions, resized boundaries, edge waypoints, dragged
label offsets, expanded and collapsed groups, and moved title/legend
chrome. It is per-user UI state, gitignored, and written next to the
source file.

The reading lived inside ``webapp/server.py``, which is why ``c4 render``
knew nothing about any of it and drew a fresh auto-layout instead of the
diagram you arranged. It lives here so the server and the renderer share
one implementation rather than two that drift — the failure this
repository keeps meeting (``dsl.py`` and ``highlight.ts``, the committed
bundle and its source, the legend and the diagram).

**Sections are top-level and additive**, which is the compatibility
contract: a sidecar written by an older version simply has no ``labels``
or ``chrome`` key and still loads. Every reader here returns an empty
mapping for anything it cannot use, because a sidecar is disposable UI
state — a corrupt one must cost you your arrangement, never your render.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

#: Sections holding ``{view_key: [element_id, ...]}`` lists.
ID_SECTIONS = ("expanded", "collapsed")


def sidecar_path(source: Path) -> Path:
    """Path of the layout sidecar stored next to a workspace source.

    Args:
        source: The workspace's root source file.

    Returns:
        The sidecar path, which need not exist.
    """
    return source.with_name(f"{source.stem}.layout.json")


def read_document(source: Path) -> dict[str, Any]:
    """Read and parse the whole sidecar, or ``{}`` if it is unusable.

    Args:
        source: The workspace's root source file.

    Returns:
        The parsed document, or an empty dict when absent or malformed.
    """
    sidecar = sidecar_path(source)
    if not sidecar.is_file():
        return {}
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def read_positions(source: Path) -> dict[str, dict[str, list[int]]]:
    """Read ``{view_key: {element_id: [x, y] | [x, y, w, h]}}``."""
    views = read_document(source).get("views")
    return views if isinstance(views, dict) else {}


def read_waypoints(source: Path) -> dict[str, dict[str, list[list[int]]]]:
    """Read ``{view_key: {edge_id: [[x, y], ...]}}`` bend points."""
    edges = read_document(source).get("edges")
    if not isinstance(edges, dict):
        return {}
    cleaned: dict[str, dict[str, list[list[int]]]] = {}
    for key, by_edge in edges.items():
        if not isinstance(by_edge, dict):
            continue
        points = {
            edge_id: [[int(p[0]), int(p[1])] for p in pts]
            for edge_id, pts in by_edge.items()
            if isinstance(pts, list)
            and all(isinstance(p, list) and len(p) == 2 for p in pts)
        }
        if points:
            cleaned[key] = points
    return cleaned


#: The routing modes the ``routing`` section may record. Only orthogonal
#: exists: an edge without an entry follows the viewer's own line style.
ROUTING_MODES = frozenset({"orthogonal"})


def read_routing(source: Path) -> dict[str, dict[str, str]]:
    """Read ``{view_key: {edge_id: "orthogonal"}}`` re-routed edges.

    An edge listed here was re-routed by dragging its segments (PP-196):
    its ``edges`` waypoints are the corners of an orthogonal route, and
    every renderer draws it that way whatever line style is selected.
    Unknown modes are dropped, like anything else a reader cannot use.
    """
    raw = read_document(source).get("routing")
    if not isinstance(raw, dict):
        return {}
    cleaned: dict[str, dict[str, str]] = {}
    for key, by_edge in raw.items():
        if not isinstance(by_edge, dict):
            continue
        modes = {
            edge_id: mode
            for edge_id, mode in by_edge.items()
            if isinstance(edge_id, str) and mode in ROUTING_MODES
        }
        if modes:
            cleaned[key] = modes
    return cleaned


def read_labels(source: Path) -> dict[str, dict[str, list[int]]]:
    """Read ``{view_key: {edge_id: [dx, dy]}}`` label offsets."""
    return _read_points(source, "labels")


def read_chrome(source: Path) -> dict[str, dict[str, list[int]]]:
    """Read ``{view_key: {"title" | "legend": [x, y]}}`` chrome positions."""
    return _read_points(source, "chrome")


def _read_points(source: Path, section: str) -> dict[str, dict[str, list[int]]]:
    """Read a section of ``{view_key: {name: [x, y]}}`` pairs."""
    raw = read_document(source).get(section)
    if not isinstance(raw, dict):
        return {}
    cleaned: dict[str, dict[str, list[int]]] = {}
    for key, by_name in raw.items():
        if not isinstance(by_name, dict):
            continue
        points = {
            name: [int(point[0]), int(point[1])]
            for name, point in by_name.items()
            if isinstance(point, list) and len(point) == 2
        }
        if points:
            cleaned[key] = points
    return cleaned


def read_ids(source: Path, section: str) -> dict[str, list[str]]:
    """Read a section of ``{view_key: [id, ...]}`` string lists.

    Backs ``expanded`` and ``collapsed``.

    Args:
        source: The workspace's root source file.
        section: The top-level section name.

    Returns:
        Per-view id lists, empty entries dropped.
    """
    raw = read_document(source).get(section)
    if not isinstance(raw, dict):
        return {}
    cleaned: dict[str, list[str]] = {}
    for key, ids in raw.items():
        if isinstance(ids, list):
            wanted = [i for i in ids if isinstance(i, str) and i]
            if wanted:
                cleaned[key] = wanted
    return cleaned


def attach_waypoints(
    data: dict[str, Any], waypoints: dict[str, list[list[int]]]
) -> None:
    """Add saved bend points onto matching edges of a graph payload.

    Edges whose id no longer appears in the view are simply skipped: the
    stale entry stays in the sidecar until that view's layout is saved
    again, and never reaches the client.
    """
    if not waypoints:
        return
    for edge in data.get("edges", []):
        points = waypoints.get(edge.get("id", ""))
        if points:
            edge["waypoints"] = [[int(x), int(y)] for x, y in points]


def attach_routing(data: dict[str, Any], routing: dict[str, str]) -> None:
    """Mark re-routed edges of a graph payload with their routing mode.

    Stale ids are skipped, as for waypoints.
    """
    if not routing:
        return
    for edge in data.get("edges", []):
        mode = routing.get(edge.get("id", ""))
        if mode in ROUTING_MODES:
            edge["routing"] = mode


def attach_labels(data: dict[str, Any], labels: dict[str, list[int]]) -> None:
    """Add saved label offsets onto matching edges of a graph payload.

    Stale ids are skipped exactly as waypoints are: the entry stays in the
    sidecar until that view's layout is saved again, and never reaches the
    client.
    """
    if not labels:
        return
    for edge in data.get("edges", []):
        offset = labels.get(edge.get("id", ""))
        if offset:
            edge["labelOffset"] = [int(offset[0]), int(offset[1])]


#: The per-view sections a named layout (PP-197) captures. A snapshot holds
#: each one's value *for its view* under the same name, so applying it is a
#: copy back into the working sections and nothing needs translating.
SNAPSHOT_SECTIONS = (
    "views",
    "edges",
    "labels",
    "expanded",
    "collapsed",
    "chrome",
    "routing",
)


def read_snapshots(source: Path) -> dict[str, dict[str, dict[str, Any]]]:
    """Read ``{view_key: {name: snapshot}}`` named layouts.

    A snapshot is ``{section: value, "savedAt": iso}`` for the sections in
    :data:`SNAPSHOT_SECTIONS`. Only the outer shape is checked here: what a
    snapshot holds is checked by the section readers once it is applied,
    because applying writes it into the working sections they read.

    Args:
        source: The workspace's root source file.

    Returns:
        Per-view named snapshots, unusable entries dropped.
    """
    raw = read_document(source).get("snapshots")
    if not isinstance(raw, dict):
        return {}
    cleaned: dict[str, dict[str, dict[str, Any]]] = {}
    for key, by_name in raw.items():
        if not isinstance(by_name, dict):
            continue
        named = {
            name: {
                field: value
                for field, value in snapshot.items()
                if field in SNAPSHOT_SECTIONS or field == "savedAt"
            }
            for name, snapshot in by_name.items()
            if isinstance(name, str) and name and isinstance(snapshot, dict)
        }
        if named:
            cleaned[key] = named
    return cleaned
