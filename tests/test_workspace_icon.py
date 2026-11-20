"""The workspace logo: the ``Workspace:Icon`` style's icon (PP-237).

structurizr-application 2026.02.01 took the logo out of ``branding`` and
into an element style no element carries. It is drawn beside the
diagram's title on every surface, which needs its proportions, read here
from the image itself because the headless renderer has no DOM.
"""

from __future__ import annotations

import base64
import struct
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from c4studio.graph.view_graph import workspace_icon
from c4studio.icons import data_uri, image_size, inline_icons
from c4studio.lint import lint
from c4studio.parser.dsl import parse_dsl, parse_dsl_file
from c4studio.publish import _logo
from c4studio.webapp.server import create_app

WIDE_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 40">'
    '<rect width="120" height="40" fill="#0b6e4f"/></svg>'
)


def _b64(media_type: str, data: bytes) -> str:
    return f"data:{media_type};base64,{base64.b64encode(data).decode('ascii')}"


def _png(width: int, height: int) -> bytes:
    # Signature and IHDR are all `image_size` reads.
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">I4sII", 13, b"IHDR", width, height)


class TestImageSize:
    @pytest.mark.parametrize(
        ("uri", "size"),
        [
            (_b64("image/svg+xml", WIDE_SVG.encode()), (120.0, 40.0)),
            (
                "data:image/svg+xml," + quote('<svg width="30px" height="10"></svg>'),
                (30.0, 10.0),
            ),
            (_b64("image/png", _png(200, 50)), (200.0, 50.0)),
            (_b64("image/gif", b"GIF89a" + struct.pack("<HH", 64, 32)), (64.0, 32.0)),
            (
                _b64(
                    "image/jpeg",
                    b"\xff\xd8\xff\xe0"
                    + struct.pack(">H", 4)
                    + b"JF"
                    + b"\xff\xc0"
                    + struct.pack(">HBHH", 11, 8, 90, 300),
                ),
                (300.0, 90.0),
            ),
        ],
        ids=["svg-viewbox", "svg-width-height", "png", "gif", "jpeg"],
    )
    def test_reads_the_header(self, uri: str, size: tuple[float, float]) -> None:
        assert image_size(uri) == size

    @pytest.mark.parametrize(
        "uri",
        [
            "https://example.com/logo.png",
            _b64("image/webp", b"RIFF\x00\x00\x00\x00WEBP"),
            "data:image/svg+xml," + quote('<svg width="100%" height="2em"></svg>'),
        ],
        ids=["url", "webp", "relative-svg"],
    )
    def test_what_it_cannot_read_is_none(self, uri: str) -> None:
        assert image_size(uri) is None


def _workspace(styles: str) -> str:
    return (
        'workspace "Acme" {\n'
        "    model {\n"
        '        s = softwareSystem "S"\n'
        "    }\n"
        "    views {\n"
        "        systemContext s Context {\n"
        "            include *\n"
        "        }\n"
        "        styles {\n"
        f"{styles}\n"
        "        }\n"
        "    }\n"
        "}\n"
    )


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "brand").mkdir()
    (tmp_path / "brand" / "logo.svg").write_text(WIDE_SVG, encoding="utf-8")
    (tmp_path / "w.dsl").write_text(
        _workspace(
            '            element "Workspace:Icon" {\n'
            '                icon "brand/logo.svg"\n'
            "                dark {\n"
            '                    icon "data:image/png;base64,AAAA"\n'
            "                }\n"
            "            }"
        ),
        encoding="utf-8",
    )
    return tmp_path


class TestResolution:
    def test_the_style_s_icon_is_the_logo(self, root: Path) -> None:
        # The dark variant is skipped, as the viewer paints one scheme.
        icon = workspace_icon(parse_dsl_file(root / "w.dsl"))
        assert icon == _b64("image/svg+xml", WIDE_SVG.encode())

    def test_the_last_rule_wins(self) -> None:
        workspace = parse_dsl(
            _workspace(
                '            element "Workspace:Icon" {\n'
                '                icon "https://example.com/a.png"\n'
                "            }\n"
                '            element "Workspace:Icon" {\n'
                '                icon "https://example.com/b.png"\n'
                "            }"
            )
        )
        assert workspace_icon(workspace) == "https://example.com/b.png"

    def test_no_style_no_logo(self) -> None:
        assert workspace_icon(parse_dsl(_workspace(""))) == ""

    def test_lint_does_not_call_it_unused(self, root: Path) -> None:
        # No element carries the tag; the style exists for its icon.
        findings = lint(parse_dsl_file(root / "w.dsl"))
        assert not [f for f in findings if f.code == "unused-style"]


class TestSurfaces:
    @pytest.fixture
    def client(self, root: Path) -> TestClient:
        client = TestClient(create_app(root=root))
        assert client.post("/api/load", json={"path": "w.dsl"}).status_code == 200
        return client

    def test_the_diagram_payload_carries_it_with_its_proportions(
        self, client: TestClient
    ) -> None:
        graph = client.get("/api/views/Context/graph").json()
        assert graph["workspaceIcon"] == {
            "src": _b64("image/svg+xml", WIDE_SVG.encode()),
            "aspect": 3.0,
        }

    def test_the_top_bar_reads_it_from_the_workspace(self, client: TestClient) -> None:
        workspace = client.get("/api/workspace").json()
        assert workspace["icon"].startswith("data:image/svg+xml;base64,")

    def test_no_logo_no_key(self, tmp_path: Path) -> None:
        (tmp_path / "w.dsl").write_text(_workspace(""), encoding="utf-8")
        client = TestClient(create_app(root=tmp_path))
        client.post("/api/load", json={"path": "w.dsl"})
        assert "workspaceIcon" not in client.get("/api/views/Context/graph").json()
        assert client.get("/api/workspace").json()["icon"] is None

    def test_the_published_site_shows_it(self, root: Path) -> None:
        html = _logo(parse_dsl_file(root / "w.dsl"))
        assert html.startswith('<img class="logo" src="data:image/svg+xml;base64,')


class TestRender:
    @pytest.fixture(autouse=True)
    def _clear_cache(self) -> None:
        data_uri.cache_clear()

    def test_a_url_logo_is_embedded_and_measured(self, tmp_path: Path) -> None:
        (tmp_path / "logo.svg").write_text(WIDE_SVG, encoding="utf-8")
        payload: dict[str, Any] = {
            "nodes": [],
            "edges": [],
            "workspaceIcon": {"src": (tmp_path / "logo.svg").as_uri()},
        }
        inline_icons(payload)
        assert payload["workspaceIcon"]["src"].startswith("data:image/svg+xml")
        assert payload["workspaceIcon"]["aspect"] == 3.0

    def test_an_unreachable_logo_is_left_out(self, tmp_path: Path) -> None:
        payload: dict[str, Any] = {
            "nodes": [],
            "edges": [],
            "workspaceIcon": {"src": (tmp_path / "missing.svg").as_uri()},
        }
        inline_icons(payload)
        assert "workspaceIcon" not in payload
