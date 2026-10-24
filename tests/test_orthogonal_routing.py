"""Orthogonal re-routing reaches every renderer (PP-196).

Dragging a segment of a Step / Smooth step line stores the route's
corners as the edge's waypoints and marks the edge in the sidecar's
``routing`` section. The canvas draws it from ``orthogonal.ts``; so must
``c4 render``, or a committed diagram would disagree with the screen. The
SVG tests read the drawn path back and check every segment is horizontal
or vertical — and, as a control, that the same layout without the flag is
not, so the check can fail.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from c4studio.layout_sidecar import read_routing
from c4studio.models import View, Workspace
from c4studio.parser.dsl import parse_dsl
from c4studio.render import RenderError, _payload_with_layout, node_executable
from c4studio.webapp.graph import react_flow_graph
from c4studio.webapp.server import create_app

DSL = """
workspace "W" {
    model {
        u = person "User"
        s = softwareSystem "S" {
            web = container "Web"
            api = container "API"
        }
        u -> web "Uses"
        web -> api "Calls"
    }
    views {
        container s "cont" {
            include *
        }
    }
}
"""

# Diagonal from one another, so an unrouted line between them is a slant.
# The boundary needs a place too: a payload missing any position makes
# both renderers discard the arrangement and lay out afresh.
POSITIONS = {
    "u": [0, 0],
    "s": [400, 300, 900, 800],
    "web": [500, 400],
    "api": [1000, 800],
}


def _node_available() -> bool:
    try:
        node_executable()
    except RenderError:
        return False
    return True


needs_node = pytest.mark.skipif(not _node_available(), reason="no node")


@pytest.fixture()
def source(tmp_path: Path) -> Path:
    path = tmp_path / "ws.dsl"
    path.write_text(DSL, encoding="utf-8")
    return path


@pytest.fixture()
def workspace() -> Workspace:
    return parse_dsl(DSL)


def _view(workspace: Workspace) -> View:
    return next(v for v in workspace.views if v.key == "cont")


def _edge_ids(workspace: Workspace) -> dict[str, str]:
    graph = react_flow_graph(workspace, _view(workspace))
    return {e["label"]: e["id"] for e in graph["edges"]}


def _write_sidecar(source: Path, document: dict[str, Any]) -> None:
    source.with_name(f"{source.stem}.layout.json").write_text(
        json.dumps({"version": 1, **document}), encoding="utf-8"
    )


def _edge_paths(svg: str) -> list[list[tuple[float, float]]]:
    """Every relationship line in the SVG, as its list of points."""
    paths = re.findall(r'<path d="([^"]+)"[^>]*marker-end=', svg)
    return [
        [(float(x), float(y)) for x, y in re.findall(r"([-\d.]+)[ ,]([-\d.]+)", d)]
        for d in paths
    ]


def _orthogonal(points: list[tuple[float, float]]) -> bool:
    return all(
        a[0] == b[0] or a[1] == b[1] for a, b in zip(points, points[1:], strict=False)
    )


class TestPayload:
    def test_routing_reaches_its_edge_and_no_other(
        self, workspace: Workspace, source: Path
    ) -> None:
        ids = _edge_ids(workspace)
        _write_sidecar(source, {"routing": {"cont": {ids["Calls"]: "orthogonal"}}})
        payload = _payload_with_layout(workspace, _view(workspace), source)
        by_id = {e["id"]: e for e in payload["edges"]}
        assert by_id[ids["Calls"]]["routing"] == "orthogonal"
        assert "routing" not in by_id[ids["Uses"]]

    def test_an_unknown_mode_is_dropped(self, source: Path) -> None:
        """A sidecar is read defensively; a mode we do not draw is noise."""
        _write_sidecar(
            source, {"routing": {"cont": {"a": "orthogonal", "b": "spline", "c": 3}}}
        )
        assert read_routing(source) == {"cont": {"a": "orthogonal"}}

    def test_a_sidecar_without_the_section_still_loads(self, source: Path) -> None:
        _write_sidecar(source, {"views": {"cont": {"u": [1, 2]}}})
        assert read_routing(source) == {}


class TestRendered:
    @needs_node
    def test_the_control_without_routing_is_diagonal(
        self, workspace: Workspace, source: Path
    ) -> None:
        """Without this, the orthogonality checks below could not fail."""
        from c4studio.render import render_view

        _write_sidecar(source, {"views": {"cont": POSITIONS}})
        svg = render_view(workspace, _view(workspace), layout_source=source)
        assert not all(_orthogonal(p) for p in _edge_paths(svg))

    @needs_node
    def test_a_rerouted_edge_with_no_corners_renders_orthogonal(
        self, workspace: Workspace, source: Path
    ) -> None:
        from c4studio.render import render_view

        ids = _edge_ids(workspace)
        _write_sidecar(
            source,
            {
                "views": {"cont": POSITIONS},
                "routing": {
                    "cont": {ids["Uses"]: "orthogonal", ids["Calls"]: "orthogonal"}
                },
            },
        )
        svg = render_view(workspace, _view(workspace), layout_source=source)
        paths = _edge_paths(svg)
        assert len(paths) == 2
        assert all(_orthogonal(p) for p in paths)
        # A diagonal pair needs at least one turn.
        assert all(len(p) >= 3 for p in paths)

    @needs_node
    def test_the_route_passes_through_its_stored_corners(
        self, workspace: Workspace, source: Path
    ) -> None:
        """What a segment drag stores is where the line goes."""
        from c4studio.render import render_view

        ids = _edge_ids(workspace)
        corners = [[640, 300], [640, 700]]
        _write_sidecar(
            source,
            {
                "views": {"cont": POSITIONS},
                "edges": {"cont": {ids["Calls"]: corners}},
                "routing": {"cont": {ids["Calls"]: "orthogonal"}},
            },
        )
        svg = render_view(workspace, _view(workspace), layout_source=source)
        routed = [p for p in _edge_paths(svg) if _orthogonal(p) and len(p) >= 3]
        assert routed, "no orthogonal path was drawn"
        # Coordinates in the SVG are offset by the canvas margin, so look
        # for the corners' *shape*: two points sharing an x, 400 apart.
        path = routed[0]
        xs = [x for x, _ in path]
        shared = {x for x in xs if xs.count(x) >= 2}
        assert any(
            abs(a[1] - b[1]) == 400
            for a, b in zip(path, path[1:], strict=False)
            if a[0] == b[0] and a[0] in shared
        )

    @needs_node
    def test_corners_that_do_not_line_up_still_render_orthogonal(
        self, workspace: Workspace, source: Path
    ) -> None:
        """Bend points placed in a curved style get an elbow between them."""
        from c4studio.render import render_view

        ids = _edge_ids(workspace)
        _write_sidecar(
            source,
            {
                "views": {"cont": POSITIONS},
                "edges": {"cont": {ids["Calls"]: [[600, 300], [900, 650]]}},
                "routing": {"cont": {ids["Calls"]: "orthogonal"}},
            },
        )
        svg = render_view(workspace, _view(workspace), layout_source=source)
        assert sum(_orthogonal(p) for p in _edge_paths(svg)) >= 1


DSL_FILE = "example.dsl"


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    (tmp_path / DSL_FILE).write_text(DSL, encoding="utf-8")
    return tmp_path


@pytest.fixture()
def client(root: Path) -> TestClient:
    client = TestClient(create_app(root=root))
    assert client.post("/api/load", json={"path": DSL_FILE}).status_code == 200
    return client


def _sidecar(root: Path) -> dict[str, Any]:
    path = root / "example.layout.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


class TestServer:
    def _ids(self, client: TestClient) -> dict[str, str]:
        graph = client.get("/api/views/cont/graph").json()
        return {e["label"]: e["id"] for e in graph["edges"]}

    def test_routing_is_saved_served_and_reloaded(
        self, client: TestClient, root: Path
    ) -> None:
        ids = self._ids(client)
        corners = [[640, 300], [640, 700]]
        response = client.post(
            "/api/views/cont/layout",
            json={
                "positions": {"u": [0, 0]},
                "waypoints": {ids["Calls"]: corners},
                "routing": {ids["Calls"]: "orthogonal"},
            },
        )
        assert response.status_code == 200
        assert _sidecar(root)["routing"] == {"cont": {ids["Calls"]: "orthogonal"}}

        by_id = {
            e["id"]: e for e in client.get("/api/views/cont/graph").json()["edges"]
        }
        assert by_id[ids["Calls"]]["routing"] == "orthogonal"
        assert by_id[ids["Calls"]]["waypoints"] == corners
        assert "routing" not in by_id[ids["Uses"]]

        fresh = TestClient(create_app(root=root))
        fresh.post("/api/load", json={"path": DSL_FILE})
        by_id = {e["id"]: e for e in fresh.get("/api/views/cont/graph").json()["edges"]}
        assert by_id[ids["Calls"]]["routing"] == "orthogonal"

    def test_a_save_without_the_edge_clears_its_routing(
        self, client: TestClient, root: Path
    ) -> None:
        """The whole view's map is sent, so absence is the reset."""
        ids = self._ids(client)
        client.post(
            "/api/views/cont/layout",
            json={"positions": {}, "routing": {ids["Calls"]: "orthogonal"}},
        )
        client.post("/api/views/cont/layout", json={"positions": {}, "routing": {}})
        assert "routing" not in _sidecar(root)
        edges = client.get("/api/views/cont/graph").json()["edges"]
        assert all("routing" not in e for e in edges)

    def test_reset_layout_clears_routing(self, client: TestClient, root: Path) -> None:
        ids = self._ids(client)
        client.post(
            "/api/views/cont/layout",
            json={"positions": {"u": [1, 2]}, "routing": {ids["Calls"]: "orthogonal"}},
        )
        assert client.delete("/api/views/cont/layout").status_code == 200
        assert "routing" not in _sidecar(root)
        edges = client.get("/api/views/cont/graph").json()["edges"]
        assert all("routing" not in e for e in edges)

    def test_saving_expansion_keeps_routing(
        self, client: TestClient, root: Path
    ) -> None:
        """Every sidecar write rewrites the file; none may drop the section."""
        ids = self._ids(client)
        client.post(
            "/api/views/cont/layout",
            json={"positions": {}, "routing": {ids["Calls"]: "orthogonal"}},
        )
        client.post("/api/views/cont/expansion", json={"expanded": [], "collapsed": []})
        assert _sidecar(root)["routing"] == {"cont": {ids["Calls"]: "orthogonal"}}


