"""`c4 render` honours the layout sidecar (PP-180).

Rendering called `react_flow_graph(workspace, view)` with no layout at
all, so a rendered SVG was a fresh auto-layout rather than the diagram
that had been arranged in the Studio. The sidecar reading lived inside
`webapp/server.py`, which is why: one implementation, reachable from one
place.

Most of this tests the payload rather than the SVG. The payload is where
the sidecar is applied and it needs no Node; the two end-to-end tests
below cover the part only a render can show.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from c4studio.models import View, Workspace
from c4studio.parser.dsl import parse_dsl
from c4studio.render import RenderError, _payload_with_layout, node_executable
from c4studio.webapp.graph import react_flow_graph

DSL = """
workspace "W" {
    model {
        u = person "User"
        s = softwareSystem "S" {
            group "Backend" {
                api = container "API"
                worker = container "Worker"
            }
            web = container "Web"
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

GROUP_ID = "__group__s__Backend"


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


def _write_sidecar(source: Path, document: dict[str, Any]) -> None:
    source.with_name(f"{source.stem}.layout.json").write_text(
        json.dumps(document), encoding="utf-8"
    )


def _node(payload: dict[str, Any], node_id: str) -> dict[str, Any]:
    return next(n for n in payload["nodes"] if n["id"] == node_id)


class TestWithoutASidecar:
    def test_no_layout_source_renders_a_fresh_auto_layout(
        self, workspace: Workspace, source: Path
    ) -> None:
        """What `--no-layout` asks for, and what keeps output portable."""
        _write_sidecar(source, {"views": {"cont": {"api": [11, 22]}}})
        payload = _payload_with_layout(workspace, _view(workspace), None)
        assert all("position" not in node for node in payload["nodes"])

    def test_a_missing_sidecar_changes_nothing(
        self, workspace: Workspace, source: Path
    ) -> None:
        arranged = _payload_with_layout(workspace, _view(workspace), source)
        assert arranged == react_flow_graph(parse_dsl(DSL), _view(parse_dsl(DSL)))

    def test_an_unreadable_sidecar_costs_the_arrangement_not_the_render(
        self, workspace: Workspace, source: Path
    ) -> None:
        """A sidecar is disposable UI state; a render is the artefact."""
        source.with_name("ws.layout.json").write_text("{not json", encoding="utf-8")
        payload = _payload_with_layout(workspace, _view(workspace), source)
        assert payload["nodes"]


class TestSections:
    def test_positions_and_sizes_are_applied(
        self, workspace: Workspace, source: Path
    ) -> None:
        _write_sidecar(
            source,
            {
                "views": {
                    "cont": {
                        "api": [11, 22],
                        # Only a boundary carries a size: it is the one
                        # thing the user can resize.
                        GROUP_ID: [33, 44, 300, 200],
                    }
                }
            },
        )
        payload = _payload_with_layout(workspace, _view(workspace), source)
        assert _node(payload, "api")["position"] == {"x": 11, "y": 22}
        group = _node(payload, GROUP_ID)
        assert group["position"] == {"x": 33, "y": 44}
        assert group["size"] == {"width": 300, "height": 200}

    def test_a_group_boundary_gets_its_stored_position(
        self, workspace: Workspace, source: Path
    ) -> None:
        """PP-181: it is synthesised after placement, so it used to get a
        size and no position — and a payload missing any position makes
        both renderers throw the arrangement away and lay out afresh."""
        _write_sidecar(source, {"views": {"cont": {GROUP_ID: [70, 90]}}})
        payload = _payload_with_layout(workspace, _view(workspace), source)
        assert _node(payload, GROUP_ID)["position"] == {"x": 70, "y": 90}

    def test_waypoints_and_label_offsets_reach_their_edges(
        self, workspace: Workspace, source: Path
    ) -> None:
        plain = react_flow_graph(workspace, _view(workspace))
        edge_id = next(e["id"] for e in plain["edges"] if e["label"] == "Calls")
        _write_sidecar(
            source,
            {
                "edges": {"cont": {edge_id: [[5, 6], [7, 8]]}},
                "labels": {"cont": {edge_id: [0, -40]}},
            },
        )
        payload = _payload_with_layout(workspace, _view(workspace), source)
        edge = next(e for e in payload["edges"] if e["id"] == edge_id)
        assert edge["waypoints"] == [[5, 6], [7, 8]]
        assert edge["labelOffset"] == [0, -40]

    def test_a_stale_edge_id_is_skipped_rather_than_failing(
        self, workspace: Workspace, source: Path
    ) -> None:
        """The entry stays in the sidecar until that view is saved again."""
        _write_sidecar(source, {"edges": {"cont": {"gone__missing__0": [[1, 2]]}}})
        payload = _payload_with_layout(workspace, _view(workspace), source)
        assert all("waypoints" not in edge for edge in payload["edges"])

    def test_collapsed_groups_are_applied(
        self, workspace: Workspace, source: Path
    ) -> None:
        _write_sidecar(source, {"collapsed": {"cont": [GROUP_ID]}})
        payload = _payload_with_layout(workspace, _view(workspace), source)
        ids = {node["id"] for node in payload["nodes"]}
        assert GROUP_ID in ids
        # Its members are gone, which is what collapsing means.
        assert "api" not in ids and "worker" not in ids

    def test_dragged_chrome_is_carried(
        self, workspace: Workspace, source: Path
    ) -> None:
        _write_sidecar(
            source, {"chrome": {"cont": {"title": [10, -20], "legend": [30, 400]}}}
        )
        payload = _payload_with_layout(workspace, _view(workspace), source)
        assert payload["chrome"] == {"title": [10, -20], "legend": [30, 400]}

    def test_another_view_s_layout_is_not_borrowed(
        self, workspace: Workspace, source: Path
    ) -> None:
        _write_sidecar(source, {"views": {"other": {"api": [11, 22]}}})
        payload = _payload_with_layout(workspace, _view(workspace), source)
        assert "position" not in _node(payload, "api")


class TestRendered:
    @needs_node
    def test_the_svg_follows_the_sidecar(
        self, workspace: Workspace, source: Path
    ) -> None:
        from c4studio.render import render_view

        plain = react_flow_graph(workspace, _view(workspace))
        positions = {
            node["id"]: [80, 60 + 400 * index]
            for index, node in enumerate(plain["nodes"])
        }
        _write_sidecar(source, {"views": {"cont": positions}})
        arranged = render_view(workspace, _view(workspace), layout_source=source)
        fresh = render_view(parse_dsl(DSL), _view(parse_dsl(DSL)))
        assert arranged != fresh
        # Stacked in a column, so the arranged canvas is the taller one.
        assert _height(arranged) > _height(fresh)

    @needs_node
    def test_no_layout_matches_a_workspace_that_was_never_arranged(
        self, workspace: Workspace, source: Path
    ) -> None:
        from c4studio.render import render_view

        _write_sidecar(source, {"views": {"cont": {"api": [900, 900]}}})
        assert render_view(
            workspace, _view(workspace), layout_source=None
        ) == render_view(parse_dsl(DSL), _view(parse_dsl(DSL)))


def _height(svg: str) -> float:
    import re

    match = re.search(r'height="([\d.]+)"', svg)
    assert match
    return float(match.group(1))
