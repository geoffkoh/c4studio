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
    assert merged["data"]["label"] == "2 relationships [1]"
    # api -> worker was internal to the group and disappears.
    assert (GROUP_ID, GROUP_ID) not in edges
    assert ("u", "web") in edges


def test_a_merged_line_s_marker_is_keyed_in_the_notes(workspace_data: JsonDict) -> None:
    # PP-229: an exported image has no hover, so what [1] stands for is
    # spelled out beside the legend, member by member.
    edges = {(e["source"], e["target"]): e for e in workspace_data["edges"]}
    assert edges[("web", GROUP_ID)]["data"]["note"] == 1
    assert workspace_data["notes"] == [
        {
            "marker": 1,
            "relationships": [
                {
                    "source": "Web",
                    "target": "API",
                    "description": "Calls",
                    "technology": "HTTPS",
                },
                {
                    "source": "Web",
                    "target": "Worker",
                    "description": "Queues work for",
                    "technology": "",
                },
            ],
        }
    ]


def test_lines_that_say_the_same_need_no_note() -> None:
    ws = parse_dsl(DSL.replace('"Queues work for"', '"Calls"'))
    view = next(v for v in ws.views if v.key == "Containers")
    data = build_view_graph(ws, view, collapse={GROUP_ID})
    edges = {(e["source"], e["target"]): e for e in data["edges"]}
    assert edges[("web", GROUP_ID)]["data"]["label"] == "Calls"
    assert "note" not in edges[("web", GROUP_ID)]["data"]
    assert data["notes"] == []


def test_markers_number_in_line_order() -> None:
    ws = parse_dsl(
        DSL.replace(
            'u -> web "Uses"',
            'u -> web "Uses"\n        u -> api "Reads"\n        u -> worker "Pokes"',
        )
    )
    view = next(v for v in ws.views if v.key == "Containers")
    data = build_view_graph(ws, view, collapse={GROUP_ID})
    labels = sorted(
        e["data"]["label"] for e in data["edges"] if e["target"] == GROUP_ID
    )
    assert labels == ["2 relationships [1]", "2 relationships [2]"]
    assert [n["marker"] for n in data["notes"]] == [1, 2]


def test_the_payload_carries_the_notes(client: TestClient) -> None:
    payload = client.get(
        "/api/views/Containers/graph", params={"collapse": GROUP_ID}
    ).json()
    merged = next(e for e in payload["edges"] if e["target"] == GROUP_ID)
    assert merged["note"] == 1
    assert payload["notes"][0]["marker"] == 1
    assert len(payload["notes"][0]["relationships"]) == 2


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


def _node_available() -> bool:
    from c4studio.render import RenderError, node_executable

    try:
        node_executable()
    except RenderError:
        return False
    return True


@pytest.mark.skipif(not _node_available(), reason="no node")
def test_c4_render_draws_the_key(tmp_path: Path) -> None:
    from c4studio.render import render_view

    source = tmp_path / "grouped.dsl"
    source.write_text(DSL, encoding="utf-8")
    (tmp_path / "grouped.layout.json").write_text(
        json.dumps({"collapsed": {"Containers": [GROUP_ID]}}), encoding="utf-8"
    )
    ws = parse_dsl(DSL)
    view = next(v for v in ws.views if v.key == "Containers")
    svg = render_view(ws, view, layout_source=source)
    assert "2 relationships [1]" in svg
    assert ">[1]</text>" in svg
    assert "Web → API: Calls [HTTPS]" in svg
    assert "Web → Worker: Queues work for" in svg
    # The key is part of the legend, so leaving the legend out leaves it out.
    bare = render_view(ws, view, layout_source=source, show_legend=False)
    assert "Web → API: Calls [HTTPS]" not in bare
