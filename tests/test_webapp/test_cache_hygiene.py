"""Cache bounds and invalidation (PP-134).

Two caches, and measuring turned their priority round.

The roadmap led with ``/api/workspace`` running ``dataclasses.asdict`` on
every call. Measured, that is 0.85 ms on a hedge_fund-sized workspace and
47 ms at 11,400 elements — where *parsing* the same file costs 340 ms.
Real, minor, memoised anyway because it grows with the model.

The graph cache was the actual problem, and worse than unbounded: the key
carries the expand and collapse sets, so the key space is 2**(expandable
elements) per view, reachable by ordinary clicking, and nothing was ever
evicted.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from c4studio.webapp import server
from c4studio.webapp.server import create_app

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    shutil.copy(FIXTURES / "example.dsl", tmp_path / "example.dsl")
    return tmp_path


@pytest.fixture()
def client(root: Path) -> TestClient:
    test_client = TestClient(create_app(root=root))
    assert test_client.post("/api/load", json={"path": "example.dsl"}).status_code == 200
    return test_client


def _state(client: TestClient) -> server.AppState:
    state: server.AppState = client.app.state.app_state  # type: ignore[attr-defined]
    return state


def test_graph_cache_is_bounded(client: TestClient) -> None:
    """Distinct expand sets must not accumulate without limit."""
    for index in range(server._MAX_CACHED_GRAPHS + 20):
        # Each distinct expand list is its own cache key, which is exactly
        # how the key space explodes in normal use.
        response = client.get(
            "/api/views/SystemContext/graph", params={"expand": f"ghost{index}"}
        )
        assert response.status_code == 200
    assert len(_state(client).diagrams) <= server._MAX_CACHED_GRAPHS


def test_eviction_is_least_recently_used(client: TestClient) -> None:
    """A re-read entry must outlive newer ones, or the cap costs more than it saves.

    The ordering here is the whole test, and an earlier version of it was
    worthless: it re-read the keeper *last*, so the keeper was freshly
    inserted whatever the eviction policy, and a plain FIFO cache passed
    it. The keeper must be touched, then pushed past the cap by other
    entries, and only then looked for.
    """
    keeper = {"expand": "keeper"}
    graph_url = "/api/views/SystemContext/graph"
    client.get(graph_url, params=keeper)

    # Fill to exactly the cap, leaving the keeper as the oldest entry.
    for index in range(server._MAX_CACHED_GRAPHS - 1):
        client.get(graph_url, params={"expand": f"n{index}"})
    assert len(_state(client).diagrams) == server._MAX_CACHED_GRAPHS

    # Touch it: under LRU this moves it to the back, under FIFO it does not.
    client.get(graph_url, params=keeper)

    # Now evict ten, without touching the keeper again.
    for index in range(10):
        client.get(graph_url, params={"expand": f"m{index}"})

    cached = [key for key in _state(client).diagrams if "keeper" in key]
    assert cached, "the recently used entry was evicted ahead of older ones"


def test_workspace_payload_is_memoised(client: TestClient) -> None:
    first = client.get("/api/workspace")
    assert first.status_code == 200
    assert _state(client).workspace_cache is not None
    assert client.get("/api/workspace").json() == first.json()


def test_reload_drops_the_workspace_payload(client: TestClient, root: Path) -> None:
    client.get("/api/workspace")
    assert _state(client).workspace_cache is not None

    source = root / "example.dsl"
    source.write_text(source.read_text().replace("Internet Banking", "Renamed", 1))
    # The poll path reloads and must forget everything derived from the
    # workspace it replaced.
    client.get("/api/status")
    assert _state(client).workspace_cache is None
    assert client.get("/api/workspace").json()["name"] == "Renamed"


def test_saving_a_layout_drops_the_workspace_payload(client: TestClient) -> None:
    """The invalidation that is easy to miss.

    ``apply_positions`` mutates the view **in place**, so the model the
    memoised ``asdict`` was taken from is no longer the model. Without this
    the endpoint would serve coordinates that had been overwritten.
    """
    client.get("/api/workspace")
    assert _state(client).workspace_cache is not None
    client.post(
        "/api/views/SystemContext/layout", json={"positions": {"customer": [42, 99]}}
    )
    assert _state(client).workspace_cache is None


def test_resetting_a_layout_drops_the_workspace_payload(client: TestClient) -> None:
    client.post(
        "/api/views/SystemContext/layout", json={"positions": {"customer": [42, 99]}}
    )
    client.get("/api/workspace")
    assert _state(client).workspace_cache is not None
    client.delete("/api/views/SystemContext/layout")
    assert _state(client).workspace_cache is None
