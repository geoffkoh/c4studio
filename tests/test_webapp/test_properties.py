"""Element and relationship properties in the Explorer's payload (PP-203).

The model graph carries each element's and relationship's ``properties``
for the details panel, in source order and without the ``c4studio.*``
settings, which configure the diagram rather than describe the model.
How the browser draws them is ``e2e/explorer-properties.spec.ts``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from c4studio.graph.view_graph import shown_properties
from c4studio.webapp.server import create_app

DSL = '''
workspace "W" {
    model {
        u = person "User"
        s = softwareSystem "S" {
            api = container "API" {
                properties {
                    "owner" "team-a"
                    "c4studio.autolayout" "lr"
                    "runbook" """
                        ## Restart

                        1. Drain
                        """
                }
            }
        }
        u -> api "Uses" {
            properties {
                "sla" "99.9%"
            }
        }
    }
    views {
        container s "cont" {
            include *
        }
    }
}
'''


@pytest.fixture()
def graph(tmp_path: Path) -> dict[str, Any]:
    (tmp_path / "w.dsl").write_text(DSL, encoding="utf-8")
    client = TestClient(create_app(root=tmp_path))
    assert client.post("/api/load", json={"path": "w.dsl"}).status_code == 200
    response = client.get("/api/model/graph", params={"level": "containers"})
    assert response.status_code == 200
    data: dict[str, Any] = response.json()
    return data


def _element(graph: dict[str, Any], element_id: str) -> dict[str, Any]:
    found: dict[str, Any] = next(e for e in graph["elements"] if e["id"] == element_id)
    return found


def test_an_element_carries_its_properties_in_source_order(
    graph: dict[str, Any],
) -> None:
    properties = _element(graph, "api")["properties"]
    assert list(properties) == ["owner", "runbook"]
    assert properties["runbook"] == "## Restart\n\n1. Drain"


def test_c4studio_settings_are_left_out(graph: dict[str, Any]) -> None:
    assert "c4studio.autolayout" not in _element(graph, "api")["properties"]


def test_an_element_without_any_has_an_empty_map(graph: dict[str, Any]) -> None:
    assert _element(graph, "u")["properties"] == {}


def test_a_relationship_carries_its_properties(graph: dict[str, Any]) -> None:
    (rel,) = [r for r in graph["relationships"] if r["destination_id"] == "api"]
    assert rel["properties"] == {"sla": "99.9%"}


def test_only_the_prefix_is_reserved() -> None:
    """`c4studio` alone, or as part of a word, is anybody's key."""
    assert shown_properties(
        {"c4studio.legend": "x", "c4studio": "a", "c4studios.x": "b"}
    ) == {"c4studio": "a", "c4studios.x": "b"}


class TestViewGraph:
    """The Diagrams page's details card reads the view graph (PP-205)."""

    @pytest.fixture()
    def client(self, tmp_path: Path) -> TestClient:
        dsl = DSL.replace(
            'container s "cont" {',
            'systemContext s "ctx" {\n            include *\n        }\n'
            '        container s "cont" {',
        ).replace(
            '        u -> api "Uses" {',
            '        db = softwareSystem "DB"\n'
            '        api -> db "Reads"\n'
            '        api -> db "Writes"\n'
            '        u -> api "Uses" {',
        )
        (tmp_path / "w.dsl").write_text(dsl, encoding="utf-8")
        client = TestClient(create_app(root=tmp_path))
        assert client.post("/api/load", json={"path": "w.dsl"}).status_code == 200
        return client

    def _graph(self, client: TestClient, key: str) -> dict[str, Any]:
        response = client.get(f"/api/views/{key}/graph")
        assert response.status_code == 200
        data: dict[str, Any] = response.json()
        return data

    def test_a_node_carries_its_properties_only_when_it_has_any(
        self, client: TestClient
    ) -> None:
        nodes = {n["id"]: n["data"] for n in self._graph(client, "cont")["nodes"]}
        assert nodes["api"]["properties"] == {
            "owner": "team-a",
            "runbook": "## Restart\n\n1. Drain",
        }
        assert "properties" not in nodes["u"]

    def test_a_line_drawing_one_relationship_carries_it(
        self, client: TestClient
    ) -> None:
        (edge,) = [
            e for e in self._graph(client, "cont")["edges"] if e["source"] == "u"
        ]
        assert edge["relationship"] == {
            "description": "Uses",
            "technology": "",
            "properties": {"sla": "99.9%"},
        }

    def test_two_relationships_on_one_pair_are_told_apart_by_label(
        self, client: TestClient
    ) -> None:
        edges = [e for e in self._graph(client, "cont")["edges"] if e["target"] == "db"]
        assert sorted(e["relationship"]["description"] for e in edges) == [
            "Reads",
            "Writes",
        ]

    def test_a_lifted_line_carries_none(self, client: TestClient) -> None:
        """In the context view `u -> api` is drawn as `u -> s`."""
        (edge,) = [
            e
            for e in self._graph(client, "ctx")["edges"]
            if (e["source"], e["target"]) == ("u", "s")
        ]
        assert "relationship" not in edge
