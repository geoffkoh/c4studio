"""Integration tests for the webapp FastAPI backend."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from c4studio.webapp.server import create_app

FIXTURE = Path(__file__).parent.parent / "fixtures" / "example.dsl"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """Return a source root containing a copy of the example fixture."""
    shutil.copy(FIXTURE, tmp_path / "example.dsl")
    return tmp_path


@pytest.fixture
def client(root: Path) -> TestClient:
    """Return a TestClient for an app rooted at the fixture directory."""
    return TestClient(create_app(root=root))


def _load(client: TestClient) -> None:
    """Load the example workspace via the API."""
    response = client.post("/api/load", json={"path": "example.dsl"})
    assert response.status_code == 200


def test_files_lists_fixture(client: TestClient) -> None:
    response = client.get("/api/files")
    assert response.status_code == 200
    assert "example.dsl" in response.json()


def test_files_hides_include_fragments(root: Path) -> None:
    split = Path(__file__).parent.parent / "fixtures" / "split_workspace"
    shutil.copytree(split, root / "split_workspace")
    client = TestClient(create_app(root=root))
    files = client.get("/api/files").json()
    assert "split_workspace/workspace.dsl" in files
    # Fragment files without a workspace block are not offered for loading.
    assert not any("model/" in f for f in files)


def test_load_split_workspace_resolves_includes(root: Path) -> None:
    split = Path(__file__).parent.parent / "fixtures" / "split_workspace"
    shutil.copytree(split, root / "split_workspace")
    client = TestClient(create_app(root=root))
    response = client.post("/api/load", json={"path": "split_workspace/workspace.dsl"})
    assert response.status_code == 200
    assert response.json()["name"] == "Split Workspace"


def test_load_then_workspace_has_software_systems(client: TestClient) -> None:
    _load(client)
    response = client.get("/api/workspace")
    assert response.status_code == 200
    data = response.json()
    assert data["model"]["software_systems"]


def test_load_returns_views_index(client: TestClient) -> None:
    response = client.post("/api/load", json={"path": "example.dsl"})
    body = response.json()
    assert body["name"] == "Internet Banking"
    assert body["path"] == "example.dsl"
    assert any(v["key"] == "SystemContext" for v in body["views"])


def test_views_marks_system_context_supported(client: TestClient) -> None:
    _load(client)
    response = client.get("/api/views")
    assert response.status_code == 200
    views = {v["key"]: v for v in response.json()}
    assert views["SystemContext"]["type"] == "systemContext"
    assert views["SystemContext"]["supported"] is True


def test_view_graph_has_nodes_and_edges(client: TestClient) -> None:
    _load(client)
    response = client.get("/api/views/SystemContext/graph")
    assert response.status_code == 200
    data = response.json()
    assert data["nodes"]
    assert data["edges"]
    node = data["nodes"][0]
    assert set(node["data"]) == {
        "label",
        "kind",
        "color",
        "technology",
        "description",
        "tags",
    }


def test_unknown_view_key_returns_404(client: TestClient) -> None:
    _load(client)
    response = client.get("/api/views/does-not-exist/graph")
    assert response.status_code == 404


def test_workspace_before_load_returns_409(client: TestClient) -> None:
    response = client.get("/api/workspace")
    assert response.status_code == 409


def test_path_traversal_rejected(client: TestClient) -> None:
    response = client.post("/api/load", json={"path": "../../etc/passwd"})
    assert response.status_code == 400


def _touch_future(path: Path, offset_ns: int = 10_000_000_000) -> None:
    """Bump a file's mtime far enough that the watch token must change."""
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + offset_ns))


def test_status_before_load_is_empty(client: TestClient) -> None:
    body = client.get("/api/status").json()
    assert body == {"path": None, "generation": 0, "error": None}


def test_status_reloads_when_source_changes(client: TestClient, root: Path) -> None:
    _load(client)
    assert client.get("/api/status").json()["generation"] == 0

    source = root / "example.dsl"
    source.write_text(
        source.read_text(encoding="utf-8").replace(
            '"Internet Banking"', '"Renamed Banking"'
        ),
        encoding="utf-8",
    )
    _touch_future(source)

    body = client.get("/api/status").json()
    assert body["generation"] == 1
    assert body["error"] is None
    assert client.get("/api/workspace").json()["name"] == "Renamed Banking"


