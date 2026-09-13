"""``PUT /api/source`` — writing DSL from the app (PP-124).

The first route that writes DSL, so the tests are mostly about the ways
writing can go wrong: clobbering an edit made elsewhere, half-writing a
file, saving into a Viewer, destroying bytes a lossy read replaced, or
serving stale text afterwards.

Saving is also the render trigger — the write bumps mtime, which is what
live reload watches — so the reload happens inside the request and the
resulting ``generation`` comes back in the response.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from c4studio.webapp.server import _fingerprint, _read_source, create_app

FIXTURES = Path(__file__).parent.parent / "fixtures"

RENAMED = """workspace "Renamed" "By the editor" {
    model {
        u = person "User"
    }
    views {
        systemLandscape Landscape {
            include *
        }
    }
}
"""


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


def _fingerprint_of(client: TestClient, path: str) -> str:
    entry = next(
        f for f in client.get("/api/source").json()["files"] if f["path"] == path
    )
    fingerprint: str = entry["fingerprint"]
    return fingerprint


def _put(client: TestClient, **body: Any) -> Any:
    # Untyped on purpose: TestClient returns an httpx or httpx2 Response
    # depending on what is installed (starlette prefers httpx2 when it is
    # present, which the assistant's optional dependency brings in).
    # Naming either package here pins the suite to one of them.
    return client.put("/api/source", json=body)


# ---------------------------------------------------------------------------
# The happy path, and the race it closes
# ---------------------------------------------------------------------------


def test_a_save_writes_reloads_and_reports_the_generation(
    client: TestClient, root: Path
) -> None:
    before = client.get("/api/status").json()["generation"]
    response = _put(
        client,
        path="example.dsl",
        content=RENAMED,
        fingerprint=_fingerprint_of(client, "example.dsl"),
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert (root / "example.dsl").read_text(encoding="utf-8") == RENAMED
    assert body["reloaded"] is True
    assert body["generation"] == before + 1
    assert body["error"] is None
    assert client.get("/api/workspace").json()["name"] == "Renamed"


def test_one_save_causes_exactly_one_reload(client: TestClient) -> None:
    """The race: the save's own reload must not trigger a second one."""
    saved = _put(
        client,
        path="example.dsl",
        content=RENAMED,
        fingerprint=_fingerprint_of(client, "example.dsl"),
    ).json()
    assert client.get("/api/status").json()["generation"] == saved["generation"]


def test_the_returned_fingerprint_allows_an_immediate_second_save(
    client: TestClient,
) -> None:
    first = _put(
        client,
        path="example.dsl",
        content=RENAMED,
        fingerprint=_fingerprint_of(client, "example.dsl"),
    ).json()
    second = _put(
        client,
        path="example.dsl",
        content=RENAMED.replace("Renamed", "Again"),
        fingerprint=first["fingerprint"],
    )
    assert second.status_code == 200


# ---------------------------------------------------------------------------
# Conflicts
# ---------------------------------------------------------------------------


def test_a_stale_fingerprint_conflicts_without_clobbering(
    client: TestClient, root: Path
) -> None:
    stale = _fingerprint_of(client, "example.dsl")
    external = 'workspace "Edited elsewhere" {\n    model {\n    }\n}\n'
    (root / "example.dsl").write_text(external, encoding="utf-8")

    response = _put(client, path="example.dsl", content=RENAMED, fingerprint=stale)
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "conflict"
    # Both sides available without another round trip...
    assert detail["content"] == external
    # ...and the other edit survived.
    assert (root / "example.dsl").read_text(encoding="utf-8") == external


def test_force_overwrites_a_conflict(client: TestClient, root: Path) -> None:
    stale = _fingerprint_of(client, "example.dsl")
    (root / "example.dsl").write_text("workspace {}\n", encoding="utf-8")

    response = _put(
        client, path="example.dsl", content=RENAMED, fingerprint=stale, force=True
    )
    assert response.status_code == 200
    assert (root / "example.dsl").read_text(encoding="utf-8") == RENAMED


def test_creating_a_file_asserts_it_does_not_exist(
    client: TestClient, root: Path
) -> None:
    response = _put(
        client, path="fragments/new.dsl", content='s = softwareSystem "New"\n'
    )
    assert response.status_code == 200
    assert (root / "fragments" / "new.dsl").exists()


def test_creating_over_an_existing_file_conflicts(client: TestClient) -> None:
    """A missing fingerprint means "new file", so this is a mistake."""
    response = _put(client, path="example.dsl", content=RENAMED)
    assert response.status_code == 409


# ---------------------------------------------------------------------------
# Saving something broken
# ---------------------------------------------------------------------------


