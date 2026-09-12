"""``GET /api/files`` discovery caching (PP-130).

The walk reads the first 8 KB of every candidate file to decide whether it
declares a ``workspace`` block. Measured on a 220-file tree that was 79% of
the endpoint's cost, so the result is cached and revalidated by stat.

What these tests pin is not the speed but the *correctness* of the
revalidation: every way the answer can change must still be noticed, and
the read must not happen again when nothing did.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from c4studio.webapp import server
from c4studio.webapp.server import create_app


def _paths(client: TestClient) -> list[str]:
    """Loadable workspace paths, the answer this endpoint used to give."""
    return [
        entry["path"]
        for entry in client.get("/api/files").json()
        if entry["kind"] == "workspace"
    ]


WORKSPACE = 'workspace "W" {\n  model {\n  }\n}\n'
FRAGMENT = "// just an include fragment\n"


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    (tmp_path / "alpha.dsl").write_text(WORKSPACE)
    (tmp_path / "model").mkdir()
    (tmp_path / "model" / "frag.dsl").write_text(FRAGMENT)
    return tmp_path


@pytest.fixture()
def client(root: Path) -> TestClient:
    return TestClient(create_app(root=root))


def _touch(path: Path, content: str) -> None:
    """Write ``content`` and force a distinct mtime.

    The cache is stat-based, so a test that rewrites a file inside one
    filesystem mtime tick would be testing the caveat rather than the
    behaviour. Production edits come from a human typing; this does not.
    """
    path.write_text(content)
    stamp = path.stat().st_mtime_ns + 2_000_000_000
    os.utime(path, ns=(stamp, stamp))


def test_lists_roots_and_fragments_apart(client: TestClient) -> None:
    assert client.get("/api/files").json() == [
        {"path": "alpha.dsl", "kind": "workspace"},
        {"path": "model/frag.dsl", "kind": "fragment"},
    ]


def test_unchanged_tree_is_not_read_again(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The second call must not open a single candidate file."""
    assert _paths(client) == ["alpha.dsl"]

    def explode(path: Path) -> str | None:
        raise AssertionError(f"re-read {path} when nothing changed")

    monkeypatch.setattr(server, "_classify", explode)
    assert _paths(client) == ["alpha.dsl"]


def test_new_workspace_is_noticed(client: TestClient, root: Path) -> None:
    assert _paths(client) == ["alpha.dsl"]
    _touch(root / "beta.dsl", WORKSPACE)
    assert _paths(client) == ["alpha.dsl", "beta.dsl"]


def test_deleted_workspace_is_noticed(client: TestClient, root: Path) -> None:
    assert _paths(client) == ["alpha.dsl"]
    (root / "alpha.dsl").unlink()
    assert _paths(client) == []


def test_fragment_gaining_a_workspace_block_is_noticed(
    client: TestClient, root: Path
) -> None:
    """The case a directory-mtime-only cache would get wrong.

    Editing a file's *contents* leaves its directory's mtime alone, so the
    file's own signature is what has to carry this.
    """
    assert _paths(client) == ["alpha.dsl"]
    _touch(root / "model" / "frag.dsl", WORKSPACE)
    assert _paths(client) == ["alpha.dsl", "model/frag.dsl"]


def test_workspace_losing_its_block_is_noticed(client: TestClient, root: Path) -> None:
    assert _paths(client) == ["alpha.dsl"]
    _touch(root / "alpha.dsl", FRAGMENT)
    assert _paths(client) == []


def test_new_directory_is_noticed(client: TestClient, root: Path) -> None:
    assert _paths(client) == ["alpha.dsl"]
    (root / "team").mkdir()
    _touch(root / "team" / "gamma.dsl", WORKSPACE)
    assert _paths(client) == ["alpha.dsl", "team/gamma.dsl"]


def test_cache_is_per_app(root: Path) -> None:
    """Two servers over the same root must not share a cache.

    The cache lives on AppState precisely so it cannot become the module
    global that CLAUDE.md rules out.
    """
    first = TestClient(create_app(root=root))
    assert _paths(first) == ["alpha.dsl"]
    _touch(root / "beta.dsl", WORKSPACE)
    second = TestClient(create_app(root=root))
    assert _paths(second) == ["alpha.dsl", "beta.dsl"]


def test_layout_sidecar_is_never_listed(client: TestClient, root: Path) -> None:
    """Sidecars used to fall out by failing the workspace-root test.

    Now that failing it merely means "fragment", excluding them has to be
    deliberate — they are gitignored per-user UI state, never edit targets.
    """
    _touch(root / "alpha.layout.json", '{"views": {}}')
    paths = [entry["path"] for entry in client.get("/api/files").json()]
    assert "alpha.layout.json" not in paths


def test_reads_a_fragment_of_no_loaded_workspace(
    client: TestClient, root: Path
) -> None:
    """GET /api/file reads any source under the root, loaded or not.

    PUT /api/source and POST /api/check already took any path; reading was
    the asymmetric one, so a fragment could be written and checked but
    never opened.
    """
    response = client.get("/api/file", params={"path": "model/frag.dsl"})
    assert response.status_code == 200
    body = response.json()
    assert body["path"] == "model/frag.dsl"
    assert body["content"] == FRAGMENT
    assert body["editable"] is True
    assert body["fingerprint"].startswith("sha256:")


def test_reading_a_missing_file_is_404(client: TestClient) -> None:
    assert client.get("/api/file", params={"path": "nope.dsl"}).status_code == 404


def test_reading_outside_the_root_is_refused(client: TestClient) -> None:
    response = client.get("/api/file", params={"path": "../secrets.dsl"})
    assert response.status_code == 400


def test_reading_an_unsupported_suffix_is_refused(
    client: TestClient, root: Path
) -> None:
    """The suffix allowlist holds here too — `!docs` markdown stays out."""
    (root / "notes.md").write_text("# notes\n")
    assert client.get("/api/file", params={"path": "notes.md"}).status_code == 400


def test_invalid_utf8_is_shown_but_not_editable(client: TestClient, root: Path) -> None:
    """Same contract GET /api/source makes: displayable, never writable."""
    (root / "broken.dsl").write_bytes(b'workspace "\xff" {\n}\n')
    body = client.get("/api/file", params={"path": "broken.dsl"}).json()
    assert body["editable"] is False
    assert "�" in body["content"]


def test_reading_is_allowed_in_viewer_mode(root: Path) -> None:
    """Viewer's guarantee is about writes; reading a file is not one."""
    viewer = TestClient(create_app(root=root, read_only=True))
    assert viewer.get("/api/file", params={"path": "model/frag.dsl"}).status_code == 200