def test_status_reloads_when_include_fragment_changes(root: Path) -> None:
    split = Path(__file__).parent.parent / "fixtures" / "split_workspace"
    shutil.copytree(split, root / "split_workspace")
    client = TestClient(create_app(root=root))
    response = client.post("/api/load", json={"path": "split_workspace/workspace.dsl"})
    assert response.status_code == 200

    fragment = root / "split_workspace" / "model" / "people.dsl"
    fragment.write_text('user = person "Renamed User"\n', encoding="utf-8")
    _touch_future(fragment)

    body = client.get("/api/status").json()
    assert body["generation"] == 1
    workspace = client.get("/api/workspace").json()
    assert workspace["model"]["people"][0]["name"] == "Renamed User"


def test_status_keeps_old_workspace_on_parse_error(
    client: TestClient, root: Path
) -> None:
    _load(client)
    source = root / "example.dsl"
    source.write_text("workspace", encoding="utf-8")  # missing { -> ParseError
    _touch_future(source)

    body = client.get("/api/status").json()
    assert body["generation"] == 0
    assert body["error"] is not None
    # The previously loaded workspace is still served.
    assert client.get("/api/workspace").json()["name"] == "Internet Banking"


def test_layout_saves_to_sidecar_and_restores_on_reload(
    client: TestClient, root: Path
) -> None:
    _load(client)
    response = client.post(
        "/api/views/SystemContext/layout",
        json={"positions": {"customer": [100, 200], "bank": [300, 400]}},
    )
    assert response.status_code == 200
    sidecar = root / "example.layout.json"
    assert sidecar.is_file()

    # The current session serves the positions...
    graph = client.get("/api/views/SystemContext/graph").json()
    positions = {n["id"]: n.get("position") for n in graph["nodes"]}
    assert positions["customer"] == {"x": 100, "y": 200}

    # ...and so does a brand new session loading the same source.
    fresh = TestClient(create_app(root=root))
    fresh.post("/api/load", json={"path": "example.dsl"})
    graph = fresh.get("/api/views/SystemContext/graph").json()
    positions = {n["id"]: n.get("position") for n in graph["nodes"]}
    assert positions["customer"] == {"x": 100, "y": 200}
    assert positions["bank"] == {"x": 300, "y": 400}


def test_layout_sidecar_hidden_from_file_browser(
    client: TestClient, root: Path
) -> None:
    _load(client)
    client.post(
        "/api/views/SystemContext/layout", json={"positions": {"customer": [1, 2]}}
    )
    assert "example.layout.json" not in client.get("/api/files").json()


def test_layout_survives_live_reload(client: TestClient, root: Path) -> None:
    _load(client)
    client.post(
        "/api/views/SystemContext/layout",
        json={"positions": {"customer": [10, 20]}},
    )
    source = root / "example.dsl"
    _touch_future(source)
    assert client.get("/api/status").json()["generation"] == 1
    graph = client.get("/api/views/SystemContext/graph").json()
    positions = {n["id"]: n.get("position") for n in graph["nodes"]}
    assert positions["customer"] == {"x": 10, "y": 20}


def test_layout_persists_boundary_sizes(client: TestClient, root: Path) -> None:
    _load(client)
    response = client.post(
        "/api/views/Containers/layout",
        json={
            "positions": {"bank": [10, 20], "webapp": [50, 80]},
            "sizes": {"bank": [900, 600]},
        },
    )
    assert response.status_code == 200

    graph = client.get("/api/views/Containers/graph").json()
    by_id = {n["id"]: n for n in graph["nodes"]}
    assert by_id["bank"]["size"] == {"width": 900, "height": 600}
    assert "size" not in by_id["webapp"]

    # A fresh session restores the size from the sidecar.
    fresh = TestClient(create_app(root=root))
    fresh.post("/api/load", json={"path": "example.dsl"})
    graph = fresh.get("/api/views/Containers/graph").json()
    by_id = {n["id"]: n for n in graph["nodes"]}
    assert by_id["bank"]["size"] == {"width": 900, "height": 600}

    # Delete clears sizes along with positions.
    client.delete("/api/views/Containers/layout")
    graph = client.get("/api/views/Containers/graph").json()
    assert all("size" not in n for n in graph["nodes"])


def test_delete_layout_returns_to_auto_layout(client: TestClient, root: Path) -> None:
    _load(client)
    client.post(
        "/api/views/SystemContext/layout",
        json={"positions": {"customer": [10, 20]}},
    )
    response = client.delete("/api/views/SystemContext/layout")
    assert response.status_code == 200
    graph = client.get("/api/views/SystemContext/graph").json()
    assert all("position" not in n for n in graph["nodes"])
    # Sidecar removed once its last view entry is gone.
    assert not (root / "example.layout.json").exists()


