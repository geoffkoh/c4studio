"""Tests for remote theme loading and its style resolution."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from c4studio.models import Shape, ViewType
from c4studio.parser.dsl import parse_dsl
from c4studio.themes import ThemeLoadError, parse_theme, theme_styles
from c4studio.graph.view_graph import build_view_graph
from typing import Any
from c4studio.models import Workspace

AWS_LIKE_THEME = {
    "name": "Cloud Icons",
    "elements": [
        {
            "tag": "Cloud - Lambda",
            "stroke": "#d86613",
            "color": "#d86613",
            "icon": "lambda.png",
        },
        {
            "tag": "Cloud - RDS",
            "shape": "Cylinder",
            "background": "#527fff",
            "icon": "https://cdn.example.com/rds.png",
        },
    ],
    "relationships": [{"tag": "Async", "dashed": True, "color": "#888888"}],
}


def _theme_file(
    tmp_path: Path, payload: dict[str, Any], name: str = "theme.json"
) -> str:
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path.as_uri()


class TestParseTheme:
    def test_maps_element_and_relationship_styles(self) -> None:
        styles = parse_theme(
            json.dumps(AWS_LIKE_THEME),
            base_url="https://themes.example.com/aws/theme.json",
        )
        by_tag = {s.tag: s for s in styles.element_styles}
        assert by_tag["Cloud - RDS"].shape == Shape.CYLINDER
        assert by_tag["Cloud - RDS"].background == "#527fff"
        assert styles.relationship_styles[0].dashed is True

    def test_relative_icons_resolve_against_the_theme_url(self) -> None:
        styles = parse_theme(
            json.dumps(AWS_LIKE_THEME),
            base_url="https://themes.example.com/aws/theme.json",
        )
        by_tag = {s.tag: s for s in styles.element_styles}
        assert (
            by_tag["Cloud - Lambda"].icon == "https://themes.example.com/aws/lambda.png"
        )
        # Absolute icon URLs are left alone.
        assert by_tag["Cloud - RDS"].icon == "https://cdn.example.com/rds.png"

    def test_invalid_json_raises_theme_load_error(self) -> None:
        with pytest.raises(ThemeLoadError):
            parse_theme("not json{")
        with pytest.raises(ThemeLoadError):
            parse_theme('["a list, not a theme"]')


class TestThemeStyles:
    def test_fetches_all_referenced_themes(self, tmp_path: Path) -> None:
        url = _theme_file(tmp_path, AWS_LIKE_THEME, "fetch_all.json")
        workspace = parse_dsl(
            f"""
            workspace "W" {{
                model {{ s = softwareSystem "S" }}
                views {{ theme "{url}" }}
            }}
            """
        )
        styles = theme_styles(workspace)
        assert {s.tag for s in styles.element_styles} == {
            "Cloud - Lambda",
            "Cloud - RDS",
        }

    def test_unreachable_theme_is_skipped(self, tmp_path: Path) -> None:
        workspace = parse_dsl(
            f"""
            workspace "W" {{
                model {{ s = softwareSystem "S" }}
                views {{ theme "{(tmp_path / "missing.json").as_uri()}" }}
            }}
            """
        )
        assert theme_styles(workspace).element_styles == []


class TestDslThemeCapture:
    def test_theme_and_themes_urls_are_recorded(self) -> None:
        workspace = parse_dsl(
            """
            workspace "W" {
                model { s = softwareSystem "S" }
                views {
                    theme "https://example.com/one/theme.json"
                    themes "https://example.com/two.json" "https://example.com/three.json"
                }
            }
            """
        )
        assert workspace.views.configuration.themes == [
            "https://example.com/one/theme.json",
            "https://example.com/two.json",
            "https://example.com/three.json",
        ]


class TestThemeInViewGraph:
    def _workspace(
        self, tmp_path: Path, theme_name: str, extra_styles: str = ""
    ) -> Workspace:
        url = _theme_file(tmp_path, AWS_LIKE_THEME, theme_name)
        return parse_dsl(
            f"""
            workspace "W" {{
                model {{
                    s = softwareSystem "Functions" "Serverless compute" "Cloud - Lambda"
                }}
                views {{
                    systemLandscape Landscape {{ include * }}
                    theme "{url}"
                    {extra_styles}
                }}
            }}
            """
        )

    def test_theme_icon_and_colour_reach_node_data(self, tmp_path: Path) -> None:
        workspace = self._workspace(tmp_path, "graph_theme.json")
        view = next(v for v in workspace.views if v.type == ViewType.SYSTEM_LANDSCAPE)
        data = build_view_graph(workspace, view)
        node = next(n for n in data["nodes"] if n["id"] == "s")
        assert node["data"]["icon"].endswith("/lambda.png")
        assert node["data"]["textColor"] == "#d86613"

    def test_workspace_styles_override_theme_styles(self, tmp_path: Path) -> None:
        workspace = self._workspace(
            tmp_path,
            "graph_override.json",
            extra_styles="""
                    styles {
                        element "Cloud - Lambda" {
                            color #123456
                        }
                    }
            """,
        )
        view = next(v for v in workspace.views if v.type == ViewType.SYSTEM_LANDSCAPE)
        data = build_view_graph(workspace, view)
        node = next(n for n in data["nodes"] if n["id"] == "s")
        assert node["data"]["textColor"] == "#123456"
        # Theme properties the workspace does not override still apply.
        assert node["data"]["icon"].endswith("/lambda.png")
