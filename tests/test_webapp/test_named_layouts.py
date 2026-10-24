"""Named layouts: saving, loading and deleting snapshots (PP-197).

A named layout is a copy of one view's working arrangement — every
per-view sidecar section — kept under a name in the sidecar's
``snapshots`` section. Loading one copies it back; the working layout is
still what autosave writes and ``c4 render`` reads.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from c4studio.layout_sidecar import read_snapshots
from c4studio.webapp.server import create_app

DSL = """
workspace "W" {
    model {
        u = person "User"
        s = softwareSystem "S" {
            web = container "Web"
            api = container "API"
        }
        u -> web "Uses"
        web -> api "Calls"
    }
    views {
        container s "cont" {
            include *
        }
        systemContext s "ctx" {
            include *
        }
    }
}
"""

DSL_FILE = "example.dsl"


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    (tmp_path / DSL_FILE).write_text(DSL, encoding="utf-8")
    return tmp_path


def _client(root: Path, *, read_only: bool = False) -> TestClient:
    client = TestClient(create_app(root=root, read_only=read_only))
    assert client.post("/api/load", json={"path": DSL_FILE}).status_code == 200
    return client


@pytest.fixture()
def client(root: Path) -> TestClient:
    return _client(root)


def _sidecar(root: Path) -> dict[str, Any]:
    path = root / "example.layout.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _positions(
    client: TestClient, key: str = "cont"
) -> dict[str, tuple[int, int] | None]:
    """Saved positions by element; ``None`` for one left to auto-layout."""
    graph = client.get(f"/api/views/{key}/graph").json()
    return {
        n["id"]: (n["position"]["x"], n["position"]["y"]) if "position" in n else None
        for n in graph["nodes"]
        if n["id"] in {"u", "web", "api"}
    }


def _arrange(client: TestClient, x: int, **extra: Any) -> None:
    body = {"positions": {"u": [x, 0], "web": [x, 300], "api": [x + 400, 300]}}
    response = client.post("/api/views/cont/layout", json={**body, **extra})
    assert response.status_code == 200


def _names(client: TestClient, key: str = "cont") -> list[str]:
    response = client.get(f"/api/views/{key}/layouts")
    assert response.status_code == 200
    return [entry["name"] for entry in response.json()["layouts"]]


class TestSave:
    def test_a_view_starts_with_none(self, client: TestClient) -> None:
        assert _names(client) == []

    def test_saving_keeps_the_working_layout_under_its_name(
        self, client: TestClient, root: Path
    ) -> None:
        _arrange(client, 100)
        response = client.post("/api/views/cont/layouts", json={"name": " Review "})
        assert response.status_code == 200
        assert [e["name"] for e in response.json()["layouts"]] == ["Review"]
        assert response.json()["layouts"][0]["savedAt"]
        saved = _sidecar(root)["snapshots"]["cont"]["Review"]
        assert saved["views"] == {"u": [100, 0], "web": [100, 300], "api": [500, 300]}

    def test_every_per_view_section_is_captured(
        self, client: TestClient, root: Path
    ) -> None:
        edge = client.get("/api/views/cont/graph").json()["edges"][0]["id"]
        _arrange(
            client,
            100,
            waypoints={edge: [[10, 20]]},
            labels={edge: [5, 6]},
            routing={edge: "orthogonal"},
            chrome={"title": [1, 2]},
        )
        client.post("/api/views/cont/expansion", json={"collapsed": ["g"]})
        client.post("/api/views/cont/layouts", json={"name": "All"})
        saved = _sidecar(root)["snapshots"]["cont"]["All"]
        assert saved["edges"] == {edge: [[10, 20]]}
        assert saved["labels"] == {edge: [5, 6]}
        assert saved["routing"] == {edge: "orthogonal"}
        assert saved["chrome"] == {"title": [1, 2]}
        assert saved["collapsed"] == ["g"]

    def test_an_existing_name_is_a_conflict_unless_overwriting(
        self, client: TestClient, root: Path
    ) -> None:
        _arrange(client, 100)
        client.post("/api/views/cont/layouts", json={"name": "Review"})
        _arrange(client, 700)
        response = client.post("/api/views/cont/layouts", json={"name": "Review"})
        assert response.status_code == 409
        assert _sidecar(root)["snapshots"]["cont"]["Review"]["views"]["u"] == [100, 0]

        response = client.post(
            "/api/views/cont/layouts", json={"name": "Review", "overwrite": True}
        )
        assert response.status_code == 200
        assert _sidecar(root)["snapshots"]["cont"]["Review"]["views"]["u"] == [700, 0]

    @pytest.mark.parametrize("name", ["", "   ", "x" * 81])
    def test_a_name_must_be_usable(self, client: TestClient, name: str) -> None:
        response = client.post("/api/views/cont/layouts", json={"name": name})
        assert response.status_code == 422

    def test_an_unknown_view_is_404(self, client: TestClient) -> None:
        response = client.post("/api/views/nope/layouts", json={"name": "A"})
        assert response.status_code == 404

    def test_layouts_belong_to_their_view(self, client: TestClient) -> None:
        _arrange(client, 100)
        client.post("/api/views/cont/layouts", json={"name": "Review"})
        assert _names(client, "ctx") == []

    def test_names_are_listed_alphabetically(self, client: TestClient) -> None:
        for name in ("beta", "Alpha", "gamma"):
            client.post("/api/views/cont/layouts", json={"name": name})
        assert _names(client) == ["Alpha", "beta", "gamma"]

    def test_a_slash_in_a_name_works(self, client: TestClient) -> None:
        """Names travel in the body, so they need no path encoding."""
        _arrange(client, 100)
        client.post("/api/views/cont/layouts", json={"name": "Ops / on-call"})
        _arrange(client, 700)
        response = client.post(
            "/api/views/cont/layouts/apply", json={"name": "Ops / on-call"}
        )
        assert response.status_code == 200
        assert _positions(client)["u"] == (100, 0)


class TestApply:
    def test_loading_restores_the_arrangement(
        self, client: TestClient, root: Path
    ) -> None:
        _arrange(client, 100)
        client.post("/api/views/cont/layouts", json={"name": "Review"})
        _arrange(client, 700)
        assert _positions(client)["u"] == (700, 0)

        response = client.post("/api/views/cont/layouts/apply", json={"name": "Review"})
        assert response.status_code == 200
        assert _positions(client)["u"] == (100, 0)
        # The working layout on disk changed too, so it survives a reload
        # and `c4 render` draws what is on screen.
        assert _sidecar(root)["views"]["cont"]["u"] == [100, 0]
        assert _positions(_client(root))["u"] == (100, 0)

    def test_loading_replaces_sections_rather_than_merging(
        self, client: TestClient, root: Path
    ) -> None:
        """A section empty when the layout was saved is empty after loading."""
        _arrange(client, 100)
        client.post("/api/views/cont/layouts", json={"name": "Plain"})
        edge = client.get("/api/views/cont/graph").json()["edges"][0]["id"]
        _arrange(client, 700, waypoints={edge: [[1, 2]]}, routing={edge: "orthogonal"})
        client.post("/api/views/cont/expansion", json={"collapsed": ["g"]})

        client.post("/api/views/cont/layouts/apply", json={"name": "Plain"})
        document = _sidecar(root)
        assert "edges" not in document
        assert "routing" not in document
        assert "collapsed" not in document
        graph = client.get("/api/views/cont/graph").json()
        assert all("waypoints" not in e and "routing" not in e for e in graph["edges"])
        assert graph["collapsedIds"] == []

    def test_an_element_the_layout_never_placed_is_laid_out_afresh(
        self, client: TestClient
    ) -> None:
        """Old positions are cleared before applying, as a reset does."""
        client.post("/api/views/cont/layout", json={"positions": {"u": [100, 0]}})
        client.post("/api/views/cont/layouts", json={"name": "Partial"})
        _arrange(client, 700)
        client.post("/api/views/cont/layouts/apply", json={"name": "Partial"})
        assert _positions(client)["api"] is None

    def test_other_views_are_untouched(self, client: TestClient, root: Path) -> None:
        client.post("/api/views/ctx/layout", json={"positions": {"u": [5, 5]}})
        _arrange(client, 100)
        client.post("/api/views/cont/layouts", json={"name": "Review"})
        client.post("/api/views/cont/layouts/apply", json={"name": "Review"})
        assert _sidecar(root)["views"]["ctx"] == {"u": [5, 5]}

    def test_an_unknown_name_is_404(self, client: TestClient) -> None:
        response = client.post("/api/views/cont/layouts/apply", json={"name": "Nope"})
        assert response.status_code == 404


class TestDelete:
    def test_deleting_forgets_the_name_only(
        self, client: TestClient, root: Path
    ) -> None:
        _arrange(client, 100)
        client.post("/api/views/cont/layouts", json={"name": "A"})
        client.post("/api/views/cont/layouts", json={"name": "B"})
        response = client.post("/api/views/cont/layouts/delete", json={"name": "A"})
        assert response.status_code == 200
        assert [e["name"] for e in response.json()["layouts"]] == ["B"]
        assert _sidecar(root)["views"]["cont"]["u"] == [100, 0]

    def test_deleting_the_last_drops_the_section(
        self, client: TestClient, root: Path
    ) -> None:
        _arrange(client, 100)
        client.post("/api/views/cont/layouts", json={"name": "A"})
        client.post("/api/views/cont/layouts/delete", json={"name": "A"})
        assert "snapshots" not in _sidecar(root)

    def test_an_unknown_name_is_404(self, client: TestClient) -> None:
        response = client.post("/api/views/cont/layouts/delete", json={"name": "Nope"})
        assert response.status_code == 404


class TestOtherWritesKeepThem:
    """Every sidecar write rewrites the file; none may drop the section."""

    @pytest.fixture()
    def saved(self, client: TestClient, root: Path) -> TestClient:
        _arrange(client, 100)
        client.post("/api/views/cont/layouts", json={"name": "Review"})
        return client

    def test_autosave(self, saved: TestClient, root: Path) -> None:
        _arrange(saved, 700)
        assert "Review" in _sidecar(root)["snapshots"]["cont"]

    def test_expansion(self, saved: TestClient, root: Path) -> None:
        saved.post("/api/views/cont/expansion", json={"expanded": ["web"]})
        assert "Review" in _sidecar(root)["snapshots"]["cont"]

    def test_reset_keeps_named_layouts_and_they_still_load(
        self, saved: TestClient, root: Path
    ) -> None:
        assert saved.delete("/api/views/cont/layout").status_code == 200
        assert "views" not in _sidecar(root) or "cont" not in _sidecar(root)["views"]
        assert _names(saved) == ["Review"]
        saved.post("/api/views/cont/layouts/apply", json={"name": "Review"})
        assert _positions(saved)["u"] == (100, 0)


class TestViewer:
    def test_named_layouts_work_in_viewer_mode(self, root: Path) -> None:
        """Arranging a view is allowed in Viewer; only the model is not."""
        viewer = _client(root, read_only=True)
        _arrange(viewer, 100)
        assert (
            viewer.post("/api/views/cont/layouts", json={"name": "Mine"}).status_code
            == 200
        )
        assert (
            viewer.post(
                "/api/views/cont/layouts/apply", json={"name": "Mine"}
            ).status_code
            == 200
        )


class TestReader:
    def test_malformed_entries_are_dropped(self, root: Path) -> None:
        source = root / DSL_FILE
        (root / "example.layout.json").write_text(
            json.dumps(
                {
                    "snapshots": {
                        "cont": {
                            "ok": {"views": {"u": [1, 2]}, "junk": 1},
                            "bad": [],
                        },
                        "ctx": "nope",
                    }
                }
            ),
            encoding="utf-8",
        )
        assert read_snapshots(source) == {"cont": {"ok": {"views": {"u": [1, 2]}}}}

    def test_a_sidecar_without_the_section_still_loads(self, root: Path) -> None:
        source = root / DSL_FILE
        (root / "example.layout.json").write_text(
            json.dumps({"views": {"cont": {"u": [1, 2]}}}), encoding="utf-8"
        )
        assert read_snapshots(source) == {}