def test_source_before_load_returns_409(client: TestClient) -> None:
    assert client.get("/api/source").status_code == 409


def test_source_returns_fragments_and_locations(root: Path) -> None:
    split = Path(__file__).parent.parent / "fixtures" / "split_workspace"
    shutil.copytree(split, root / "split_workspace")
    client = TestClient(create_app(root=root))
    client.post("/api/load", json={"path": "split_workspace/workspace.dsl"})

    body = client.get("/api/source").json()
    paths = [f["path"] for f in body["files"]]
    assert paths[0] == "split_workspace/workspace.dsl"
    assert "split_workspace/model/people.dsl" in paths
    assert "split_workspace/model/relationships.dsl" in paths
    assert 'user = person "User"' in body["files"][1]["content"] or any(
        'user = person "User"' in f["content"] for f in body["files"]
    )
    assert body["locations"]["user"] == {
        "path": "split_workspace/model/people.dsl",
        "line": 1,
    }
    assert body["locations"]["core"]["path"] == "split_workspace/model/systems.dsl"


def test_source_refreshes_after_live_reload(client: TestClient, root: Path) -> None:
    _load(client)
    first = client.get("/api/source").json()
    assert "Internet Banking" in first["files"][0]["content"]

    source = root / "example.dsl"
    source.write_text(
        source.read_text(encoding="utf-8").replace(
            '"Internet Banking"', '"Renamed Banking"'
        ),
        encoding="utf-8",
    )
    _touch_future(source)
    assert client.get("/api/status").json()["generation"] == 1
    refreshed = client.get("/api/source").json()
    assert "Renamed Banking" in refreshed["files"][0]["content"]


