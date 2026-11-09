"""The toolbar's line style, saved per view and drawn by ``c4 render`` (PP-222).

The Studio's Bezier / Straight / Step / Smooth step choice used to live
only in the browser, so ``c4 render`` drew straight lines whatever the
screen showed. It is now a ``lineStyle`` section of the layout sidecar,
and both renderers draw from the same geometry. The rendered checks each
pair a style with one that draws differently, so none of them can pass
by accident.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from c4studio.layout_sidecar import read_line_styles
from c4studio.models import View, Workspace
from c4studio.parser.dsl import parse_dsl
from c4studio.render import RenderError, _payload_with_layout, node_executable
from c4studio.webapp.server import create_app

LONG_LABEL = "Publishes shipment status changes for every downstream consumer"

DSL = f"""
workspace "W" {{
    model {{
        u = person "User"
        s = softwareSystem "S" {{
            web = container "Web"
            api = container "API"
        }}
        u -> web "Uses"
        web -> api "{LONG_LABEL}"
        api -> web "Notifies"
    }}
    views {{
        container s "cont" {{
            include *
        }}
    }}
}}
"""

# Diagonal from one another, so each style draws its own shape.
POSITIONS = {
    "u": [0, 0],
    "s": [400, 300, 900, 800],
    "web": [500, 400],
    "api": [1000, 800],
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
def workspace() -> Workspace:
    return parse_dsl(DSL)


@pytest.fixture()
def source(tmp_path: Path) -> Path:
    path = tmp_path / "ws.dsl"
    path.write_text(DSL, encoding="utf-8")
    return path


def _view(workspace: Workspace) -> View:
    return next(v for v in workspace.views if v.key == "cont")


def _write_sidecar(source: Path, document: dict[str, Any]) -> None:
    source.with_name(f"{source.stem}.layout.json").write_text(
        json.dumps({"version": 1, **document}), encoding="utf-8"
    )


class TestSidecar:
    def test_it_reads_each_views_style(self, source: Path) -> None:
        _write_sidecar(source, {"lineStyle": {"cont": "smoothstep", "x": "straight"}})
        assert read_line_styles(source) == {"cont": "smoothstep", "x": "straight"}

    def test_an_unknown_style_is_dropped(self, source: Path) -> None:
        _write_sidecar(source, {"lineStyle": {"a": "step", "b": "spline", "c": 3}})
        assert read_line_styles(source) == {"a": "step"}

    def test_a_sidecar_without_the_section_still_loads(self, source: Path) -> None:
        _write_sidecar(source, {"views": {"cont": {"u": [1, 2]}}})
        assert read_line_styles(source) == {}

    def test_the_render_payload_carries_it(
        self, workspace: Workspace, source: Path
    ) -> None:
        _write_sidecar(source, {"lineStyle": {"cont": "step"}})
        payload = _payload_with_layout(workspace, _view(workspace), source)
        assert payload["lineStyle"] == "step"

    def test_a_view_without_one_has_none(
        self, workspace: Workspace, source: Path
    ) -> None:
        _write_sidecar(source, {"lineStyle": {"other": "step"}})
        payload = _payload_with_layout(workspace, _view(workspace), source)
        assert "lineStyle" not in payload


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    (tmp_path / DSL_FILE).write_text(DSL, encoding="utf-8")
    return tmp_path


def _client(root: Path, *, read_only: bool = False) -> TestClient:
    client = TestClient(create_app(root=root, read_only=read_only))
    assert client.post("/api/load", json={"path": DSL_FILE}).status_code == 200
    return client


def _sidecar(root: Path) -> dict[str, Any]:
    path = root / "example.layout.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _served(client: TestClient) -> Any:
    return client.get("/api/views/cont/graph").json().get("lineStyle")


class TestServer:
    def test_it_is_saved_served_and_reloaded(self, root: Path) -> None:
        client = _client(root)
        assert _served(client) is None
        response = client.put(
            "/api/views/cont/line-style", json={"style": "smoothstep"}
        )
        assert response.status_code == 200
        assert _sidecar(root)["lineStyle"] == {"cont": "smoothstep"}
        assert _served(client) == "smoothstep"
        assert _served(_client(root)) == "smoothstep"

    def test_an_unknown_style_is_refused(self, root: Path) -> None:
        client = _client(root)
        response = client.put("/api/views/cont/line-style", json={"style": "spline"})
        assert response.status_code == 422
        assert "lineStyle" not in _sidecar(root)

    def test_null_forgets_the_views_choice(self, root: Path) -> None:
        client = _client(root)
        client.put("/api/views/cont/line-style", json={"style": "step"})
        client.put("/api/views/cont/line-style", json={"style": None})
        assert "lineStyle" not in _sidecar(root)
        assert _served(client) is None

    def test_viewer_may_save_it(self, root: Path) -> None:
        """How the diagram is drawn, never the model — like every layout write."""
        client = _client(root, read_only=True)
        response = client.put("/api/views/cont/line-style", json={"style": "step"})
        assert response.status_code == 200
        assert _served(client) == "step"

    def test_other_writes_and_reset_keep_it(self, root: Path) -> None:
        client = _client(root)
        client.put("/api/views/cont/line-style", json={"style": "step"})
        client.post("/api/views/cont/layout", json={"positions": {"u": [1, 2]}})
        client.post("/api/views/cont/expansion", json={"expanded": [], "collapsed": []})
        assert client.delete("/api/views/cont/layout").status_code == 200
        assert _sidecar(root)["lineStyle"] == {"cont": "step"}

    def test_named_layouts_capture_and_restore_it(self, root: Path) -> None:
        client = _client(root)
        client.put("/api/views/cont/line-style", json={"style": "smoothstep"})
        client.post("/api/views/cont/layouts", json={"name": "Smooth"})
        client.put("/api/views/cont/line-style", json={"style": "straight"})
        client.post("/api/views/cont/layouts/apply", json={"name": "Smooth"})
        assert _served(client) == "smoothstep"
        assert _sidecar(root)["lineStyle"] == {"cont": "smoothstep"}


def _paths(svg: str) -> list[str]:
    """Every relationship line's path data."""
    return re.findall(r'<path d="([^"]+)"[^>]*marker-end=', svg)


