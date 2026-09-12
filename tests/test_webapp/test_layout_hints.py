"""Per-boundary auto-layout hints via ``c4studio.autolayout`` (PP-115).

An element property overrides the rank direction inside the boundary that
element renders as; a view property keyed by group name does the same for
a group boundary. The hint travels as ``rankDirection`` on the boundary's
node data, which is all the layout engine needs — it already runs one
dagre pass per boundary level.
"""

from __future__ import annotations

from typing import Any

from c4studio.graph.view_graph import build_view_graph
from c4studio.parser.dsl import parse_dsl

JsonDict = dict[str, Any]

DSL = """
workspace "W" {
    model {
        u = person "User"
        s = softwareSystem "S" {
            properties {
                "c4studio.autolayout" "lr"
            }
            group "Backend" {
                api = container "API"
                worker = container "Worker"
            }
            web = container "Web" {
                properties {
                    "c4studio.autolayout" "sideways"
                }
                ui = component "UI"
            }
        }
        u -> web "Uses"
        web -> api "Calls"
    }
    views {
        container s Containers {
            include *
            properties {
                "c4studio.autolayout.Backend" "BT"
            }
        }
        component web WebComponents {
            include *
        }
    }
}
"""


def _graph(key: str) -> JsonDict:
    ws = parse_dsl(DSL)
    view = next(v for v in ws.views if v.key == key)
    return build_view_graph(ws, view)


def _node(data: JsonDict, node_id: str) -> JsonDict:
    return next(n for n in data["nodes"] if n["id"] == node_id)


def test_element_property_lands_on_its_boundary() -> None:
    data = _graph("Containers")
    assert _node(data, "s")["data"]["rankDirection"] == "LR"


def test_view_property_lands_on_the_group_boundary_case_insensitively() -> None:
    data = _graph("Containers")
    group = _node(data, "__group__s__Backend")
    assert group["data"]["rankDirection"] == "BT"


def test_an_unrecognised_hint_is_ignored() -> None:
    """Properties are free-form text; a typo must never break a render."""
    data = _graph("WebComponents")
    assert "rankDirection" not in _node(data, "web")["data"]


def test_non_boundary_nodes_never_carry_the_hint() -> None:
    data = _graph("Containers")
    assert "rankDirection" not in _node(data, "web")["data"]
