"""Tests for default-view ordering and autoLayout spacing in the webapp API."""

from __future__ import annotations

from pystructurizr.parser.dsl import parse_dsl
from pystructurizr.webapp.graph import react_flow_graph
from pystructurizr.webapp.server import _views_index


DSL = """
workspace "W" {
    model {
        u = person "User"
        s = softwareSystem "S"
        u -> s "Uses"
    }
    views {
        systemLandscape "land" {
            include *
        }
        systemContext s "ctx" {
            include *
            default
            autoLayout lr 300 150
        }
    }
}
"""


def test_views_index_flags_and_orders_default_first() -> None:
    ws = parse_dsl(DSL)
    index = _views_index(ws)
    assert index[0]["key"] == "ctx"
    assert index[0]["default"] is True
    assert all(not entry["default"] for entry in index[1:])


def test_views_index_keeps_declaration_order_without_default() -> None:
    ws = parse_dsl(DSL)
    ws.views.configuration.default_view = ""
    index = _views_index(ws)
    assert [entry["key"] for entry in index] == ["land", "ctx"]


def test_graph_payload_carries_layout_separations() -> None:
    ws = parse_dsl(DSL)
    view = next(v for v in ws.views if v.key == "ctx")
    payload = react_flow_graph(ws, view)
    assert payload["rankDirection"] == "LR"
    assert payload["rankSeparation"] == 300
    assert payload["nodeSeparation"] == 150


def test_graph_payload_defaults_without_autolayout() -> None:
    ws = parse_dsl(DSL)
    view = next(v for v in ws.views if v.key == "land")
    payload = react_flow_graph(ws, view)
    assert payload["rankSeparation"] == 100
    assert payload["nodeSeparation"] == 100
