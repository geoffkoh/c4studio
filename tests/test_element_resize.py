"""Element boxes resized in the Studio (PP-224).

Only boundaries used to be resizable. An element's size is stored the way
a boundary's always was — ``[x, y, width, height]`` in the sidecar's
``views`` entry — so an older sidecar still loads and named layouts carry
it unchanged. These tests hold the server and ``c4 render`` to it; the
resize handles themselves are exercised in ``e2e/element-resize.spec.ts``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from c4studio.models import View, Workspace
from c4studio.parser.dsl import parse_dsl
from c4studio.render import RenderError, _payload_with_layout, node_executable
from c4studio.webapp.server import create_app

DSL = """
workspace "W" {
    model {
        u = person "User"
        s = softwareSystem "S" {
            web = container "Web" "Serves the single-page app to every browser that asks"
            api = container "API"
        }
        u -> web "Uses"
        web -> api "Calls"
    }
    views {
        container s "cont" {
            include *
        }
    }
}
"""

POSITIONS: dict[str, list[int]] = {
    "u": [0, 0],
    "s": [0, 250, 700, 400],
    "web": [40, 300],
    "api": [400, 300],
}
DSL_FILE = "example.dsl"


def _node_available() -> bool:
    try:
        node_executable()
    except RenderError:
        return False
    return True


needs_node = pytest.mark.skipif(not _node_available(), reason="no node")


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    (tmp_path / DSL_FILE).write_text(DSL, encoding="utf-8")
    return tmp_path


@pytest.fixture()
def client(root: Path) -> TestClient:
    client = TestClient(create_app(root=root))
    assert client.post("/api/load", json={"path": DSL_FILE}).status_code == 200
    return client


def _sidecar(root: Path) -> dict[str, Any]:
    document: dict[str, Any] = json.loads(
        (root / "example.layout.json").read_text(encoding="utf-8")
    )
    return document


def _nodes(client: TestClient) -> dict[str, Any]:
    return {n["id"]: n for n in client.get("/api/views/cont/graph").json()["nodes"]}


def _save(client: TestClient, sizes: dict[str, list[int]]) -> None:
    response = client.post(
        "/api/views/cont/layout",
        json={
            "positions": {eid: g[:2] for eid, g in POSITIONS.items()},
            "sizes": {"s": [700, 400], **sizes},
        },
    )
    assert response.status_code == 200


class TestServer:
    def test_a_resized_element_is_saved_served_and_reloaded(
        self, client: TestClient, root: Path
    ) -> None:
        _save(client, {"web": [320, 180]})
        assert _sidecar(root)["views"]["cont"]["web"] == [40, 300, 320, 180]
        assert _nodes(client)["web"]["size"] == {"width": 320, "height": 180}

        fresh = TestClient(create_app(root=root))
        fresh.post("/api/load", json={"path": DSL_FILE})
        assert _nodes(fresh)["web"]["size"] == {"width": 320, "height": 180}

    def test_an_element_nobody_resized_has_no_size(
        self, client: TestClient, root: Path
    ) -> None:
        """So it keeps growing to fit its text when the text changes."""
        _save(client, {"web": [320, 180]})
        assert _sidecar(root)["views"]["cont"]["api"] == [400, 300]
        assert "size" not in _nodes(client)["api"]

    def test_reset_layout_forgets_it(self, client: TestClient) -> None:
        _save(client, {"web": [320, 180]})
        assert client.delete("/api/views/cont/layout").status_code == 200
        assert "size" not in _nodes(client)["web"]

    def test_named_layouts_capture_and_restore_it(self, client: TestClient) -> None:
        _save(client, {"web": [320, 180]})
        client.post("/api/views/cont/layouts", json={"name": "Wide"})
        _save(client, {})
        assert "size" not in _nodes(client)["web"]
        client.post("/api/views/cont/layouts/apply", json={"name": "Wide"})
        assert _nodes(client)["web"]["size"] == {"width": 320, "height": 180}


def _view(workspace: Workspace) -> View:
    return next(v for v in workspace.views if v.key == "cont")


def _write_sidecar(source: Path, views: dict[str, list[int]]) -> None:
    source.with_name(f"{source.stem}.layout.json").write_text(
        json.dumps({"version": 1, "views": {"cont": views}}), encoding="utf-8"
    )


class TestRender:
    def test_the_payload_carries_the_size(self, tmp_path: Path) -> None:
        source = tmp_path / "ws.dsl"
        source.write_text(DSL, encoding="utf-8")
        _write_sidecar(source, {**POSITIONS, "web": [40, 300, 320, 180]})
        workspace = parse_dsl(DSL)
        payload = _payload_with_layout(workspace, _view(workspace), source)
        by_id = {n["id"]: n for n in payload["nodes"]}
        assert by_id["web"]["size"] == {"width": 320, "height": 180}
        assert "size" not in by_id["api"]

    @needs_node
    def test_it_draws_the_box_at_that_size_and_wraps_to_it(
        self, tmp_path: Path
    ) -> None:
        """Wider than the default 200, so the description takes fewer lines."""
        from c4studio.render import render_view

        source = tmp_path / "ws.dsl"
        source.write_text(DSL, encoding="utf-8")
        workspace = parse_dsl(DSL)

        def description_lines(views: dict[str, list[int]]) -> tuple[bool, int]:
            _write_sidecar(source, views)
            svg = render_view(workspace, _view(workspace), layout_source=source)
            sized = re.search(r'<rect [^>]*width="320" height="180"', svg) is not None
            lines = [
                t
                for t in re.findall(r"<text[^>]*>([^<]*)</text>", svg)
                if t.split()[0] in {"Serves", "the", "single-page", "app", "every"}
                or "browser" in t
            ]
            return sized, len(lines)

        default_sized, default_lines = description_lines(POSITIONS)
        wide_sized, wide_lines = description_lines(
            {**POSITIONS, "web": [40, 300, 320, 180]}
        )
        assert not default_sized
        assert wide_sized
        assert wide_lines < default_lines
