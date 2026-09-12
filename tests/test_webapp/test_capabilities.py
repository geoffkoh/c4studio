"""Studio and Viewer modes (PP-119).

Studio is the default: the server allows DSL editing. ``--viewer`` opts
into Viewer, where routes that write DSL refuse with 403 — but layout and
expansion still persist, because arranging a diagram is part of reading
it and the sidecar holding that arrangement is per-user UI state either
way.

No DSL write route exists yet; this lands the guard rail first so every
later write route is guarded from birth.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from c4studio.webapp.server import create_app

FIXTURE = Path(__file__).parent.parent / "fixtures" / "example.dsl"


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    shutil.copy(FIXTURE, tmp_path / "example.dsl")
    return tmp_path


@pytest.fixture()
def client(root: Path) -> TestClient:
    """A Studio (default, editable) client with the fixture loaded."""
    test_client = TestClient(create_app(root=root))
    assert (
        test_client.post("/api/load", json={"path": "example.dsl"}).status_code == 200
    )
    return test_client


@pytest.fixture()
def viewer_client(root: Path) -> TestClient:
    """A Viewer (read-only) client with the fixture loaded."""
    test_client = TestClient(create_app(root=root, read_only=True))
    assert (
        test_client.post("/api/load", json={"path": "example.dsl"}).status_code == 200
    )
    return test_client


def test_studio_is_the_default(client: TestClient) -> None:
    body = client.get("/api/capabilities").json()
    assert body["readOnly"] is False
    assert body["mode"] == "studio"
    assert body["features"]["editSource"] is True


def test_viewer_reports_itself(viewer_client: TestClient) -> None:
    body = viewer_client.get("/api/capabilities").json()
    assert body["readOnly"] is True
    assert body["mode"] == "viewer"
    assert body["features"]["editSource"] is False


def test_capabilities_answers_without_a_workspace(root: Path) -> None:
    """It describes the server, not a workspace, so it must not 409."""
    fresh = TestClient(create_app(root=root))
    response = fresh.get("/api/capabilities")
    assert response.status_code == 200
    assert response.json()["mode"] == "studio"


def test_viewer_still_arranges_diagrams(viewer_client: TestClient) -> None:
    """You cannot change the model, but you can arrange the view."""
    saved = viewer_client.post(
        "/api/views/SystemContext/layout",
        json={"positions": {"customer": [10, 20]}},
    )
    assert saved.status_code == 200

    expansion = viewer_client.post(
        "/api/views/SystemContext/expansion",
        json={"expanded": [], "collapsed": []},
    )
    assert expansion.status_code == 200

    assert viewer_client.delete("/api/views/SystemContext/layout").status_code == 200


def test_viewer_still_reads_everything(viewer_client: TestClient) -> None:
    for path in (
        "/api/files",
        "/api/status",
        "/api/source",
        "/api/workspace",
        "/api/views",
        "/api/views/SystemContext/graph",
    ):
        assert viewer_client.get(path).status_code == 200, path
