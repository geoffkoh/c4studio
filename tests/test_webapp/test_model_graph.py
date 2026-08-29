"""Tests for the full-model explorer graph endpoint."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from c4studio.webapp.server import create_app

FIXTURE = Path(__file__).parent.parent / "fixtures" / "example.dsl"


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    """Return a TestClient with the example workspace loaded."""
    shutil.copy(FIXTURE, tmp_path / "example.dsl")
    test_client = TestClient(create_app(root=tmp_path))
    response = test_client.post("/api/load", json={"path": "example.dsl"})
    assert response.status_code == 200
    return test_client


def _graph(client: TestClient, level: str = "containers") -> dict[str, Any]:
    response = client.get(f"/api/model/graph?level={level}")
    assert response.status_code == 200
    data: dict[str, Any] = response.json()
    return data


def _nodes_by_label(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {node["data"]["label"]: node for node in data["nodes"]}


def test_requires_loaded_workspace(tmp_path: Path) -> None:
    client = TestClient(create_app(root=tmp_path))
    response = client.get("/api/model/graph")
    assert response.status_code == 409


def test_rejects_unknown_level(client: TestClient) -> None:
    response = client.get("/api/model/graph?level=bogus")
    assert response.status_code == 400
    assert "level" in response.json()["detail"]


def test_systems_level_shows_top_level_elements_only(client: TestClient) -> None:
    data = _graph(client, "systems")
    nodes = _nodes_by_label(data)
    assert set(nodes) == {
        "Personal Banking Customer",
        "Internet Banking System",
        "E-mail System",
        "Mainframe Banking System",
    }
    assert all(node["data"]["kind"] != "boundary" for node in data["nodes"])


def test_systems_level_lifts_container_relationships(client: TestClient) -> None:
    data = _graph(client, "systems")
    nodes = _nodes_by_label(data)
    customer = nodes["Personal Banking Customer"]["id"]
    bank = nodes["Internet Banking System"]["id"]
    email = nodes["E-mail System"]["id"]
    pairs = {(edge["source"], edge["target"]) for edge in data["edges"]}
    # customer -> spa and api -> email are declared at container level but
    # surface between the top-level elements here.
    assert (customer, bank) in pairs
    assert (bank, email) in pairs


def test_containers_level_nests_containers_in_system_boundary(
    client: TestClient,
) -> None:
    data = _graph(client, "containers")
    nodes = _nodes_by_label(data)
    bank = nodes["Internet Banking System"]
    assert bank["data"]["kind"] == "boundary"
    assert bank["data"]["boundaryLabel"] == "Software System"
    for label in ("Web Application", "Single-Page App", "API Application", "Database"):
        assert nodes[label]["parentId"] == bank["id"]
    # Systems without containers stay leaf nodes.
    assert nodes["E-mail System"]["data"]["kind"] == "system-external"


def test_containers_level_keeps_declared_relationships(client: TestClient) -> None:
    data = _graph(client, "containers")
    nodes = _nodes_by_label(data)
    labels = {(edge["source"], edge["target"]): edge["label"] for edge in data["edges"]}
    spa = nodes["Single-Page App"]["id"]
    api = nodes["API Application"]["id"]
    customer = nodes["Personal Banking Customer"]["id"]
    email = nodes["E-mail System"]["id"]
    assert labels[(customer, spa)] == "Uses"
    assert labels[(spa, api)] == "Makes API calls"
    assert labels[(api, email)] == "Sends e-mails"


def test_nodes_carry_palette_colours(client: TestClient) -> None:
    data = _graph(client, "containers")
    nodes = _nodes_by_label(data)
    assert nodes["Web Application"]["data"]["color"]
    assert nodes["Personal Banking Customer"]["data"]["color"]


def test_element_index_covers_all_static_elements(client: TestClient) -> None:
    data = _graph(client, "systems")
    by_name = {entry["name"]: entry for entry in data["elements"]}
    # 1 person + 3 systems + 4 containers, present regardless of the level.
    assert len(data["elements"]) == 8
    assert by_name["Web Application"]["level"] == "containers"
    assert by_name["Web Application"]["parent"] == "Internet Banking System"
    assert by_name["Internet Banking System"]["level"] == "systems"
    assert by_name["Personal Banking Customer"]["kind"] == "person"


def test_relationship_index_lists_declared_relationships(
    client: TestClient,
) -> None:
    data = _graph(client)
    descriptions = {rel["description"] for rel in data["relationships"]}
    assert "Sends e-mails" in descriptions
    assert "Visits" in descriptions


def test_views_by_element_maps_elements_to_view_keys(client: TestClient) -> None:
    data = _graph(client)
    by_name = {entry["name"]: entry["id"] for entry in data["elements"]}
    membership = data["views_by_element"]
    assert "SystemContext" in membership[by_name["Internet Banking System"]]
    assert "Containers" in membership[by_name["Internet Banking System"]]
    assert membership[by_name["Web Application"]] == ["Containers"]
