"""Recolouring from the details card, over the API (PP-231).

``POST /api/style`` works out the text edit and writes nothing; the client
saves it through ``PUT /api/source``. These tests apply the returned text
the way the client does and check the graph that results.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from c4studio.webapp.server import create_app

DSL = """workspace "W" {
    model {
        u = person "User"
        s = softwareSystem "S" {
            api = container "API" "" "" "Service"
            db = container "DB" "" "" "Database"
            cache = container "Cache" "" "" "Database"
        }
        u -> api "Uses"
        api -> db "Reads" "" "Async"
    }
    views {
        container s Containers {
            include *
        }
        styles {
            element "Element" {
                color #ffffff
            }
            element "Database" {
                background #438dd5
            }
        }
    }
}
"""


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "w.dsl").write_text(DSL, encoding="utf-8")
    return tmp_path


@pytest.fixture
def client(root: Path) -> TestClient:
    client = TestClient(create_app(root=root))
    assert client.post("/api/load", json={"path": "w.dsl"}).status_code == 200
    return client


def _apply(client: TestClient, root: Path, body: dict[str, Any]) -> dict[str, Any]:
    """Plan an edit and save it, as the Studio does when nothing is unsaved."""
    response = client.post("/api/style", json=body)
    assert response.status_code == 200, response.text
    plan: dict[str, Any] = response.json()
    for file in plan["files"]:
        (root / file["path"]).write_text(file["content"], encoding="utf-8")
    assert client.post("/api/load", json={"path": "w.dsl"}).status_code == 200
    return plan


def _nodes(client: TestClient) -> dict[str, dict[str, Any]]:
    graph = client.get("/api/views/Containers/graph").json()
    return {node["id"]: node["data"] for node in graph["nodes"]}


def test_planning_writes_nothing(client: TestClient, root: Path) -> None:
    response = client.post(
        "/api/style",
        json={
            "kind": "element",
            "property": "background",
            "value": "#ff0000",
            "tag": "Database",
        },
    )
    assert response.status_code == 200
    assert (root / "w.dsl").read_text(encoding="utf-8") == DSL
    assert [f["path"] for f in response.json()["files"]] == ["w.dsl"]


def test_a_tag_recolours_every_element_carrying_it(
    client: TestClient, root: Path
) -> None:
    _apply(
        client,
        root,
        {
            "kind": "element",
            "property": "background",
            "value": "#FF0000",
            "tag": "Database",
        },
    )
    nodes = _nodes(client)
    assert nodes["db"]["background"] == "#ff0000"
    assert nodes["cache"]["background"] == "#ff0000"
    assert nodes["db"]["styleOrigins"]["background"] == {
        "tag": "Database",
        "theme": False,
    }


def test_only_this_element_gives_it_a_tag_and_a_style(
    client: TestClient, root: Path
) -> None:
    plan = _apply(
        client,
        root,
        {
            "kind": "element",
            "property": "background",
            "value": "#00aa00",
            "element": "db",
        },
    )
    assert plan == {"files": plan["files"], "tag": "DB", "newTag": True}
    nodes = _nodes(client)
    assert nodes["db"]["background"] == "#00aa00"
    assert nodes["cache"]["background"] == "#438dd5"
    assert nodes["db"]["tags"] == ["Database", "DB"]

    # Again: the element's own tag is reused, not a second one added.
    plan = _apply(
        client,
        root,
        {"kind": "element", "property": "stroke", "value": "#111111", "element": "db"},
    )
    assert plan["tag"] == "DB" and plan["newTag"] is False
    text = (root / "w.dsl").read_text(encoding="utf-8")
    assert text.count('tags "DB"') == 1
    assert _nodes(client)["db"]["stroke"] == "#111111"


def test_a_generic_tag_one_element_carries_is_not_its_own(
    client: TestClient, root: Path
) -> None:
    # Only `api` is a `Service`, but a rule for `Service` would colour the
    # next one tagged too, so "only this" makes a tag of its own.
    plan = _apply(
        client,
        root,
        {
            "kind": "element",
            "property": "background",
            "value": "#123456",
            "element": "api",
        },
    )
    assert plan["tag"] == "API" and plan["newTag"] is True


def test_a_reset_removes_the_rule_s_line(client: TestClient, root: Path) -> None:
    _apply(
        client,
        root,
        {"kind": "element", "property": "background", "value": None, "tag": "Database"},
    )
    assert "background" not in _nodes(client)["db"]


def test_a_line_is_recoloured_by_its_tag(client: TestClient, root: Path) -> None:
    _apply(
        client,
        root,
        {"kind": "relationship", "property": "style", "value": "solid", "tag": "Async"},
    )
    edges = client.get("/api/views/Containers/graph").json()["edges"]
    reads = next(e for e in edges if e["source"] == "api" and e["target"] == "db")
    assert reads["lineStyle"] == "solid"
    assert reads["styleOrigins"] == {"style": "Async"}


def test_the_payload_says_how_far_a_tag_reaches(client: TestClient) -> None:
    graph = client.get("/api/views/Containers/graph").json()
    counts = graph["styleTagCounts"]
    assert counts["element"]["Database"] == 2
    assert counts["element"]["Container"] == 3
    assert counts["relationship"] == {"Relationship": 2, "Async": 1}
    nodes = {node["id"]: node["data"] for node in graph["nodes"]}
    assert nodes["api"]["kindTag"] == "Container"
    assert nodes["api"]["styleOrigins"] == {"color": {"tag": "Element", "theme": False}}


def test_unsaved_text_is_what_gets_edited(client: TestClient) -> None:
    unsaved = DSL.replace("background #438dd5", "background #000000")
    response = client.post(
        "/api/style",
        json={
            "kind": "element",
            "property": "stroke",
            "value": "#ffffff",
            "tag": "Database",
            "buffers": {"w.dsl": unsaved},
        },
    )
    content = response.json()["files"][0]["content"]
    assert "background #000000\n                stroke #ffffff" in content


def test_only_this_waits_for_unsaved_edits_to_its_definition(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/style",
        json={
            "kind": "element",
            "property": "background",
            "value": "#ffffff",
            "element": "db",
            "buffers": {"w.dsl": DSL + "\n"},
        },
    )
    assert response.status_code == 409
    assert "unsaved" in response.json()["detail"]


@pytest.mark.parametrize(
    "body",
    [
        {
            "kind": "element",
            "property": "background",
            "value": "red",
            "tag": "Database",
        },
        {"kind": "element", "property": "shape", "value": "Box", "tag": "Database"},
        {"kind": "element", "property": "background", "value": "#ffffff"},
        {
            "kind": "relationship",
            "property": "color",
            "value": "#ffffff",
            "element": "db",
        },
    ],
)
def test_what_the_card_would_not_send_is_refused(
    client: TestClient, body: dict[str, Any]
) -> None:
    assert client.post("/api/style", json=body).status_code == 422


def test_viewer_mode_refuses(root: Path) -> None:
    viewer = TestClient(create_app(root=root, read_only=True))
    viewer.post("/api/load", json={"path": "w.dsl"})
    response = viewer.post(
        "/api/style",
        json={
            "kind": "element",
            "property": "background",
            "value": "#ffffff",
            "tag": "Database",
        },
    )
    assert response.status_code == 403
