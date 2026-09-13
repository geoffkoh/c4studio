"""Starter templates over the API (PP-139).

Two read routes and no writable one. Creating a workspace in the app is a
`GET /api/templates/{name}` followed by `PUT /api/source`, so it inherits
that route's 409-on-clobber and its Viewer guard rather than restating
either — and the name substitution keeps the single implementation D1
gave it.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from c4studio import templates
from c4studio.webapp.server import create_app


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(root=tmp_path))


def test_lists_every_shipped_template(client: TestClient) -> None:
    listed = client.get("/api/templates").json()
    assert [entry["name"] for entry in listed] == [
        t.name for t in templates.list_templates()
    ]
    assert all(entry["summary"] for entry in listed), "each needs a one-liner"


def test_renders_a_template(client: TestClient) -> None:
    body = client.get("/api/templates/minimal").json()
    assert body["content"] == templates.get_template("minimal").content


def test_renders_with_a_workspace_name(client: TestClient) -> None:
    body = client.get("/api/templates/minimal", params={"workspace": "Acme"}).json()
    assert '"Acme"' in body["content"]
    assert templates.DEFAULT_NAME not in body["content"]


def test_unknown_template_is_404(client: TestClient) -> None:
    assert client.get("/api/templates/nope").status_code == 404


def test_listing_is_available_in_viewer(tmp_path: Path) -> None:
    """A read. Viewer is stopped at the write it would need to use one."""
    viewer = TestClient(create_app(root=tmp_path, read_only=True))
    assert viewer.get("/api/templates").status_code == 200


def test_creating_a_workspace_is_render_then_save(
    client: TestClient, tmp_path: Path
) -> None:
    """The whole flow the dialog performs, with no route of its own."""
    content = client.get("/api/templates/full-c4", params={"workspace": "Acme"}).json()[
        "content"
    ]
    saved = client.put(
        "/api/source",
        json={"path": "acme/workspace.dsl", "content": content, "fingerprint": None},
    )
    assert saved.status_code == 200
    assert (tmp_path / "acme" / "workspace.dsl").is_file()

    loaded = client.post("/api/load", json={"path": "acme/workspace.dsl"})
    assert loaded.status_code == 200
    assert loaded.json()["name"] == "Acme"
    assert [view["key"] for view in loaded.json()["views"]] == [
        "SystemContext",
        "Containers",
        "ApiComponents",
    ]


def test_creating_over_an_existing_file_is_refused(
    client: TestClient, tmp_path: Path
) -> None:
    """Inherited from PUT, not reimplemented."""
    (tmp_path / "taken.dsl").write_text("// mine\n")
    content = client.get("/api/templates/minimal").json()["content"]
    response = client.put(
        "/api/source",
        json={"path": "taken.dsl", "content": content, "fingerprint": None},
    )
    assert response.status_code == 409
    assert (tmp_path / "taken.dsl").read_text() == "// mine\n"


def test_viewer_cannot_create_a_workspace(tmp_path: Path) -> None:
    viewer = TestClient(create_app(root=tmp_path, read_only=True))
    content = viewer.get("/api/templates/minimal").json()["content"]
    response = viewer.put(
        "/api/source",
        json={"path": "w.dsl", "content": content, "fingerprint": None},
    )
    assert response.status_code == 403
    assert not (tmp_path / "w.dsl").exists()
