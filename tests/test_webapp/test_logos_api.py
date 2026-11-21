"""The logo picker's server side (PP-238).

``GET /api/logos`` lists the images under the workspace's folder, likely
logos first, with the logo now set; ``POST /api/logos/copy`` copies a file
picked from the machine into ``brand/``, or finds it already there. The
logo itself is written by ``POST /api/style`` with ``tag:
"Workspace:Icon"``, which the icon picker's tests already cover; the last
test here pins that it works for a tag no element carries.
"""

from __future__ import annotations

import base64
import subprocess
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from c4studio.icons import MAX_ICON_BYTES
from c4studio.webapp.server import create_app

SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 4 1"><rect width="4" height="1"/></svg>'
OTHER = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"/>'

DSL = """workspace "W" {
    model {
        s = softwareSystem "S"
    }
    views {
        systemLandscape L {
            include *
        }
STYLES
    }
}
"""


def _write(root: Path, styles: str = "") -> None:
    (root / "w.dsl").write_text(DSL.replace("STYLES", styles), encoding="utf-8")


def _client(root: Path, *, read_only: bool = False) -> TestClient:
    client = TestClient(create_app(root=root, read_only=read_only))
    assert client.post("/api/load", json={"path": "w.dsl"}).status_code == 200
    return client


def _logos(root: Path) -> dict[str, Any]:
    response = _client(root).get("/api/logos")
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    return body


@pytest.fixture
def root(tmp_path: Path) -> Path:
    _write(tmp_path)
    (tmp_path / "brand").mkdir()
    (tmp_path / "brand" / "acme.svg").write_text(SVG, encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "acme-logo.png").write_bytes(b"\x89PNG")
    (tmp_path / "docs" / "diagram.png").write_bytes(b"\x89PNG")
    (tmp_path / "docs" / "benchmark.png").write_bytes(b"\x89PNG")
    return tmp_path


class TestListing:
    def test_likely_logos_come_first(self, root: Path) -> None:
        images = _logos(root)["images"]
        assert [(i["path"], i["suggested"]) for i in images] == [
            ("brand/acme.svg", True),
            ("docs/acme-logo.png", True),
            # `mark` only as a word: a benchmark chart is not a logo.
            ("docs/benchmark.png", False),
            ("docs/diagram.png", False),
        ]

    def test_build_and_hidden_folders_are_skipped(self, root: Path) -> None:
        for folder in ("node_modules/pkg", "dist", ".cache"):
            (root / folder).mkdir(parents=True)
            (root / folder / "logo.svg").write_text(SVG, encoding="utf-8")
        paths = [i["path"] for i in _logos(root)["images"]]
        assert not any("logo.svg" in path for path in paths)

    def test_gitignored_files_are_skipped(self, root: Path) -> None:
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        (root / ".gitignore").write_text("docs/diagram.png\n", encoding="utf-8")
        paths = [i["path"] for i in _logos(root)["images"]]
        assert "docs/diagram.png" not in paths
        assert "docs/acme-logo.png" in paths

    def test_a_file_too_large_to_embed_is_listed_with_its_size(
        self, root: Path
    ) -> None:
        (root / "brand" / "poster.png").write_bytes(b"\0" * (MAX_ICON_BYTES + 1))
        body = _logos(root)
        poster = next(i for i in body["images"] if i["path"] == "brand/poster.png")
        assert poster["size"] > body["maxBytes"]

    def test_no_logo_set(self, root: Path) -> None:
        body = _logos(root)
        assert body["current"] is None
        assert body["fromTheme"] is False
        assert body["branding"] is None

    def test_the_current_logo_is_a_root_relative_path(self, root: Path) -> None:
        _write(
            root,
            '        styles {\n            element "Workspace:Icon" {\n'
            '                icon "brand/acme.svg"\n            }\n        }',
        )
        assert _logos(root)["current"] == "brand/acme.svg"

    def test_a_logo_from_a_fragment_resolves_against_it(self, root: Path) -> None:
        (root / "styles").mkdir()
        (root / "styles" / "look.dsl").write_text(
            'styles {\n    element "Workspace:Icon" {\n'
            '        icon "../brand/acme.svg"\n    }\n}\n',
            encoding="utf-8",
        )
        _write(root, '        !include "styles/look.dsl"')
        assert _logos(root)["current"] == "brand/acme.svg"

    def test_a_branding_logo_is_offered_while_nothing_is_drawn(
        self, root: Path
    ) -> None:
        _write(root, '        branding {\n            logo "brand/acme.svg"\n        }')
        assert _logos(root)["branding"] == "brand/acme.svg"

    def test_a_branding_logo_is_not_offered_beside_a_drawn_one(
        self, root: Path
    ) -> None:
        _write(
            root,
            '        branding {\n            logo "docs/acme-logo.png"\n        }\n'
            '        styles {\n            element "Workspace:Icon" {\n'
            '                icon "brand/acme.svg"\n            }\n        }',
        )
        assert _logos(root)["branding"] is None


