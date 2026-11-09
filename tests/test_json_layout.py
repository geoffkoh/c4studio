"""A layout saved in workspace JSON is drawn as Structurizr drew it (PP-220).

Structurizr keeps each view's arrangement in the JSON: element ``x``/``y``
and, per line, ``relationships[].vertices``. c4studio dropped all of it.
The parser kept only the elements' ids and never read a vertex, and the
exporter never wrote one, so a diagram arranged in Structurizr came back
laid out from scratch.

Three things beyond reading the numbers make the layout land:

- Structurizr stores no position for a boundary. Both renderers fit one
  around its children instead of falling back to auto-layout.
- The coordinates are corners of Structurizr's boxes, 450x300 unless a style
  says otherwise, so the elements are drawn at that size.
- A view Structurizr would lay out afresh (``automaticLayout``, or every
  element at 0,0, which is what the Java library writes for a view nobody
  arranged) keeps no positions, as ``structurizr-diagram.js`` decides it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from c4studio.generators.json_export import export_json
from c4studio.models import Workspace
from c4studio.parser.json_parser import STRUCTURIZR_ELEMENT_SIZE, parse_json
from c4studio.render import RenderError, _payload_with_layout, node_executable
from c4studio.webapp.graph import react_flow_graph


def _node_available() -> bool:
    try:
        node_executable()
    except RenderError:
        return False
    return True


needs_node = pytest.mark.skipif(not _node_available(), reason="no node")

# The shape Structurizr writes: numeric ids, an implied relationship (7)
# standing for 5 at system level, and positions plus vertices per view.
WORKSPACE: dict[str, Any] = {
    "workspace": {
        "name": "W",
        "model": {
            "people": [
                {
                    "id": "1",
                    "name": "User",
                    "tags": "Element,Person,Staff",
                    "relationships": [
                        {
                            "id": "5",
                            "sourceId": "1",
                            "destinationId": "3",
                            "description": "Uses",
                        },
                        {
                            "id": "7",
                            "sourceId": "1",
                            "destinationId": "2",
                            "description": "Uses",
                            "linkedRelationshipId": "5",
                        },
                    ],
                }
            ],
            "softwareSystems": [
                {
                    "id": "2",
                    "name": "S",
                    "containers": [
                        {
                            "id": "3",
                            "name": "Web",
                            "relationships": [
                                {
                                    "id": "6",
                                    "sourceId": "3",
                                    "destinationId": "4",
                                    "description": "Calls",
                                }
                            ],
                        },
                        {"id": "4", "name": "API"},
                    ],
                }
            ],
            "deploymentNodes": [
                {
                    "id": "8",
                    "name": "Server",
                    "environment": "Live",
                    "containerInstances": [
                        {"id": "9", "containerId": "4", "environment": "Live"}
                    ],
                }
            ],
        },
        "views": {
            "systemContextViews": [
                {
                    "key": "ctx",
                    "softwareSystemId": "2",
                    "elements": [
                        {"id": "1", "x": 0, "y": 0},
                        {"id": "2", "x": 0, "y": 400},
                    ],
                    "relationships": [{"id": "7", "vertices": [{"x": 300, "y": 200}]}],
                }
            ],
            "containerViews": [
                {
                    "key": "cont",
                    "softwareSystemId": "2",
                    "elements": [
                        {"id": "1", "x": 0, "y": 0},
                        {"id": "3", "x": 0, "y": 400},
                        {"id": "4", "x": 0, "y": 800},
                    ],
                    "relationships": [
                        {
                            "id": "5",
                            "vertices": [{"x": 300, "y": 150}, {"x": 300, "y": 250}],
                        },
                        {"id": "6"},
                    ],
                },
                {
                    # What the Java library writes for a view nobody arranged.
                    "key": "unarranged",
                    "softwareSystemId": "2",
                    "elements": [
                        {"id": "1", "x": 0, "y": 0},
                        {"id": "3", "x": 0, "y": 0},
                        {"id": "4", "x": 0, "y": 0},
                    ],
                    "relationships": [
                        {"id": "5", "vertices": [{"x": 300, "y": 150}]},
                    ],
                },
                {
                    "key": "auto",
                    "softwareSystemId": "2",
                    "automaticLayout": {"rankDirection": "TopBottom"},
                    "elements": [
                        {"id": "1", "x": 10, "y": 10},
                        {"id": "3", "x": 10, "y": 500},
                        {"id": "4", "x": 10, "y": 900},
                    ],
                },
            ],
            "dynamicViews": [
                {
                    "key": "dyn",
                    "elementId": "2",
                    "elements": [
                        {"id": "1", "x": 0, "y": 0},
                        {"id": "3", "x": 0, "y": 400},
                        {"id": "4", "x": 0, "y": 800},
                    ],
                    "relationships": [
                        {"id": "5", "order": "1"},
                        {"id": "6", "order": "2", "vertices": [{"x": 500, "y": 600}]},
                    ],
                }
            ],
            "deploymentViews": [
                {
                    "key": "live",
                    "environment": "Live",
                    "elements": [
                        {"id": "8", "x": 0, "y": 0},
                        {"id": "9", "x": 100, "y": 100},
                    ],
                }
            ],
            "configuration": {
                "styles": {
                    "elements": [
                        {"tag": "Person", "width": 400},
                        {"tag": "Staff", "height": 250},
                    ]
                }
            },
        },
    }
}


def _workspace() -> Workspace:
    return parse_json(json.dumps(WORKSPACE))


def _payload(workspace: Workspace, key: str) -> dict[str, Any]:
    view = next(v for v in workspace.views if v.key == key)
    return react_flow_graph(workspace, view)


def _edges(workspace: Workspace, key: str) -> dict[tuple[str, str], dict[str, Any]]:
    return {(e["source"], e["target"]): e for e in _payload(workspace, key)["edges"]}


def _nodes(workspace: Workspace, key: str) -> dict[str, dict[str, Any]]:
    return {n["id"]: n for n in _payload(workspace, key)["nodes"]}


class TestPositions:
    def test_elements_keep_their_place(self) -> None:
        nodes = _nodes(_workspace(), "cont")
        assert nodes["3"]["position"] == {"x": 0, "y": 400}
        assert nodes["4"]["position"] == {"x": 0, "y": 800}

    def test_a_boundary_has_no_position_to_keep(self) -> None:
        # Fitted around its children by the renderers, so its absence must
        # not be what sends them to auto-layout (needsAutoLayout).
        nodes = _nodes(_workspace(), "cont")
        assert nodes["2"]["data"]["kind"] == "boundary"
        assert "position" not in nodes["2"]
        assert {nodes["3"]["parentId"], nodes["4"]["parentId"]} == {"2"}

    @pytest.mark.parametrize("key", ["unarranged", "auto"])
    def test_a_view_structurizr_would_lay_out_afresh_keeps_nothing(
        self, key: str
    ) -> None:
        workspace = _workspace()
        view = next(v for v in workspace.views if v.key == key)
        assert view.element_views == []
        nodes = _nodes(workspace, key)
        assert not any("position" in n or "size" in n for n in nodes.values())
        # Its vertices are coordinates in a layout that is not drawn.
        assert not any("waypoints" in e for e in _edges(workspace, key).values())

    def test_a_partly_placed_view_loses_no_element_on_export(self) -> None:
        document = json.loads(json.dumps(WORKSPACE))
        view = document["workspace"]["views"]["containerViews"][0]
        view["elements"][2] = {"id": "4"}
        exported = json.loads(export_json(parse_json(json.dumps(document))))
        elements = exported["workspace"]["views"]["containerViews"][0]["elements"]
        assert {"id": "4"} in elements
        assert {"id": "3", "x": 0, "y": 400} in elements


class TestSizes:
    def test_elements_are_structurizr_sized(self) -> None:
        nodes = _nodes(_workspace(), "cont")
        width, height = STRUCTURIZR_ELEMENT_SIZE
        assert nodes["3"]["size"] == {"width": width, "height": height}

    def test_styles_size_them_in_declaration_order(self) -> None:
        # Person sets the width, the element's own Staff tag the height.
        nodes = _nodes(_workspace(), "cont")
        assert nodes["1"]["size"] == {"width": 400, "height": 250}

    def test_a_deployment_node_is_a_boundary_not_a_box(self) -> None:
        workspace = _workspace()
        view = next(v for v in workspace.views if v.key == "live")
        sized = {ve.id: (ve.width, ve.height) for ve in view.element_views}
        assert sized["8"] == (None, None)
        assert sized["9"] == STRUCTURIZR_ELEMENT_SIZE
        nodes = _nodes(workspace, "live")
        assert "size" not in nodes["8"]


class TestVertices:
    def test_the_parser_reads_them(self) -> None:
        view = next(v for v in _workspace().views if v.key == "cont")
        by_id = {rv.id: rv for rv in view.relationship_views}
        assert [(v.x, v.y) for v in by_id["5"].vertices] == [(300, 150), (300, 250)]
        assert by_id["6"].vertices == []

    def test_the_parser_skips_a_malformed_vertex(self) -> None:
        document = json.loads(json.dumps(WORKSPACE))
        rv = document["workspace"]["views"]["containerViews"][0]["relationships"][0]
        rv["vertices"] = [{"x": 1, "y": 2}, {"x": "a", "y": 3}, {"y": 4}, "junk"]
        view = next(
            v for v in parse_json(json.dumps(document)).views if v.key == "cont"
        )
        assert [(v.x, v.y) for v in view.relationship_views[0].vertices] == [(1, 2)]

    def test_export_writes_them_back(self) -> None:
        exported = json.loads(export_json(_workspace()))
        rels = exported["workspace"]["views"]["containerViews"][0]["relationships"]
        by_id = {rv["id"]: rv for rv in rels}
        assert by_id["5"]["vertices"] == [{"x": 300, "y": 150}, {"x": 300, "y": 250}]
        # No bend points, no key — the file stays as Structurizr writes it.
        assert "vertices" not in by_id["6"]

    def test_a_line_is_drawn_through_them(self) -> None:
        edges = _edges(_workspace(), "cont")
        assert edges[("1", "3")]["waypoints"] == [[300, 150], [300, 250]]
        assert "waypoints" not in edges[("3", "4")]

    def test_an_implied_relationship_reaches_the_lifted_line(self) -> None:
        # The view names relationship 7, which the graph never draws under
        # that id: it draws the lift of 5. The endpoints are what they share.
        edges = _edges(_workspace(), "ctx")
        assert edges[("1", "2")]["waypoints"] == [[300, 200]]

    def test_a_dynamic_step_is_matched_by_its_order(self) -> None:
        edges = _edges(_workspace(), "dyn")
        assert edges[("3", "4")]["waypoints"] == [[500, 600]]
        assert "waypoints" not in edges[("1", "3")]

    def test_the_layout_sidecar_wins(self, tmp_path: Path) -> None:
        source = tmp_path / "workspace.json"
        source.write_text(json.dumps(WORKSPACE), encoding="utf-8")
        workspace = parse_json(source.read_text(encoding="utf-8"))
        view = next(v for v in workspace.views if v.key == "cont")
        edge_id = next(
            e["id"]
            for e in react_flow_graph(workspace, view)["edges"]
            if e["source"] == "1"
        )
        (tmp_path / "workspace.layout.json").write_text(
            json.dumps({"edges": {"cont": {edge_id: [[10, 20]]}}}), encoding="utf-8"
        )
        payload = _payload_with_layout(workspace, view, source)
        edge = next(e for e in payload["edges"] if e["id"] == edge_id)
        assert edge["waypoints"] == [[10, 20]]


@needs_node
class TestRendered:
    """What only the Node renderer can show: the layout it actually drew."""

    def _svg(self, key: str) -> str:
        from c4studio.render import render_view

        workspace = _workspace()
        view = next(v for v in workspace.views if v.key == key)
        return render_view(workspace, view, show_title=False, show_legend=False)

    def test_it_draws_the_stored_layout_not_a_fresh_one(self) -> None:
        svg = self._svg("cont")
        # Structurizr-sized boxes, exactly where the JSON put them relative
        # to each other: 400 apart down one column.
        boxes = [
            (float(x), float(y))
            for x, y in re.findall(
                r'<rect x="([\d.]+)" y="([\d.]+)" width="450" height="300"', svg
            )
        ]
        assert len(boxes) == 2
        (x1, y1), (x2, y2) = sorted(boxes, key=lambda box: box[1])
        assert (x2 - x1, y2 - y1) == (0, 400)

    def test_the_line_bends_through_its_vertices(self) -> None:
        svg = self._svg("cont")
        bent = re.search(
            r'<path d="M [\d. ]+ L ([\d.]+) ([\d.]+) L ([\d.]+) ([\d.]+) L', svg
        )
        assert bent is not None
        # Shifted by the same offset as the elements, but still 100 apart
        # in one vertical run, as the vertices are.
        x1, y1, x2, y2 = (float(n) for n in bent.groups())
        assert (x2 - x1, y2 - y1) == (0, 100)