def test_no_static_dir_serves_not_built_hint(root: Path, tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"
    client = TestClient(create_app(root=root, static_dir=missing))
    response = client.get("/")
    assert response.status_code == 200
    assert "not built" in response.json()["detail"]


def test_built_static_dir_serves_index(root: Path, tmp_path: Path) -> None:
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text(
        "<!doctype html><title>spa</title>", encoding="utf-8"
    )
    client = TestClient(create_app(root=root, static_dir=static_dir))
    response = client.get("/")
    assert response.status_code == 200
    assert "<title>spa</title>" in response.text


def test_edge_ids_are_numbered_per_pair(client: TestClient) -> None:
    """Ids must not shift when an unrelated edge appears in the view.

    Saved waypoints are keyed by edge id, and most DSL relationships carry
    no explicit id, so the fallback id has to be stable across edits that
    leave a given endpoint pair alone.
    """
    _load(client)
    ids = {
        e["id"] for e in client.get("/api/views/SystemContext/graph").json()["edges"]
    }
    assert ids == {
        "customer__bank__0",
        "bank__email__0",
        "bank__mainframe__0",
        "email__customer__0",
    }


def test_layout_persists_edge_waypoints(client: TestClient, root: Path) -> None:
    _load(client)
    points = [[120, 240], [180, 260]]
    response = client.post(
        "/api/views/SystemContext/layout",
        json={
            "positions": {"customer": [10, 20]},
            "waypoints": {"customer__bank__0": points},
        },
    )
    assert response.status_code == 200

    sidecar = json.loads((root / "example.layout.json").read_text(encoding="utf-8"))
    assert sidecar["edges"]["SystemContext"]["customer__bank__0"] == points

    # Served to the current session...
    graph = client.get("/api/views/SystemContext/graph").json()
    by_id = {e["id"]: e for e in graph["edges"]}
    assert by_id["customer__bank__0"]["waypoints"] == points
    assert "waypoints" not in by_id["bank__email__0"]

    # ...and to a fresh one loading the same source.
    fresh = TestClient(create_app(root=root))
    fresh.post("/api/load", json={"path": "example.dsl"})
    graph = fresh.get("/api/views/SystemContext/graph").json()
    by_id = {e["id"]: e for e in graph["edges"]}
    assert by_id["customer__bank__0"]["waypoints"] == points


def test_layout_persists_dragged_label_offsets(client: TestClient, root: Path) -> None:
    """Label offsets take the same route as waypoints (PP-100)."""
    _load(client)
    response = client.post(
        "/api/views/SystemContext/layout",
        json={
            "positions": {"customer": [10, 20]},
            "labels": {"customer__bank__0": [40, -25]},
        },
    )
    assert response.status_code == 200

    sidecar = json.loads((root / "example.layout.json").read_text(encoding="utf-8"))
    assert sidecar["labels"]["SystemContext"]["customer__bank__0"] == [40, -25]

    graph = client.get("/api/views/SystemContext/graph").json()
    by_id = {e["id"]: e for e in graph["edges"]}
    assert by_id["customer__bank__0"]["labelOffset"] == [40, -25]
    assert "labelOffset" not in by_id["bank__email__0"]

    # ...and to a fresh session loading the same source.
    fresh = TestClient(create_app(root=root))
    fresh.post("/api/load", json={"path": "example.dsl"})
    graph = fresh.get("/api/views/SystemContext/graph").json()
    assert {e["id"]: e for e in graph["edges"]}["customer__bank__0"]["labelOffset"] == [
        40,
        -25,
    ]


def test_label_dragged_back_to_default_is_not_persisted(
    client: TestClient, root: Path
) -> None:
    """The sidecar records deviations, not zeroes."""
    _load(client)
    client.post(
        "/api/views/SystemContext/layout",
        json={"positions": {}, "labels": {"customer__bank__0": [40, -25]}},
    )
    client.post(
        "/api/views/SystemContext/layout",
        json={"positions": {}, "labels": {"customer__bank__0": [0, 0]}},
    )
    sidecar_path = root / "example.layout.json"
    if sidecar_path.exists():
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        assert "SystemContext" not in sidecar.get("labels", {})
    graph = client.get("/api/views/SystemContext/graph").json()
    assert all("labelOffset" not in e for e in graph["edges"])


def test_delete_layout_clears_label_offsets(client: TestClient, root: Path) -> None:
    _load(client)
    client.post(
        "/api/views/SystemContext/layout",
        json={
            "positions": {"customer": [1, 2]},
            "labels": {"customer__bank__0": [8, 9]},
        },
    )
    assert client.delete("/api/views/SystemContext/layout").status_code == 200
    graph = client.get("/api/views/SystemContext/graph").json()
    assert all("labelOffset" not in e for e in graph["edges"])


def test_sidecars_without_a_labels_section_still_load(
    client: TestClient, root: Path
) -> None:
    """Sidecars written before label dragging existed must keep working."""
    _load(client)
    (root / "example.layout.json").write_text(
        json.dumps({"version": 1, "views": {"SystemContext": {"customer": [5, 6]}}}),
        encoding="utf-8",
    )
    fresh = TestClient(create_app(root=root))
    fresh.post("/api/load", json={"path": "example.dsl"})
    graph = fresh.get("/api/views/SystemContext/graph").json()
    assert graph["nodes"]
    assert all("labelOffset" not in e for e in graph["edges"])


def test_clearing_waypoints_drops_them_from_the_sidecar(
    client: TestClient, root: Path
) -> None:
    _load(client)
    client.post(
        "/api/views/SystemContext/layout",
        json={
            "positions": {"customer": [10, 20]},
            "waypoints": {"customer__bank__0": [[1, 2]]},
        },
    )
    client.post(
        "/api/views/SystemContext/layout",
        json={"positions": {"customer": [10, 20]}, "waypoints": {}},
    )
    sidecar = json.loads((root / "example.layout.json").read_text(encoding="utf-8"))
    assert "edges" not in sidecar
    graph = client.get("/api/views/SystemContext/graph").json()
    assert all("waypoints" not in e for e in graph["edges"])


def test_delete_layout_clears_waypoints(client: TestClient, root: Path) -> None:
    _load(client)
    client.post(
        "/api/views/SystemContext/layout",
        json={"positions": {}, "waypoints": {"customer__bank__0": [[5, 6]]}},
    )
    assert client.delete("/api/views/SystemContext/layout").status_code == 200
    # Reset means auto-layout, which includes straight edges.
    assert not (root / "example.layout.json").exists()
    graph = client.get("/api/views/SystemContext/graph").json()
    assert all("waypoints" not in e for e in graph["edges"])


def test_legacy_sidecar_without_edges_section_still_loads(root: Path) -> None:
    """Sidecars written before waypoints existed must keep working."""
    (root / "example.layout.json").write_text(
        json.dumps({"version": 1, "views": {"SystemContext": {"customer": [7, 8]}}}),
        encoding="utf-8",
    )
    client = TestClient(create_app(root=root))
    client.post("/api/load", json={"path": "example.dsl"})
    graph = client.get("/api/views/SystemContext/graph").json()
    positions = {n["id"]: n.get("position") for n in graph["nodes"]}
    assert positions["customer"] == {"x": 7, "y": 8}
    assert all("waypoints" not in e for e in graph["edges"])
