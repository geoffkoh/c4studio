"""The bundled icon pack (PP-239).

``GET /api/icons/bundled`` lists what c4studio ships, ``GET
/api/icons/bundled/<pack>/<name>.svg`` serves one icon, and ``POST
/api/icons/bundled/copy`` copies one into the workspace's
``icons/<pack>/`` with the pack's licence, so the style the picker writes
next names a file in the workspace, never one in the installed package.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from c4studio import bundled_icons
from c4studio.parser.dsl import parse_dsl_file
from c4studio.webapp.server import create_app

DSL = """workspace "W" {
    model {
        s = softwareSystem "S" {
            tags "Store"
        }
    }
    views {
        systemLandscape L {
            include *
        }
        styles {
            element "Store" {
                background #1168bd
                color #ffffff
            }
        }
    }
}
"""


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "w.dsl").write_text(DSL, encoding="utf-8")
    return tmp_path


def _client(root: Path, *, read_only: bool = False) -> TestClient:
    client = TestClient(create_app(root=root, read_only=read_only))
    assert client.post("/api/load", json={"path": "w.dsl"}).status_code == 200
    return client


class TestPack:
    def test_the_tabler_pack_is_shipped_with_its_licence(self) -> None:
        pack = bundled_icons.load("tabler")
        assert len(pack.icons) > 4000
        assert pack.licence.startswith("MIT License")
        assert "Paweł Kuna" in pack.licence

    def test_no_brand_logos(self) -> None:
        # Other companies' marks come only from a curated subset (PP-240).
        assert not any(
            name.startswith("brand-") for name in bundled_icons.load("tabler").icons
        )

    def test_every_icon_is_plain_shapes_in_current_color(self) -> None:
        # What the Studio serves and copies must not be able to carry
        # script; vendor_tabler.py checks this, and so does this.
        shape = re.compile(
            r"<(?:path|circle|rect|line|polyline|polygon|ellipse)"
            r"(?: (?:d|cx|cy|r|rx|ry|x|y|x1|y1|x2|y2|width|height|points|fill|stroke"
            r'|stroke-width)="[^"<>]*")* ?/>'
        )
        for name, (_, _, shapes) in bundled_icons.load("tabler").icons.items():
            assert shape.sub("", shapes) == "", name
            assert "url(" not in shapes, name

    def test_an_icon_is_a_whole_svg(self) -> None:
        svg = bundled_icons.svg("tabler", "database")
        assert svg.startswith('<svg xmlns="http://www.w3.org/2000/svg"')
        assert 'stroke="currentColor"' in svg
        assert svg.rstrip().endswith("</svg>")

    @pytest.mark.parametrize(
        ("pack", "name"),
        [("tabler", "no-such-icon"), ("tabler", "../LICENSE"), ("other", "database")],
    )
    def test_unknown_icons_are_refused(self, pack: str, name: str) -> None:
        with pytest.raises(bundled_icons.BundledIconError):
            bundled_icons.svg(pack, name)


class TestRoutes:
    def test_listing_needs_no_workspace(self, tmp_path: Path) -> None:
        body = TestClient(create_app(root=tmp_path)).get("/api/icons/bundled").json()
        (pack,) = body["packs"]
        assert pack["name"] == "tabler"
        assert pack["folder"] == "icons/tabler"
        database = next(i for i in pack["icons"] if i["name"] == "database")
        assert database["category"] == "Database"
        assert "storage" in database["tags"].split()

    def test_an_icon_is_served_sandboxed(self, tmp_path: Path) -> None:
        response = TestClient(create_app(root=tmp_path)).get(
            "/api/icons/bundled/tabler/database.svg"
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/svg+xml"
        assert "sandbox" in response.headers["content-security-policy"]
        assert response.text == bundled_icons.svg("tabler", "database")

    def test_an_unknown_icon_is_404(self, tmp_path: Path) -> None:
        client = TestClient(create_app(root=tmp_path))
        assert client.get("/api/icons/bundled/tabler/nope.svg").status_code == 404
        assert client.get("/api/icons/bundled/other/database.svg").status_code == 404


def _copy(client: TestClient, name: str = "database") -> dict[str, object]:
    response = client.post(
        "/api/icons/bundled/copy", json={"pack": "tabler", "name": name}
    )
    assert response.status_code == 200, response.text
    body: dict[str, object] = response.json()
    return body


class TestCopy:
    def test_the_icon_and_the_licence_are_copied(self, root: Path) -> None:
        assert _copy(_client(root)) == {
            "path": "icons/tabler/database.svg",
            "written": True,
        }
        copied = root / "icons" / "tabler"
        assert (copied / "database.svg").read_text(
            encoding="utf-8"
        ) == bundled_icons.svg("tabler", "database")
        assert (
            (copied / "LICENSE").read_text(encoding="utf-8").startswith("MIT License")
        )

    def test_beside_the_workspace_file_not_the_root(self, root: Path) -> None:
        (root / "arch").mkdir()
        (root / "arch" / "w.dsl").write_text(DSL, encoding="utf-8")
        client = TestClient(create_app(root=root))
        assert client.post("/api/load", json={"path": "arch/w.dsl"}).status_code == 200
        assert _copy(client)["path"] == "arch/icons/tabler/database.svg"

    def test_a_file_already_there_is_kept(self, root: Path) -> None:
        mine = root / "icons" / "tabler" / "database.svg"
        mine.parent.mkdir(parents=True)
        mine.write_text("<svg/>", encoding="utf-8")
        (mine.parent / "LICENSE").write_text("kept", encoding="utf-8")
        assert _copy(_client(root)) == {
            "path": "icons/tabler/database.svg",
            "written": False,
        }
        assert mine.read_text(encoding="utf-8") == "<svg/>"
        assert (mine.parent / "LICENSE").read_text(encoding="utf-8") == "kept"

    def test_an_unknown_icon_is_refused(self, root: Path) -> None:
        response = _client(root).post(
            "/api/icons/bundled/copy", json={"pack": "tabler", "name": "../../w"}
        )
        assert response.status_code == 422
        assert not (root / "icons").exists()

    def test_viewer_refuses(self, root: Path) -> None:
        response = _client(root, read_only=True).post(
            "/api/icons/bundled/copy", json={"pack": "tabler", "name": "database"}
        )
        assert response.status_code == 403
        assert not (root / "icons").exists()

    def test_the_copy_is_set_through_the_style_route(self, root: Path) -> None:
        client = _client(root)
        path = _copy(client)["path"]
        plan = client.post(
            "/api/style",
            json={"kind": "element", "property": "icon", "value": path, "tag": "Store"},
        ).json()
        (written,) = plan["files"]
        assert 'icon "icons/tabler/database.svg"' in written["content"]


class TestTint:
    """An icon drawn in ``currentColor`` is painted in the text colour."""

    def _node(self, root: Path, styles: str) -> dict[str, object]:
        _copy(_client(root))
        text = DSL.replace("color #ffffff", f"color #ffffff\n{styles}")
        (root / "w.dsl").write_text(text, encoding="utf-8")
        client = _client(root)
        graph = client.get("/api/views/L/graph").json()
        (node,) = [n for n in graph["nodes"] if n["id"] == "s"]
        data: dict[str, object] = node["data"]
        return data

    def test_without_being_asked(self, root: Path) -> None:
        data = self._node(root, '                icon "icons/tabler/database.svg"')
        assert data["iconTint"] == "#ffffff"

    def test_false_still_turns_it_off(self, root: Path) -> None:
        data = self._node(
            root,
            '                icon "icons/tabler/database.svg"\n'
            "                properties {\n"
            '                    "c4studio.iconTint" "false"\n'
            "                }",
        )
        assert "iconTint" not in data

    def test_a_coloured_icon_is_drawn_as_it_is(self, root: Path) -> None:
        (root / "icons").mkdir()
        (root / "icons" / "tile.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1">'
            '<rect width="1" height="1" fill="#ff9900" stroke="currentColor"/></svg>',
            encoding="utf-8",
        )
        data = self._node(root, '                icon "icons/tile.svg"')
        assert "iconTint" not in data


def test_the_pack_json_is_one_icon_per_line() -> None:
    # A version bump stays reviewable: vendor_tabler.py writes it this way.
    path = Path(bundled_icons.__file__).parent / "icon_packs" / "tabler" / "icons.json"
    lines = path.read_text(encoding="utf-8").splitlines()
    data = json.loads("\n".join(lines))
    assert len(lines) > len(data["icons"])
    assert set(data) == {"version", "icons"}
    # Provenance lives in the README; the shipped data names no URL.
    assert "://" not in path.read_text(encoding="utf-8")
    readme = (path.parent / "README.md").read_text(encoding="utf-8")
    assert data["version"] in readme
    assert re.search(r"sha1 \| `[0-9a-f]{40}`", readme)


def test_the_copied_icon_parses_as_an_embedded_image(root: Path) -> None:
    _copy(_client(root))
    text = DSL.replace(
        "color #ffffff", 'color #ffffff\n icon "icons/tabler/database.svg"'
    )
    (root / "w.dsl").write_text(text, encoding="utf-8")
    workspace = parse_dsl_file(root / "w.dsl")
    (style,) = [
        s for s in workspace.views.configuration.styles.element_styles if s.icon
    ]
    assert style.icon.startswith("data:image/svg+xml")
