"""Which styles paint a selection, and where they are written (PP-230).

The details card names the style rules that matched an element or a
relationship, in resolution order, and opens the editor at a rule written
in the workspace's files. A rule from a theme has no file, so it is named
but not offered as a jump.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from c4studio.parser.locations import style_locations
from c4studio.webapp.server import create_app

DSL = """workspace "W" {
    model {
        u = person "User"
        s = softwareSystem "S" {
            api = container "API" "" "" "Service"
            db = container "DB" "" "" "Database"
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
                shape Cylinder
            }
            element "Service" {
                background #1168bd
            }
            relationship "Async" {
                style Dotted
            }
            element "Database" {
                background #438dd5
                properties {
                    note "a second rule for the same tag"
                }
            }
        }
    }
}
"""


def _client(tmp_path: Path) -> TestClient:
    (tmp_path / "w.dsl").write_text(DSL, encoding="utf-8")
    client = TestClient(create_app(root=tmp_path))
    assert client.post("/api/load", json={"path": "w.dsl"}).status_code == 200
    return client


def _graph(client: TestClient) -> dict[str, Any]:
    graph: dict[str, Any] = client.get("/api/views/Containers/graph").json()
    return graph


def test_every_rule_is_located_in_source_order(tmp_path: Path) -> None:
    (tmp_path / "w.dsl").write_text(DSL, encoding="utf-8")
    found = [
        (kind, tag, line) for kind, tag, _, line in style_locations(tmp_path / "w.dsl")
    ]
    assert found == [
        ("element", "Element", 16),
        ("element", "Database", 19),
        ("element", "Service", 22),
        ("relationship", "Async", 25),
        ("element", "Database", 28),
    ]


def test_a_model_element_is_not_a_style_rule(tmp_path: Path) -> None:
    source = tmp_path / "w.dsl"
    source.write_text(
        'workspace { model { t = element "Telematics" "IoT" } '
        'views { styles { element "IoT" { background #000000 } } } }',
        encoding="utf-8",
    )
    assert [tag for _, tag, _, _ in style_locations(source)] == ["IoT"]


def test_the_source_listing_carries_the_rules(tmp_path: Path) -> None:
    body = _client(tmp_path).get("/api/source").json()
    assert body["styles"][-1] == {
        "kind": "element",
        "tag": "Database",
        "path": "w.dsl",
        "line": 28,
    }
    assert {
        "kind": "relationship",
        "tag": "Async",
        "path": "w.dsl",
        "line": 25,
    } in body["styles"]


def test_an_element_names_the_rules_that_matched(tmp_path: Path) -> None:
    nodes = {n["id"]: n for n in _graph(_client(tmp_path))["nodes"]}
    # Resolution order, each tag once; `Element` matches everything.
    assert nodes["db"]["data"]["matchedStyles"] == ["Element", "Database"]
    assert nodes["api"]["data"]["matchedStyles"] == ["Element", "Service"]
    assert nodes["u"]["data"]["matchedStyles"] == ["Element"]


def test_a_line_names_the_rules_that_matched(tmp_path: Path) -> None:
    edges = {(e["source"], e["target"]): e for e in _graph(_client(tmp_path))["edges"]}
    assert edges[("api", "db")]["matchedStyles"] == ["Async"]
    # Nothing styles plain relationships here, so nothing is named.
    assert "matchedStyles" not in edges[("u", "api")]
