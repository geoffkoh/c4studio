"""``GET /api/impact/{element_id}`` (PP-193).

The walk itself is pinned by ``tests/test_impact.py``; this is the route
the Studio's impact overlay reads: the same answer as ``c4 impact
--json``, plus the element's ``family``, which the page needs to mark
whatever a view draws in the element's place.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from c4studio.impact import family
from c4studio.parser.dsl import parse_dsl
from c4studio.webapp.server import create_app

DSL = """
workspace "W" {
    model {
        u = person "User"
        shop = softwareSystem "Shop" {
            web = container "Web" {
                page = component "Page"
            }
            api = container "API"
            web -> api "Calls"
        }
        partner = softwareSystem "Partner"
        u -> web "Uses"
        api -> partner "Calls"
    }
    views {
        systemContext shop Context {
            include *
        }
        container shop Containers {
            include *
        }
    }
}
"""


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    (tmp_path / "w.dsl").write_text(DSL, encoding="utf-8")
    client = TestClient(create_app(root=tmp_path))
    assert client.post("/api/load", json={"path": "w.dsl"}).status_code == 200
    return client


def _ids(hops: list[dict[str, object]]) -> list[object]:
    return [hop["id"] for hop in hops]


def test_the_answer_has_both_directions_views_and_family(client: TestClient) -> None:
    body = client.get("/api/impact/api").json()
    assert body["element"] == {"id": "api", "name": "API", "kind": "container"}
    assert "web" in _ids(body["dependents"])
    assert "u" in _ids(body["dependents"])
    assert "partner" in _ids(body["dependencies"])
    assert body["views"] == ["Containers"]
    assert body["family"] == ["shop"]


def test_depth_limits_the_walk(client: TestClient) -> None:
    near = client.get("/api/impact/api", params={"depth": 1}).json()
    assert "u" not in _ids(near["dependents"])
    assert {hop["depth"] for hop in near["dependents"]} == {1}


def test_an_unknown_element_is_404(client: TestClient) -> None:
    response = client.get("/api/impact/nobody")
    assert response.status_code == 404
    assert "nobody" in response.json()["detail"]


def test_a_depth_below_one_is_refused(client: TestClient) -> None:
    assert client.get("/api/impact/api", params={"depth": 0}).status_code == 422


def test_viewer_may_ask(tmp_path: Path) -> None:
    """A read: the read-only server answers it like any graph request."""
    (tmp_path / "w.dsl").write_text(DSL, encoding="utf-8")
    viewer = TestClient(create_app(root=tmp_path, read_only=True))
    viewer.post("/api/load", json={"path": "w.dsl"})
    assert viewer.get("/api/impact/api").status_code == 200


class TestFamily:
    def test_ancestors_and_descendants_in_model_order(self) -> None:
        ws = parse_dsl(DSL)
        assert family(ws, "web") == ["shop", "page"]
        assert family(ws, "shop") == ["web", "page", "api"]
        assert family(ws, "u") == []

    def test_an_unknown_id_raises(self) -> None:
        with pytest.raises(KeyError):
            family(parse_dsl(DSL), "nobody")
