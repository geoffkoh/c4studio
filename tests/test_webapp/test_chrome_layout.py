"""Dragged diagram chrome (title/legend) persistence (PP-117).

Dragged positions live in the sidecar's additive ``chrome`` section as
``{view_key: {"title"|"legend": [x, y]}}``, ride back on the graph
payload, and clear with reset-layout. Chrome the user never moved is
absent everywhere — the client keeps computing its placement.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from c4studio.webapp.server import create_app

DSL = """
workspace "W" {
    model {
        u = person "User"
        s = softwareSystem "S"
        u -> s "Uses"
    }
    views {
        systemContext s Context {
            include *
        }
    }
}
"""


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    (tmp_path / "w.dsl").write_text(DSL, encoding="utf-8")
    test_client = TestClient(create_app(root=tmp_path))
    assert test_client.post("/api/load", json={"path": "w.dsl"}).status_code == 200
    return test_client


def _graph(client: TestClient) -> dict[str, Any]:
    data: dict[str, Any] = client.get("/api/views/Context/graph").json()
    return data


def test_untouched_chrome_is_absent_from_the_payload(client: TestClient) -> None:
    assert "chrome" not in _graph(client)


def test_dragged_chrome_round_trips(client: TestClient, tmp_path: Path) -> None:
    response = client.post(
        "/api/views/Context/layout",
        json={
            "positions": {"u": [10, 20]},
            "chrome": {"title": [400, -60], "legend": [-120, 300]},
        },
    )
    assert response.status_code == 200

    sidecar = json.loads((tmp_path / "w.layout.json").read_text(encoding="utf-8"))
    assert sidecar["chrome"] == {
        "Context": {"title": [400, -60], "legend": [-120, 300]}
    }
    assert _graph(client)["chrome"] == {"title": [400, -60], "legend": [-120, 300]}

    # Survives a fresh app over the same sidecar.
    fresh = TestClient(create_app(root=tmp_path))
    fresh.post("/api/load", json={"path": "w.dsl"})
    assert _graph(fresh)["chrome"] == {"title": [400, -60], "legend": [-120, 300]}


def test_a_save_without_chrome_clears_the_section(
    client: TestClient, tmp_path: Path
) -> None:
    client.post(
        "/api/views/Context/layout",
        json={"positions": {"u": [10, 20]}, "chrome": {"title": [400, -60]}},
    )
    # The double-click reset path: the next save simply omits the chrome.
    client.post(
        "/api/views/Context/layout",
        json={"positions": {"u": [10, 20]}, "chrome": {}},
    )
    sidecar = json.loads((tmp_path / "w.layout.json").read_text(encoding="utf-8"))
    assert "chrome" not in sidecar
    assert "chrome" not in _graph(client)


def test_reset_layout_clears_chrome(client: TestClient, tmp_path: Path) -> None:
    client.post(
        "/api/views/Context/layout",
        json={"positions": {}, "chrome": {"legend": [5, 6]}},
    )
    assert client.delete("/api/views/Context/layout").status_code == 200
    assert not (tmp_path / "w.layout.json").exists()
    assert "chrome" not in _graph(client)
