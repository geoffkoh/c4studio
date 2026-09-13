"""Folder, rename and delete (PP-135).

The first routes that destroy data on the user's disk, so what is pinned
here is mostly what they *refuse*. The happy paths are one line each; the
refusals are the feature.

Creating a file has no route and needs none: ``PUT /api/source`` with a
null fingerprint asserts the file does not exist and makes its parents on
the way, so create-over-existing is already a 409.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from c4studio.webapp.server import create_app

FIXTURES = Path(__file__).parent.parent / "fixtures"
FRAGMENT = "// a fragment\n"


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    shutil.copy(FIXTURES / "example.dsl", tmp_path / "example.dsl")
    (tmp_path / "spare.dsl").write_text(FRAGMENT)
    return tmp_path


@pytest.fixture()
def client(root: Path) -> TestClient:
    test_client = TestClient(create_app(root=root))
    assert (
        test_client.post("/api/load", json={"path": "example.dsl"}).status_code == 200
    )
    return test_client


# --- creating -------------------------------------------------------------


def test_creates_a_folder(client: TestClient, root: Path) -> None:
    assert client.post("/api/folder", json={"path": "team/sub"}).status_code == 200
    assert (root / "team" / "sub").is_dir()


def test_creating_an_existing_folder_is_a_conflict(client: TestClient) -> None:
    client.post("/api/folder", json={"path": "team"})
    assert client.post("/api/folder", json={"path": "team"}).status_code == 409


def test_put_creates_a_file_with_its_parents(client: TestClient, root: Path) -> None:
    """The reason there is no create-file route."""
    response = client.put(
        "/api/source",
        json={"path": "new/deep/frag.dsl", "content": FRAGMENT, "fingerprint": None},
    )
    assert response.status_code == 200
    assert (root / "new" / "deep" / "frag.dsl").read_text() == FRAGMENT


# --- renaming -------------------------------------------------------------


def test_renames_a_file(client: TestClient, root: Path) -> None:
    response = client.post("/api/rename", json={"path": "spare.dsl", "to": "moved.dsl"})
    assert response.status_code == 200
    assert not (root / "spare.dsl").exists()
    assert (root / "moved.dsl").read_text() == FRAGMENT


def test_rename_never_clobbers(client: TestClient, root: Path) -> None:
    """The one-keystroke typo a rename route must not honour."""
    (root / "taken.dsl").write_text("// do not lose me\n")
    response = client.post("/api/rename", json={"path": "spare.dsl", "to": "taken.dsl"})
    assert response.status_code == 409
    assert (root / "taken.dsl").read_text() == "// do not lose me\n"
    assert (root / "spare.dsl").exists(), "the source must survive a refused rename"


def test_rename_carries_the_layout_across(client: TestClient, root: Path) -> None:
    """Losing an arrangement because a file was renamed is a bad surprise."""
    (root / "spare.layout.json").write_text('{"views": {"K": {}}}')
    client.post("/api/rename", json={"path": "spare.dsl", "to": "moved.dsl"})
    assert not (root / "spare.layout.json").exists()
    assert (root / "moved.layout.json").read_text() == '{"views": {"K": {}}}'


def test_cannot_rename_the_loaded_workspace(client: TestClient, root: Path) -> None:
    response = client.post(
        "/api/rename", json={"path": "example.dsl", "to": "other.dsl"}
    )
    assert response.status_code == 409
    assert (root / "example.dsl").exists()


# --- deleting -------------------------------------------------------------


def test_deletes_a_file(client: TestClient, root: Path) -> None:
    assert client.delete("/api/file", params={"path": "spare.dsl"}).status_code == 200
    assert not (root / "spare.dsl").exists()


def test_delete_removes_the_orphaned_sidecar(client: TestClient, root: Path) -> None:
    """A stale sidecar would attach itself to any future file of that name."""
    (root / "spare.layout.json").write_text("{}")
    client.delete("/api/file", params={"path": "spare.dsl"})
    assert not (root / "spare.layout.json").exists()


def test_cannot_delete_a_sidecar_directly(client: TestClient, root: Path) -> None:
    """If the listing does not show it, no route may remove it."""
    sidecar = root / "example.layout.json"
    sidecar.write_text("{}")
    response = client.delete("/api/file", params={"path": "example.layout.json"})
    assert response.status_code == 400
    assert sidecar.exists()


def test_cannot_delete_an_unsupported_suffix(client: TestClient, root: Path) -> None:
    """`!docs` markdown is outside the allowlist, so it is outside this too."""
    notes = root / "notes.md"
    notes.write_text("# notes\n")
    assert client.delete("/api/file", params={"path": "notes.md"}).status_code == 400
    assert notes.exists()


def test_cannot_delete_outside_the_root(client: TestClient) -> None:
    response = client.delete("/api/file", params={"path": "../escape.dsl"})
    assert response.status_code == 400


def test_cannot_delete_the_loaded_workspace(client: TestClient, root: Path) -> None:
    response = client.delete("/api/file", params={"path": "example.dsl"})
    assert response.status_code == 409
    assert (root / "example.dsl").exists()


def test_deleting_a_missing_file_is_404(client: TestClient) -> None:
    assert client.delete("/api/file", params={"path": "ghost.dsl"}).status_code == 404


def test_folder_delete_refuses_a_non_empty_folder(
    client: TestClient, root: Path
) -> None:
    """No recursive delete: the one operation that destroys unnamed work."""
    (root / "team").mkdir()
    (root / "team" / "keep.dsl").write_text(FRAGMENT)
    response = client.delete("/api/folder", params={"path": "team"})
    assert response.status_code == 409
    assert (root / "team" / "keep.dsl").exists()


def test_folder_delete_removes_an_empty_folder(client: TestClient, root: Path) -> None:
    (root / "empty").mkdir()
    assert client.delete("/api/folder", params={"path": "empty"}).status_code == 200
    assert not (root / "empty").exists()


def test_cannot_delete_the_root_itself(client: TestClient, root: Path) -> None:
    assert client.delete("/api/folder", params={"path": "."}).status_code == 400
    assert root.is_dir()


# --- visibility and mode --------------------------------------------------


def test_the_listing_reflects_the_change(client: TestClient) -> None:
    """C1's cache needs no invalidation: these move a directory's mtime."""
    before = {entry["path"] for entry in client.get("/api/files").json()}
    assert "spare.dsl" in before
    client.delete("/api/file", params={"path": "spare.dsl"})
    after = {entry["path"] for entry in client.get("/api/files").json()}
    assert "spare.dsl" not in after


def test_deleting_an_included_fragment_fails_soft(tmp_path: Path) -> None:
    """The project's contract: the last good workspace keeps being served."""
    shutil.copytree(FIXTURES / "split_workspace", tmp_path / "split")
    client = TestClient(create_app(root=tmp_path))
    assert (
        client.post("/api/load", json={"path": "split/workspace.dsl"}).status_code
        == 200
    )
    fragment = next(
        entry["path"]
        for entry in client.get("/api/files").json()
        if entry["kind"] == "fragment"
    )
    assert client.delete("/api/file", params={"path": fragment}).status_code == 200

    status = client.get("/api/status").json()
    assert status["error"], "a dangling !include must be reported"
    assert client.get("/api/workspace").status_code == 200


@pytest.mark.parametrize(
    ("method", "url", "kwargs"),
    [
        ("post", "/api/folder", {"json": {"path": "team"}}),
        ("post", "/api/rename", {"json": {"path": "spare.dsl", "to": "x.dsl"}}),
        ("delete", "/api/file", {"params": {"path": "spare.dsl"}}),
        ("delete", "/api/folder", {"params": {"path": "team"}}),
    ],
)
def test_viewer_refuses_every_file_operation(
    root: Path, method: str, url: str, kwargs: dict[str, object]
) -> None:
    viewer = TestClient(create_app(root=root, read_only=True))
    assert getattr(viewer, method)(url, **kwargs).status_code == 403
    assert (root / "spare.dsl").exists()
