"""Tests for group boundary rendering in static view graphs (Phase 2)."""

from __future__ import annotations

from c4studio.parser.dsl import parse_dsl
from c4studio.graph.view_graph import build_view_graph
from typing import Any, cast

JsonDict = dict[str, Any]


GROUPED_DSL = """
workspace "W" {
    model {
        group "Internal" {
            u = person "User"
            s = softwareSystem "S" {
                group "Backend" {
                    api = container "API"
                }
                web = container "Web"
            }
        }
        ext = softwareSystem "External"
        u -> s "Uses"
        ext -> s "Monitors"
    }
    views {
        systemContext s "ctx" {
            include *
        }
        container s "cont" {
            include *
        }
    }
}
"""


def _node_by_id(data: JsonDict, node_id: str) -> JsonDict:
    for node in data["nodes"]:
        if node["id"] == node_id:
            return cast(JsonDict, node)
    raise AssertionError(f"no node with id {node_id!r}")


def _group_nodes(data: JsonDict) -> list[JsonDict]:
    return [
        n
        for n in data["nodes"]
        if n["data"].get("kind") == "boundary"
        and n["data"].get("boundaryLabel") == "Group"
    ]


def test_system_context_groups_become_boundaries() -> None:
    ws = parse_dsl(GROUPED_DSL)
    view = next(v for v in ws.views if v.key == "ctx")
    data = build_view_graph(ws, view)
    groups = _group_nodes(data)
    assert len(groups) == 1
    group_node = groups[0]
    assert group_node["data"]["label"] == "Internal"
    # Grouped elements are parented to the group boundary.
    assert _node_by_id(data, "u")["parentId"] == group_node["id"]
    assert _node_by_id(data, "s")["parentId"] == group_node["id"]
    # Ungrouped elements are not.
    assert "parentId" not in _node_by_id(data, "ext")


def test_group_boundaries_precede_their_children() -> None:
    ws = parse_dsl(GROUPED_DSL)
    view = next(v for v in ws.views if v.key == "ctx")
    data = build_view_graph(ws, view)
    order = [n["id"] for n in data["nodes"]]
    group_id = _group_nodes(data)[0]["id"]
    assert order.index(group_id) < order.index("u")
    assert order.index(group_id) < order.index("s")


def test_container_view_groups_nest_inside_system_boundary() -> None:
    ws = parse_dsl(GROUPED_DSL)
    view = next(v for v in ws.views if v.key == "cont")
    data = build_view_graph(ws, view)
    groups = _group_nodes(data)
    backend = next(g for g in groups if g["data"]["label"] == "Backend")
    # The group nests inside the scoped system boundary...
    assert backend["parentId"] == "s"
    # ...and the grouped container nests inside the group.
    assert _node_by_id(data, "api")["parentId"] == backend["id"]
    # The ungrouped container stays directly inside the system boundary.
    assert _node_by_id(data, "web")["parentId"] == "s"


def test_no_group_nodes_without_groups() -> None:
    ws = parse_dsl(
        """
        workspace "W" {
            model {
                u = person "User"
                s = softwareSystem "S"
                u -> s "Uses"
            }
            views {
                systemContext s "ctx" { include * }
            }
        }
        """
    )
    data = build_view_graph(ws, ws.views[0])
    assert _group_nodes(data) == []
