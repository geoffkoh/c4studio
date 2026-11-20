"""Opt-in icon tinting: ``c4studio.iconTint`` (PP-234).

A one-colour glyph is drawn black whatever the box, which is unreadable
on a dark one. The property paints the icon in one colour, keeping its
shape: ``true`` means the element's text colour, a hex colour that
colour. It is opt-in because a cloud vendor's multi-colour icon would
flatten to a silhouette. The browser's mask is ``e2e/icon-tint.spec.ts``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from c4studio.lint import lint
from c4studio.parser.dsl import parse_dsl
from c4studio.webapp.server import create_app

ICON = "data:image/svg+xml;base64,PHN2Zy8+"

DSL = """
workspace "W" {
    model {
        s = softwareSystem "S" {
            db = container "DB" {
                tags "Database"
            }
        }
    }
    views {
        container s cont {
            include *
        }
        styles {
STYLES
        }
    }
}
"""


def _node(tmp_path: Path, styles: str) -> dict[str, Any]:
    (tmp_path / "w.dsl").write_text(DSL.replace("STYLES", styles), encoding="utf-8")
    client = TestClient(create_app(root=tmp_path))
    assert client.post("/api/load", json={"path": "w.dsl"}).status_code == 200
    graph = client.get("/api/views/cont/graph").json()
    node: dict[str, Any] = next(n["data"] for n in graph["nodes"] if n["id"] == "db")
    return node


def _tint(value: str, extra: str = "") -> str:
    return (
        'element "Database" {\n'
        f'    icon "{ICON}"\n'
        f"    {extra}\n"
        f'    properties {{ "c4studio.iconTint" "{value}" }}\n'
        "}"
    )


class TestPayload:
    def test_true_is_the_element_s_text_colour(self, tmp_path: Path) -> None:
        node = _node(tmp_path, _tint("true", "color #112233"))
        assert node["iconTint"] == "#112233"

    def test_true_without_a_text_colour_is_white(self, tmp_path: Path) -> None:
        # Both renderers draw text white when no style sets a colour.
        assert _node(tmp_path, _tint("true"))["iconTint"] == "#ffffff"

    def test_a_colour_set_by_a_later_rule_counts(self, tmp_path: Path) -> None:
        # `true` reads the final text colour, not the one when it was set.
        node = _node(
            tmp_path, _tint("true") + '\nelement "Container" { color #ff0000 }'
        )
        assert node["iconTint"] == "#ff0000"

    def test_a_hex_colour_is_that_colour(self, tmp_path: Path) -> None:
        assert _node(tmp_path, _tint("#336791"))["iconTint"] == "#336791"

    def test_false_turns_a_broader_rule_off(self, tmp_path: Path) -> None:
        node = _node(
            tmp_path,
            'element "Element" { properties { "c4studio.iconTint" "true" } }\n'
            + _tint("false"),
        )
        assert "iconTint" not in node

    def test_no_icon_no_tint(self, tmp_path: Path) -> None:
        node = _node(
            tmp_path,
            'element "Database" { properties { "c4studio.iconTint" "true" } }',
        )
        assert "iconTint" not in node

    def test_without_the_property_nothing_is_tinted(self, tmp_path: Path) -> None:
        node = _node(tmp_path, f'element "Database" {{ icon "{ICON}" }}')
        assert node["icon"] == ICON
        assert "iconTint" not in node

    def test_an_invalid_value_paints_nothing(self, tmp_path: Path) -> None:
        assert "iconTint" not in _node(tmp_path, _tint("yes"))


class TestLint:
    @pytest.mark.parametrize(
        ("value", "flagged"),
        [
            ("true", False),
            ("FALSE", False),
            ("#abc", False),
            ("yes", True),
            ("red", True),
        ],
    )
    def test_invalid_values_are_reported(self, value: str, flagged: bool) -> None:
        workspace = parse_dsl(DSL.replace("STYLES", _tint(value)))
        codes = {finding.code for finding in lint(workspace)}
        assert ("invalid-icon-tint" in codes) is flagged


def test_the_logistics_sample_tints_its_queue_glyph() -> None:
    samples = Path(__file__).parent.parent / "samples"
    client = TestClient(create_app(root=samples))
    client.post("/api/load", json={"path": "logistics_network.dsl"})
    graph = client.get("/api/views/PlatformContainers/graph").json()
    bus = next(
        n["data"] for n in graph["nodes"] if n["data"].get("label") == "Event Bus"
    )
    assert bus["icon"].startswith("data:image/svg+xml")
    assert bus["iconTint"] == "#ffffff"