def _copy(client: TestClient, name: str, content: bytes, **extra: Any) -> Any:
    return client.post(
        "/api/logos/copy",
        json={"name": name, "content": base64.b64encode(content).decode(), **extra},
    )


class TestCopy:
    def test_a_new_file_goes_to_brand(self, root: Path) -> None:
        response = _copy(_client(root), "/Users/me/Downloads/new.svg", OTHER.encode())
        assert response.json() == {
            "path": "brand/new.svg",
            "existing": False,
            "written": True,
        }
        assert (root / "brand" / "new.svg").read_text(encoding="utf-8") == OTHER

    def test_a_dry_run_writes_nothing(self, root: Path) -> None:
        response = _copy(_client(root), "new.svg", OTHER.encode(), dry_run=True)
        assert response.json()["path"] == "brand/new.svg"
        assert response.json()["written"] is False
        assert not (root / "brand" / "new.svg").exists()

    def test_the_same_content_is_found_where_it_is(self, root: Path) -> None:
        response = _copy(_client(root), "renamed.svg", SVG.encode())
        assert response.json() == {
            "path": "brand/acme.svg",
            "existing": True,
            "written": False,
        }
        assert not (root / "brand" / "renamed.svg").exists()

    def test_a_taken_name_is_numbered(self, root: Path) -> None:
        response = _copy(_client(root), "acme.svg", OTHER.encode())
        assert response.json()["path"] == "brand/acme-2.svg"
        assert (root / "brand" / "acme.svg").read_text(encoding="utf-8") == SVG

    @pytest.mark.parametrize("name", ["notes.txt", ".hidden.svg", "script.html"])
    def test_only_an_image_name(self, root: Path, name: str) -> None:
        assert _copy(_client(root), name, OTHER.encode()).status_code == 422

    def test_too_large_is_refused(self, root: Path) -> None:
        big = b"\0" * (MAX_ICON_BYTES + 1)
        response = _copy(_client(root), "big.png", big)
        assert response.status_code == 422
        assert not (root / "brand" / "big.png").exists()

    def test_viewer_refuses(self, root: Path) -> None:
        viewer = _client(root, read_only=True)
        assert _copy(viewer, "new.svg", OTHER.encode()).status_code == 403
        assert not (root / "brand" / "new.svg").exists()


def test_the_aspect_is_read_from_the_file(root: Path) -> None:
    # A viewBox alone, which the browser cannot measure.
    client = _client(root)
    response = client.get("/api/logos/aspect", params={"path": "brand/acme.svg"})
    assert response.json() == {"aspect": 4.0}
    escape = client.get("/api/logos/aspect", params={"path": "../x.svg"})
    assert escape.status_code == 400


def test_the_logo_is_set_through_the_style_route(root: Path) -> None:
    client = _client(root)
    plan = client.post(
        "/api/style",
        json={
            "kind": "element",
            "property": "icon",
            "value": "brand/acme.svg",
            "tag": "Workspace:Icon",
        },
    ).json()
    (written,) = plan["files"]
    assert 'element "Workspace:Icon" {' in written["content"]
    assert 'icon "brand/acme.svg"' in written["content"]
