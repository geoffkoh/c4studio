"""The icon picker's server side (PP-233).

``GET /api/icons`` lists ``icons/`` beside the workspace, ``GET
/api/icons/file`` serves one image for a thumbnail, and ``POST
/api/style`` with ``property: icon`` writes the picked file into a rule,
spelled relative to the file the rule is in.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from c4studio.webapp.server import create_app

SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"><rect width="1" height="1"/></svg>'

DSL = """workspace "W" {
    model {
        s = softwareSystem "S" {
            fn = container "Fn" "" "" "Lambda"
            db = container "DB" "" "" "Database"
        }
    }
    views {
        container s Containers {
            include *
        }
        !include "styles/look.dsl"
    }
}
"""

LOOK = """styles {
    element "Database" {
        background #438dd5
    }
}
"""


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "w.dsl").write_text(DSL, encoding="utf-8")
    (tmp_path / "styles").mkdir()
    (tmp_path / "styles" / "look.dsl").write_text(LOOK, encoding="utf-8")
    aws = tmp_path / "icons" / "aws"
    aws.mkdir(parents=True)
    (aws / "Arch_AWS-Lambda_48.svg").write_text(SVG, encoding="utf-8")
    (aws / "Arch_AWS-Lambda_16.svg").write_text(SVG, encoding="utf-8")
    return tmp_path


@pytest.fixture
def client(root: Path) -> TestClient:
    client = TestClient(create_app(root=root))
    assert client.post("/api/load", json={"path": "w.dsl"}).status_code == 200
    return client


def _apply(client: TestClient, root: Path, body: dict[str, Any]) -> dict[str, Any]:
    response = client.post("/api/style", json=body)
    assert response.status_code == 200, response.text
    plan: dict[str, Any] = response.json()
    for file in plan["files"]:
        (root / file["path"]).write_text(file["content"], encoding="utf-8")
    assert client.post("/api/load", json={"path": "w.dsl"}).status_code == 200
    return plan


def _node(client: TestClient, node_id: str) -> dict[str, Any]:
    graph = client.get("/api/views/Containers/graph").json()
    data: dict[str, Any] = next(n["data"] for n in graph["nodes"] if n["id"] == node_id)
    return data


def test_the_library_lists_one_entry_per_icon(client: TestClient) -> None:
    listing = client.get("/api/icons").json()
    assert listing == {
        "folder": "icons",
        "exists": True,
        "truncated": False,
        "icons": [
            {
                "path": "icons/aws/Arch_AWS-Lambda_48.svg",
                "name": "Lambda",
                "pack": "aws",
                "used": False,
            }
        ],
    }


def test_no_folder_says_so(tmp_path: Path) -> None:
    (tmp_path / "w.dsl").write_text(
        DSL.replace('        !include "styles/look.dsl"\n', "")
    )
    client = TestClient(create_app(root=tmp_path))
    client.post("/api/load", json={"path": "w.dsl"})
    listing = client.get("/api/icons").json()
    assert listing["exists"] is False
    assert listing["icons"] == []


def test_a_thumbnail_is_served_inert(client: TestClient) -> None:
    response = client.get(
        "/api/icons/file", params={"path": "icons/aws/Arch_AWS-Lambda_48.svg"}
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")
    assert response.headers["content-security-policy"].startswith("sandbox")
    assert response.headers["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize(
    ("path", "status"),
    [("../outside.svg", 400), ("w.dsl", 404), ("icons/aws/nope.svg", 404)],
)
def test_only_images_under_the_root_are_served(
    client: TestClient, path: str, status: int
) -> None:
    assert client.get("/api/icons/file", params={"path": path}).status_code == status


def test_a_picked_icon_is_spelled_from_the_rule_s_file(
    client: TestClient, root: Path
) -> None:
    # `Database`'s rule is in styles/look.dsl, so the path climbs out of it.
    _apply(
        client,
        root,
        {
            "kind": "element",
            "property": "icon",
            "value": "icons/aws/Arch_AWS-Lambda_48.svg",
            "tag": "Database",
        },
    )
    look = (root / "styles" / "look.dsl").read_text(encoding="utf-8")
    assert 'icon "../icons/aws/Arch_AWS-Lambda_48.svg"' in look
    data = _node(client, "db")
    assert data["icon"].startswith("data:image/svg+xml;base64,")
    assert data["iconSource"] == "../icons/aws/Arch_AWS-Lambda_48.svg"
    assert client.get("/api/icons").json()["icons"][0]["used"] is True


def test_a_url_is_written_as_it_is(client: TestClient, root: Path) -> None:
    _apply(
        client,
        root,
        {
            "kind": "element",
            "property": "icon",
            "value": "https://example.com/l.png",
            "tag": "Database",
        },
    )
    look = (root / "styles" / "look.dsl").read_text(encoding="utf-8")
    assert 'icon "https://example.com/l.png"' in look


def test_only_this_element_gets_the_icon(client: TestClient, root: Path) -> None:
    _apply(
        client,
        root,
        {
            "kind": "element",
            "property": "icon",
            "value": "icons/aws/Arch_AWS-Lambda_48.svg",
            "element": "fn",
        },
    )
    assert _node(client, "fn")["icon"].startswith("data:")
    assert "icon" not in _node(client, "db")


@pytest.mark.parametrize("value", ["../outside.svg", "icons/aws/nope.svg", "w.dsl"])
def test_a_path_that_is_not_an_image_here_is_refused(
    client: TestClient, value: str
) -> None:
    response = client.post(
        "/api/style",
        json={"kind": "element", "property": "icon", "value": value, "tag": "Database"},
    )
    assert response.status_code == 422


def test_viewer_lists_but_does_not_write(root: Path) -> None:
    viewer = TestClient(create_app(root=root, read_only=True))
    viewer.post("/api/load", json={"path": "w.dsl"})
    assert viewer.get("/api/icons").status_code == 200
    response = viewer.post(
        "/api/style",
        json={
            "kind": "element",
            "property": "icon",
            "value": "icons/aws/Arch_AWS-Lambda_48.svg",
            "tag": "Database",
        },
    )
    assert response.status_code == 403
