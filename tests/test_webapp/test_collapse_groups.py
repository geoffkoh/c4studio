"""Collapsible group boundaries (PP-114).

A group boundary named in ``collapse`` becomes a single stand-in node:
members vanish, edges touching them lift to the stand-in and merge, and
the state persists through the layout sidecar's additive ``expanded`` /
``collapsed`` sections.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from c4studio.graph.view_graph import build_view_graph
from c4studio.parser.dsl import parse_dsl
from c4studio.webapp.server import create_app

JsonDict = dict[str, Any]

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
        web -> api "Calls" "HTTPS"
        web -> worker "Queues work for"
        api -> worker "Hands off to"
    }
    views {
        container s Containers {
            include *
        }
    }
}
"""

GROUP_ID = "__group__s__Backend"


@pytest.fixture()
def workspace_data() -> JsonDict:
    ws = parse_dsl(DSL)
    view = next(v for v in ws.views if v.key == "Containers")
    return build_view_graph(ws, view, collapse={GROUP_ID})


def test_members_are_swallowed_by_the_stand_in(workspace_data: JsonDict) -> None:
    ids = {n["id"] for n in workspace_data["nodes"]}
    assert GROUP_ID in ids
    assert "api" not in ids
    assert "worker" not in ids
    assert "web" in ids


def test_the_stand_in_is_a_plain_expandable_node(workspace_data: JsonDict) -> None:
    node = next(n for n in workspace_data["nodes"] if n["id"] == GROUP_ID)
    assert node["data"]["kind"] == "group"
    assert node["data"]["expandable"] is True
    assert node["data"]["collapsedGroup"] is True
    assert node["data"]["description"] == "2 elements"


def test_edges_lift_and_merge(workspace_data: JsonDict) -> None:
    edges = {(e["source"], e["target"]): e for e in workspace_data["edges"]}
    # web -> api and web -> worker merge into one lifted edge.
    merged = edges[("web", GROUP_ID)]
    assert merged["data"]["label"] == "2 relationships"
    # api -> worker was internal to the group and disappears.
    assert (GROUP_ID, GROUP_ID) not in edges
    assert ("u", "web") in edges


def test_the_legend_gains_a_group_row(workspace_data: JsonDict) -> None:
    labels = [entry["label"] for entry in workspace_data["legend"]]
    assert "Group (collapsed)" in labels


def test_collapsing_nothing_changes_nothing() -> None:
    ws = parse_dsl(DSL)
    view = next(v for v in ws.views if v.key == "Containers")
    plain = build_view_graph(ws, view)
    ignored = build_view_graph(ws, view, collapse={"__group__s__NoSuchGroup"})
    assert {n["id"] for n in ignored["nodes"]} == {n["id"] for n in plain["nodes"]}


# ---------------------------------------------------------------------------
# API round-trip
# ---------------------------------------------------------------------------


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    (tmp_path / "grouped.dsl").write_text(DSL, encoding="utf-8")
    test_client = TestClient(create_app(root=tmp_path))
    response = test_client.post("/api/load", json={"path": "grouped.dsl"})
    assert response.status_code == 200
    return test_client


def test_collapse_param_and_echo(client: TestClient) -> None:
    data = client.get(f"/api/views/Containers/graph?collapse={GROUP_ID}").json()
    assert GROUP_ID in {n["id"] for n in data["nodes"]}
    assert data["collapsedIds"] == [GROUP_ID]
    assert data["expandedIds"] == []


def test_expansion_persists_to_the_sidecar_and_seeds_the_next_load(
    client: TestClient, tmp_path: Path
) -> None:
    saved = client.post(
        "/api/views/Containers/expansion",
        json={"expanded": [], "collapsed": [GROUP_ID]},
    )
    assert saved.status_code == 200

    sidecar = json.loads((tmp_path / "grouped.layout.json").read_text())
    assert sidecar["collapsed"] == {"Containers": [GROUP_ID]}

    # A request naming no state gets the saved state applied and echoed.
    data = client.get("/api/views/Containers/graph").json()
    assert data["collapsedIds"] == [GROUP_ID]
    assert "api" not in {n["id"] for n in data["nodes"]}

    # An explicitly empty parameter overrides the saved state.
    data = client.get("/api/views/Containers/graph?collapse=").json()
    assert data["collapsedIds"] == []
    assert "api" in {n["id"] for n in data["nodes"]}

    # Clearing the state removes the section (and the file, if now empty).
    cleared = client.post(
        "/api/views/Containers/expansion",
        json={"expanded": [], "collapsed": []},
    )
    assert cleared.status_code == 200
    assert not (tmp_path / "grouped.layout.json").exists()


def test_reset_layout_clears_expansion_state(
    client: TestClient, tmp_path: Path
) -> None:
    client.post(
        "/api/views/Containers/expansion",
        json={"expanded": [], "collapsed": [GROUP_ID]},
    )
    assert (tmp_path / "grouped.layout.json").exists()
    client.delete("/api/views/Containers/layout")
    assert not (tmp_path / "grouped.layout.json").exists()
    data = client.get("/api/views/Containers/graph").json()
    assert data["collapsedIds"] == []