def test_invalid_dsl_saves_and_reports(client: TestClient, root: Path) -> None:
    """Refusing to save mid-thought would make the editor unusable."""
    good_name = client.get("/api/workspace").json()["name"]
    before = client.get("/api/status").json()["generation"]
    broken = 'workspace "W" {\n    model {\n        softwareSystem\n    }\n}\n'
    response = _put(
        client,
        path="example.dsl",
        content=broken,
        fingerprint=_fingerprint_of(client, "example.dsl"),
    )
    assert response.status_code == 200
    body = response.json()

    assert (root / "example.dsl").read_text(encoding="utf-8") == broken
    assert body["error"] is not None
    assert body["generation"] == before
    # The last good workspace keeps being served, so the diagram does not
    # blank out while you are mid-edit.
    assert client.get("/api/workspace").json()["name"] == good_name


def test_a_broken_save_still_serves_the_new_text(
    client: TestClient, root: Path
) -> None:
    """The source cache must not outlive the file it describes."""
    broken = "workspace {\n"
    _put(
        client,
        path="example.dsl",
        content=broken,
        fingerprint=_fingerprint_of(client, "example.dsl"),
    )
    entry = next(
        f
        for f in client.get("/api/source").json()["files"]
        if f["path"] == "example.dsl"
    )
    assert entry["content"] == broken


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------


def test_viewer_refuses_to_write_and_leaves_the_file_alone(root: Path) -> None:
    viewer = TestClient(create_app(root=root, read_only=True))
    viewer.post("/api/load", json={"path": "example.dsl"})
    before = (root / "example.dsl").read_text(encoding="utf-8")

    response = viewer.put(
        "/api/source",
        json={"path": "example.dsl", "content": RENAMED, "fingerprint": None},
    )
    assert response.status_code == 403
    assert (root / "example.dsl").read_text(encoding="utf-8") == before


def test_traversal_is_rejected(client: TestClient) -> None:
    assert _put(client, path="../escape.dsl", content="x").status_code == 400


def test_unsupported_suffixes_are_rejected(client: TestClient) -> None:
    assert _put(client, path="notes.txt", content="x").status_code == 400


def test_a_file_that_is_not_utf8_is_flagged_and_refused(
    client: TestClient, root: Path
) -> None:
    """Round-tripping replaced bytes would destroy what was really there."""
    binary = root / "binary.dsl"
    binary.write_bytes(b'workspace "B" {\n\xff\xfe\n}\n')

    # Still readable — a viewer should show something — but flagged.
    content, editable = _read_source(binary)
    assert editable is False
    assert "�" in content

    response = _put(
        client,
        path="binary.dsl",
        content="workspace {}\n",
        fingerprint=_fingerprint(binary),
    )
    assert response.status_code == 422
    assert binary.read_bytes() == b'workspace "B" {\n\xff\xfe\n}\n'


# ---------------------------------------------------------------------------
# Housekeeping
# ---------------------------------------------------------------------------


def test_no_temp_files_are_left_behind(client: TestClient, root: Path) -> None:
    _put(
        client,
        path="example.dsl",
        content=RENAMED,
        fingerprint=_fingerprint_of(client, "example.dsl"),
    )
    assert list(root.glob(".*.tmp")) == []


def test_line_endings_are_written_verbatim(client: TestClient, root: Path) -> None:
    """Saving must not rewrite every line of a file it barely touched."""
    crlf = RENAMED.replace("\n", "\r\n")
    _put(
        client,
        path="example.dsl",
        content=crlf,
        fingerprint=_fingerprint_of(client, "example.dsl"),
    )
    assert (root / "example.dsl").read_bytes().count(b"\r\n") == crlf.count("\r\n")


def test_saving_a_fragment_reloads_the_root(tmp_path: Path) -> None:
    shutil.copytree(FIXTURES / "split_workspace", tmp_path / "split")
    client = TestClient(create_app(root=tmp_path))
    client.post("/api/load", json={"path": "split/workspace.dsl"})

    fragment = "split/model/people.dsl"
    before = client.get("/api/status").json()["generation"]
    response = _put(
        client,
        path=fragment,
        content='u = person "User"\nextra = person "Extra"\n',
        fingerprint=_fingerprint_of(client, fragment),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["reloaded"] is True
    assert body["generation"] == before + 1
    names = [p["name"] for p in client.get("/api/workspace").json()["model"]["people"]]
    assert "Extra" in names


def test_os_replace_keeps_the_file_readable_throughout(
    client: TestClient, root: Path
) -> None:
    """A sibling temp plus rename: a reader never sees a partial file."""
    target = root / "example.dsl"
    inode_before = os.stat(target).st_ino
    _put(
        client,
        path="example.dsl",
        content=RENAMED,
        fingerprint=_fingerprint_of(client, "example.dsl"),
    )
    # A rename swaps the inode; an in-place truncate-and-write would not.
    assert os.stat(target).st_ino != inode_before
