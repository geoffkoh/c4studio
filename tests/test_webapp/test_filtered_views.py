"""Tests for filtered views (tag-based include/exclude over a base view)."""

from __future__ import annotations

import pytest

from pystructurizr.models import FilterMode, View, ViewType, Workspace
from pystructurizr.parser.dsl import parse_dsl
from pystructurizr.webapp.graph import is_supported, react_flow_graph
from pystructurizr.graph.view_graph import build_view_graph

DSL = """
workspace "W" {
    model {
        trader = person "Trader"
        core = softwareSystem "Core Platform" "In-house" {
            web = container "Web App" "" "React" "Payments"
            db  = container "Database" "" "PostgreSQL" "Database"
        }
        vendor = softwareSystem "Vendor Feed" "SaaS" "External System"
        trader -> core "Uses"
        core -> vendor "Pulls data from"
        web -> db "Reads/writes"
    }
    views {
        systemLandscape Landscape "Everything" {
            include *
            autoLayout lr
        }
        container core Containers "Core containers" {
            include *
        }
        filtered Landscape exclude "External System" InternalOnly "Internal"
        filtered Landscape include "Person" PeopleOnly
        filtered Containers include "Database" DataStores
        filtered Missing exclude "X" Broken
    }
}
"""


@pytest.fixture(scope="module")
def workspace() -> Workspace:
    return parse_dsl(DSL)


def _view(workspace: Workspace, key: str) -> View:
    return next(v for v in workspace.views if v.key == key)


class TestDslParsing:
    def test_filtered_views_are_parsed(self, workspace: Workspace) -> None:
        view = _view(workspace, "InternalOnly")
        assert view.type == ViewType.FILTERED
        assert view.base_view_key == "Landscape"
        assert view.filter_mode == FilterMode.EXCLUDE
        assert view.filter_tags == ["External System"]
        assert view.title == "Internal"

    def test_key_defaults_from_base_and_mode(self) -> None:
        ws = parse_dsl(
            """
            workspace "W" {
                model { s = softwareSystem "S" }
                views {
                    systemLandscape L { include * }
                    filtered L include "Element"
                }
            }
            """
        )
        keys = [v.key for v in ws.views if v.type == ViewType.FILTERED]
        assert keys == ["L_include"]

    def test_filtered_views_are_supported(self, workspace: Workspace) -> None:
        assert is_supported(_view(workspace, "InternalOnly"))


class TestExcludeMode:
    def test_excluded_tag_removes_elements_and_their_edges(
        self, workspace: Workspace
    ) -> None:
        data = build_view_graph(workspace, _view(workspace, "InternalOnly"))
        ids = {n["id"] for n in data["nodes"]}
        assert "vendor" not in ids
        assert {"trader", "core"} <= ids
        assert all("vendor" not in (e["source"], e["target"]) for e in data["edges"])
        # The trader -> core edge survives.
        assert any(
            e["source"] == "trader" and e["target"] == "core" for e in data["edges"]
        )


class TestIncludeMode:
    def test_include_keeps_only_matching_implicit_tags(
        self, workspace: Workspace
    ) -> None:
        # "Person" is an implicit tag: only the trader remains.
        data = build_view_graph(workspace, _view(workspace, "PeopleOnly"))
        ids = {n["id"] for n in data["nodes"]}
        assert ids == {"trader"}
        assert data["edges"] == []

    def test_include_on_container_view_prunes_empty_boundaries(
        self, workspace: Workspace
    ) -> None:
        data = build_view_graph(workspace, _view(workspace, "DataStores"))
        by_id = {n["id"]: n for n in data["nodes"]}
        assert "db" in by_id
        assert "web" not in by_id
        # The scope boundary still holds the database, so it survives.
        assert by_id["db"].get("parentId") in by_id


class TestEdgeCases:
    def test_missing_base_view_yields_empty_graph(self, workspace: Workspace) -> None:
        data = build_view_graph(workspace, _view(workspace, "Broken"))
        assert data == {"nodes": [], "edges": []}

    def test_rank_direction_inherited_from_base_view(
        self, workspace: Workspace
    ) -> None:
        flow = react_flow_graph(workspace, _view(workspace, "InternalOnly"))
        assert flow["rankDirection"] == "LR"
