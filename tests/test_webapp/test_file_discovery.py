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


def test_lists_only_workspace_roots(client: TestClient) -> None:
    assert client.get("/api/files").json() == ["alpha.dsl"]


def test_unchanged_tree_is_not_read_again(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The second call must not open a single candidate file."""
    assert client.get("/api/files").json() == ["alpha.dsl"]

    def explode(path: Path) -> bool:
        raise AssertionError(f"re-read {path} when nothing changed")

    monkeypatch.setattr(server, "_is_workspace_root", explode)
    assert client.get("/api/files").json() == ["alpha.dsl"]


def test_new_workspace_is_noticed(client: TestClient, root: Path) -> None:
    assert client.get("/api/files").json() == ["alpha.dsl"]
    _touch(root / "beta.dsl", WORKSPACE)
    assert client.get("/api/files").json() == ["alpha.dsl", "beta.dsl"]


def test_deleted_workspace_is_noticed(client: TestClient, root: Path) -> None:
    assert client.get("/api/files").json() == ["alpha.dsl"]
    (root / "alpha.dsl").unlink()
    assert client.get("/api/files").json() == []


def test_fragment_gaining_a_workspace_block_is_noticed(
    client: TestClient, root: Path
) -> None:
    """The case a directory-mtime-only cache would get wrong.

    Editing a file's *contents* leaves its directory's mtime alone, so the
    file's own signature is what has to carry this.
    """
    assert client.get("/api/files").json() == ["alpha.dsl"]
    _touch(root / "model" / "frag.dsl", WORKSPACE)
    assert client.get("/api/files").json() == ["alpha.dsl", "model/frag.dsl"]


def test_workspace_losing_its_block_is_noticed(client: TestClient, root: Path) -> None:
    assert client.get("/api/files").json() == ["alpha.dsl"]
    _touch(root / "alpha.dsl", FRAGMENT)
    assert client.get("/api/files").json() == []


def test_new_directory_is_noticed(client: TestClient, root: Path) -> None:
    assert client.get("/api/files").json() == ["alpha.dsl"]
    (root / "team").mkdir()
    _touch(root / "team" / "gamma.dsl", WORKSPACE)
    assert client.get("/api/files").json() == ["alpha.dsl", "team/gamma.dsl"]


def test_cache_is_per_app(root: Path) -> None:
    """Two servers over the same root must not share a cache.

    The cache lives on AppState precisely so it cannot become the module
    global that CLAUDE.md rules out.
    """
    first = TestClient(create_app(root=root))
    assert first.get("/api/files").json() == ["alpha.dsl"]
    _touch(root / "beta.dsl", WORKSPACE)
    second = TestClient(create_app(root=root))
    assert second.get("/api/files").json() == ["alpha.dsl", "beta.dsl"]