def _render(workspace: Workspace, source: Path, style: str | None) -> str:
    from c4studio.render import render_view

    document: dict[str, Any] = {"views": {"cont": POSITIONS}}
    if style is not None:
        document["lineStyle"] = {"cont": style}
    _write_sidecar(source, document)
    return render_view(workspace, _view(workspace), layout_source=source)


@needs_node
class TestRendered:
    def test_no_saved_style_draws_bezier_as_the_studio_does(
        self, workspace: Workspace, source: Path
    ) -> None:
        uses = [d for d in _paths(_render(workspace, source, None)) if " C " in d]
        assert len(uses) == 1, "the lone line should be a cubic Bezier"

    def test_straight_draws_one_run(self, workspace: Workspace, source: Path) -> None:
        paths = _paths(_render(workspace, source, "straight"))
        assert not any(" C " in d for d in paths)
        assert any(re.fullmatch(r"M [-\d. ]+ L [-\d. ]+", d) for d in paths)

    @pytest.mark.parametrize("style", ["step", "smoothstep"])
    def test_a_step_style_routes_every_line(
        self, workspace: Workspace, source: Path, style: str
    ) -> None:
        paths = _paths(_render(workspace, source, style))
        assert len(paths) == 3
        # Smooth step rounds its corners with a quadratic; Step does not.
        assert all((" Q " in d) is (style == "smoothstep") for d in paths)
        assert not any(" C " in d for d in paths)
        # Every run horizontal or vertical, and the diagonal pairs need a turn.
        for d in paths:
            points = [
                (float(x), float(y)) for x, y in re.findall(r"([-\d.]+) ([-\d.]+)", d)
            ]
            assert len(points) >= 3
            assert all(
                a[0] == b[0] or a[1] == b[1]
                for a, b in zip(points, points[1:], strict=False)
            )

    def test_lines_between_the_same_pair_bow_apart(
        self, workspace: Workspace, source: Path
    ) -> None:
        """web -> api and api -> web, which used to be drawn on top of each other."""
        bowed = [
            d for d in _paths(_render(workspace, source, "straight")) if " Q " in d
        ]
        assert len(bowed) == 2
        controls = {re.search(r" Q ([-\d.]+ [-\d.]+)", d).group(1) for d in bowed}  # type: ignore[union-attr]
        assert len(controls) == 2

    def test_a_long_label_wraps_rather_than_being_cut(
        self, workspace: Workspace, source: Path
    ) -> None:
        svg = _render(workspace, source, "straight")
        text = " ".join(re.findall(r"<text[^>]*>([^<]*)</text>", svg))
        assert "…" not in text
        for word in LONG_LABEL.split():
            assert word in text