class TestPinnedSides:
    """Ends pinned to a side of their node (PP-201)."""

    def _pinned(self, client: TestClient, edge: str, **sides: str) -> Any:
        return client.post(
            "/api/views/cont/layout",
            json={
                "positions": {"u": [0, 0]},
                "routing": {edge: "orthogonal"},
                "sides": {edge: sides},
            },
        )

    def test_sides_are_saved_served_and_reloaded(
        self, client: TestClient, root: Path
    ) -> None:
        ids = TestServer()._ids(client)
        assert self._pinned(client, ids["Calls"], source="top").status_code == 200
        assert _sidecar(root)["sides"] == {"cont": {ids["Calls"]: {"source": "top"}}}
        by_id = {
            e["id"]: e for e in client.get("/api/views/cont/graph").json()["edges"]
        }
        assert by_id[ids["Calls"]]["sides"] == {"source": "top"}
        assert "sides" not in by_id[ids["Uses"]]

        fresh = TestClient(create_app(root=root))
        fresh.post("/api/load", json={"path": DSL_FILE})
        edges = fresh.get("/api/views/cont/graph").json()["edges"]
        assert {e["id"]: e.get("sides") for e in edges}[ids["Calls"]] == {
            "source": "top"
        }

    def test_a_pin_needs_a_rerouted_edge_and_a_real_side(
        self, client: TestClient, root: Path
    ) -> None:
        ids = TestServer()._ids(client)
        client.post(
            "/api/views/cont/layout",
            json={
                "positions": {},
                "routing": {ids["Calls"]: "orthogonal"},
                "sides": {
                    ids["Calls"]: {"source": "diagonal", "target": "left"},
                    ids["Uses"]: {"source": "top"},
                    "nope": {"middle": "top"},
                },
            },
        )
        assert _sidecar(root)["sides"] == {"cont": {ids["Calls"]: {"target": "left"}}}

    def test_reset_clears_sides(self, client: TestClient, root: Path) -> None:
        ids = TestServer()._ids(client)
        self._pinned(client, ids["Calls"], source="top")
        client.delete("/api/views/cont/layout")
        assert "sides" not in _sidecar(root)
        edges = client.get("/api/views/cont/graph").json()["edges"]
        assert all("sides" not in e for e in edges)

    def test_other_writes_keep_sides(self, client: TestClient, root: Path) -> None:
        ids = TestServer()._ids(client)
        self._pinned(client, ids["Calls"], source="top")
        client.post("/api/views/cont/expansion", json={"expanded": [], "collapsed": []})
        client.post("/api/views/cont/layouts", json={"name": "A"})
        assert _sidecar(root)["sides"] == {"cont": {ids["Calls"]: {"source": "top"}}}

    def test_named_layouts_capture_and_restore_sides(
        self, client: TestClient, root: Path
    ) -> None:
        ids = TestServer()._ids(client)
        self._pinned(client, ids["Calls"], source="top")
        client.post("/api/views/cont/layouts", json={"name": "Pinned"})
        self._pinned(client, ids["Calls"], source="bottom")
        client.post("/api/views/cont/layouts/apply", json={"name": "Pinned"})
        edges = client.get("/api/views/cont/graph").json()["edges"]
        assert {e["id"]: e.get("sides") for e in edges}[ids["Calls"]] == {
            "source": "top"
        }

    @needs_node
    def test_render_leaves_through_the_pinned_side(
        self, workspace: Workspace, source: Path
    ) -> None:
        """Unpinned, web -> api leaves sideways; pinned top, it goes up."""
        from c4studio.render import render_view

        ids = _edge_ids(workspace)

        def first_run(sides: dict[str, Any]) -> tuple[Any, Any]:
            _write_sidecar(
                source,
                {
                    "views": {"cont": POSITIONS},
                    "routing": {"cont": {ids["Calls"]: "orthogonal"}},
                    "sides": sides,
                },
            )
            svg = render_view(workspace, _view(workspace), layout_source=source)
            routed = [p for p in _edge_paths(svg) if _orthogonal(p) and len(p) >= 3]
            assert len(routed) == 1
            return routed[0][0], routed[0][1]

        a, b = first_run({})
        assert a[1] == b[1], "the control should leave horizontally"
        a, b = first_run({"cont": {ids["Calls"]: {"source": "top"}}})
        assert a[0] == b[0] and b[1] < a[1]
