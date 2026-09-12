"""A failed reload must still refresh the watched file list (PP-120).

A root that fails to parse used to keep watching the files it referenced
when it last parsed. So adding ``!include model/new.dsl`` before
``new.dsl`` exists left nothing watching ``new.dsl``, and creating it
reloaded nothing — the workspace stayed broken until the root was touched
again.

Rare with an external editor, which rewrites the root on save anyway.
The normal order in an in-app editor: declare the include, then create
the fragment.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from c4studio.webapp.server import create_app

ROOT_DSL = """
workspace "Watching" {
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


def _touch_future(path: Path, offset_ns: int = 10_000_000_000) -> None:
    """Bump a file's mtime far enough that the watch token must change."""
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + offset_ns))


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    (tmp_path / "workspace.dsl").write_text(ROOT_DSL, encoding="utf-8")
    return tmp_path


@pytest.fixture()
def client(root: Path) -> TestClient:
    test_client = TestClient(create_app(root=root))
    assert (
        test_client.post("/api/load", json={"path": "workspace.dsl"}).status_code == 200
    )
    return test_client


def test_creating_a_missing_include_target_reloads(
    client: TestClient, root: Path
) -> None:
    """Declare the include first, create the fragment second."""
    source = root / "workspace.dsl"
    source.write_text(
        ROOT_DSL.replace(
            'u = person "User"',
            'u = person "User"\n        !include model/new.dsl',
        ),
        encoding="utf-8",
    )
    _touch_future(source)

    # The include target does not exist yet, so the reload fails and the
    # last good workspace keeps being served.
    broken = client.get("/api/status").json()
    assert broken["error"] is not None
    assert broken["generation"] == 0

    fragment = root / "model" / "new.dsl"
    fragment.parent.mkdir()
    fragment.write_text('s = softwareSystem "Added"\n', encoding="utf-8")
    _touch_future(fragment)

    # Creating it must be noticed: the fragment is watched even though the
    # parse that would have discovered it failed.
    fixed = client.get("/api/status").json()
    assert fixed["error"] is None
    assert fixed["generation"] == 1
    names = [
        s["name"]
        for s in client.get("/api/workspace").json()["model"]["software_systems"]
    ]
    assert names == ["Added"]


def test_a_still_broken_source_is_not_reparsed_every_poll(
    client: TestClient, root: Path
) -> None:
    """The watch token is claimed before the attempt, not after it."""
    source = root / "workspace.dsl"
    source.write_text("workspace {\n  model {\n", encoding="utf-8")
    _touch_future(source)

    first = client.get("/api/status").json()
    assert first["error"] is not None

    state = client.app.state.app_state  # type: ignore[attr-defined]
    token_after_first = state.watch_token
    assert client.get("/api/status").json()["error"] is not None
    assert state.watch_token == token_after_first
