"""``POST /api/check`` — diagnostics for text that is not on disk (PP-122).

The editor's feedback loop. It answers a question about some text and
changes nothing: no file written, no workspace replaced, no cache
dropped, no generation bumped.

A fragment is not a valid workspace on its own, so a buffer belonging to
the loaded workspace is parsed in its root's context with the buffer
standing in for the file on disk.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from c4studio.webapp.server import create_app

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    shutil.copy(FIXTURES / "example.dsl", tmp_path / "example.dsl")
    return tmp_path


@pytest.fixture()
def client(root: Path) -> TestClient:
    test_client = TestClient(create_app(root=root))
    assert (
        test_client.post("/api/load", json={"path": "example.dsl"}).status_code == 200
    )
    return test_client


@pytest.fixture()
def split(tmp_path: Path) -> TestClient:
    """A client over the multi-file fixture, for fragment checking."""
    shutil.copytree(FIXTURES / "split_workspace", tmp_path / "split")
    test_client = TestClient(create_app(root=tmp_path))
    assert (
        test_client.post("/api/load", json={"path": "split/workspace.dsl"}).status_code
        == 200
    )
    return test_client


def _check(client: TestClient, path: str, content: str) -> dict[str, Any]:
    response = client.post("/api/check", json={"path": path, "content": content})
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def test_clean_text_reports_nothing(client: TestClient, root: Path) -> None:
    body = _check(
        client, "example.dsl", (root / "example.dsl").read_text(encoding="utf-8")
    )
    assert body["ok"] is True
    assert body["diagnostics"] == []
    assert body["name"]


def test_a_broken_buffer_reports_with_a_placeable_position(
    client: TestClient,
) -> None:
    body = _check(
        client,
        "example.dsl",
        'workspace "W" {\n    model {\n        softwareSystem\n    }\n}\n',
    )
    assert body["ok"] is False
    first = body["diagnostics"][0]
    assert first["path"] == "example.dsl"
    assert first["line"] == 3
    assert first["severity"] == "error"


def test_every_problem_is_reported_not_just_the_first(client: TestClient) -> None:
    body = _check(
        client,
        "example.dsl",
        'workspace "W" {\n'
        "    model {\n"
        "        softwareSystem\n"
        "        container\n"
        "    }\n"
        "}\n",
    )
    assert len(body["diagnostics"]) >= 2


def test_warnings_are_reported_but_still_ok(client: TestClient) -> None:
    """Skipped constructs are worth showing; they are not failures."""
    body = _check(
        client,
        "example.dsl",
        'workspace "W" {\n    model {\n        !bogus thing\n    }\n}\n',
    )
    assert body["ok"] is True
    assert any(d["severity"] == "warning" for d in body["diagnostics"])


def test_checking_changes_nothing(client: TestClient, root: Path) -> None:
    """The whole contract: it is a question, not an edit."""
    before_disk = (root / "example.dsl").read_text(encoding="utf-8")
    before_status = client.get("/api/status").json()
    before_workspace = client.get("/api/workspace").json()

    _check(client, "example.dsl", "total nonsense {{{\n")

    assert (root / "example.dsl").read_text(encoding="utf-8") == before_disk
    after_status = client.get("/api/status").json()
    assert after_status["generation"] == before_status["generation"]
    assert after_status["error"] is None
    assert client.get("/api/workspace").json() == before_workspace


def test_an_unsaved_fragment_is_checked_in_its_root_context(
    split: TestClient,
) -> None:
    """Alone, a fragment has no `workspace` block and reports nonsense."""
    body = _check(
        split, "split/model/people.dsl", 'u = person "User"\np = person "Second"\n'
    )
    assert body["ok"] is True, body["diagnostics"]
    assert body["diagnostics"] == []


def test_a_diagnostic_in_a_fragment_names_the_fragment(split: TestClient) -> None:
    """So the editor underlines the file the user is actually looking at."""
    body = _check(split, "split/model/people.dsl", 'u = person "User"\n!bogus thing\n')
    directive = next(
        d for d in body["diagnostics"] if "unsupported directive" in d["message"]
    )
    assert directive["path"] == "split/model/people.dsl"
    assert directive["line"] == 2


def test_the_view_list_previews_an_edit(client: TestClient) -> None:
    """A view added in the buffer shows up before the file is saved."""
    added = (
        'workspace "W" {\n'
        "    model {\n"
        '        s = softwareSystem "S"\n'
        "    }\n"
        "    views {\n"
        "        systemContext s BrandNew {\n"
        "            include *\n"
        "        }\n"
        "    }\n"
        "}\n"
    )
    body = _check(client, "example.dsl", added)
    assert "BrandNew" in [v["key"] for v in body["views"]]
    # ...and not in the workspace that is actually loaded.
    assert "BrandNew" not in [v["key"] for v in client.get("/api/views").json()]


def test_check_is_available_in_viewer_mode(root: Path) -> None:
    """Checking is a read; Viewer wants diagnostics for what it displays."""
    viewer = TestClient(create_app(root=root, read_only=True))
    viewer.post("/api/load", json={"path": "example.dsl"})
    response = viewer.post(
        "/api/check", json={"path": "example.dsl", "content": 'workspace "W" {}\n'}
    )
    assert response.status_code == 200


def test_check_rejects_traversal(client: TestClient) -> None:
    response = client.post(
        "/api/check", json={"path": "../../etc/passwd", "content": ""}
    )
    assert response.status_code == 400


def test_status_surfaces_skipped_constructs(root: Path) -> None:
    """Viewer gains warning display, independent of any editing."""
    (root / "warny.dsl").write_text(
        'workspace "W" {\n    model {\n        !bogus thing\n    }\n}\n',
        encoding="utf-8",
    )
    client = TestClient(create_app(root=root))
    client.post("/api/load", json={"path": "warny.dsl"})
    body = client.get("/api/status").json()
    assert body["error"] is None
    assert [d["path"] for d in body["diagnostics"]] == ["warny.dsl"]
