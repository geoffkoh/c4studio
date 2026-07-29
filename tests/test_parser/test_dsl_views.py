"""Tests for custom/image views, default, properties, animation, autoLayout (Phase 4)."""

from pystructurizr.generators.json_export import workspace_to_json
from pystructurizr.models import ViewType
from pystructurizr.parser.dsl import parse_dsl


BASE_MODEL = """
        model {
            u = person "User"
            s = softwareSystem "S" {
                web = container "Web"
            }
            box = element "Box"
            u -> s "Uses"
        }
"""


def _workspace(views: str) -> str:
    return f'workspace "W" {{ {BASE_MODEL} views {{ {views} }} }}'


def test_custom_view_parsed() -> None:
    ws = parse_dsl(
        _workspace(
            """
            custom "customKey" "My Title" "My description" {
                include *
                autoLayout lr
            }
            """
        )
    )
    assert len(ws.views.custom_views) == 1
    view = ws.views.custom_views[0]
    assert view.type == ViewType.CUSTOM
    assert view.key == "customKey"
    assert view.title == "My Title"
    assert view.description == "My description"
    assert view.include_all is True


def test_image_view_sources() -> None:
    ws = parse_dsl(
        _workspace(
            """
            image s "img1" {
                plantuml "https://example.com/x.puml"
            }
            image * "img2" {
                kroki graphviz "https://example.com/x.dot"
                title "Kroki view"
            }
            image s "img3" {
                mermaid "https://example.com/x.mmd"
            }
            image s "img4" {
                image "https://example.com/x.png"
            }
            """
        )
    )
    views = {v.key: v for v in ws.views.image_views}
    assert views["img1"].element_id == "s"
    assert views["img1"].content == "https://example.com/x.puml"
    assert views["img1"].content_type == "plantuml"
    assert views["img2"].element_id == ""
    assert views["img2"].content == "https://example.com/x.dot"
    assert views["img2"].content_type == "kroki/graphviz"
    assert views["img2"].title == "Kroki view"
    assert views["img3"].content_type == "mermaid"
    assert views["img4"].content == "https://example.com/x.png"
    assert views["img4"].content_type == "image"


def test_default_view_recorded() -> None:
    ws = parse_dsl(
        _workspace(
            """
            systemContext s "ctx" {
                include *
            }
            container s "cont" {
                include *
                default
            }
            """
        )
    )
    assert ws.views.configuration.default_view == "cont"


def test_view_properties_block() -> None:
    ws = parse_dsl(
        _workspace(
            """
            systemContext s "ctx" {
                include *
                properties {
                    "owner" "team-a"
                }
            }
            """
        )
    )
    assert ws.views[0].properties == {"owner": "team-a"}


def test_animation_steps_resolve_identifiers() -> None:
    ws = parse_dsl(
        _workspace(
            """
            systemContext s "ctx" {
                include *
                animation {
                    u s
                    web
                }
            }
            """
        )
    )
    view = ws.views[0]
    assert len(view.animations) == 2
    assert view.animations[0].order == 1
    assert view.animations[0].element_ids == ["u", "s"]
    assert view.animations[1].order == 2
    assert view.animations[1].element_ids == ["web"]


def test_autolayout_separations() -> None:
    ws = parse_dsl(
        _workspace(
            """
            systemContext s "ctx" {
                include *
                autoLayout lr 300 150
            }
            """
        )
    )
    layout = ws.views[0].auto_layout
    assert layout is not None
    assert layout.rank_separation == 300
    assert layout.node_separation == 150


def test_autolayout_without_separations_keeps_defaults() -> None:
    ws = parse_dsl(
        _workspace(
            """
            systemContext s "ctx" {
                include *
                autoLayout
            }
            """
        )
    )
    layout = ws.views[0].auto_layout
    assert layout is not None
    assert layout.rank_separation == 100
    assert layout.node_separation == 100


def test_view_features_round_trip_to_json() -> None:
    ws = parse_dsl(
        _workspace(
            """
            systemContext s "ctx" {
                include *
                default
                autoLayout tb 250 125
                animation {
                    u
                }
            }
            """
        )
    )
    data = workspace_to_json(ws)["workspace"]
    assert data["views"]["configuration"]["defaultView"] == "ctx"
    view = data["views"]["systemContextViews"][0]
    assert view["automaticLayout"]["rankSeparation"] == 250
    assert view["animations"][0]["elements"] == ["u"]
