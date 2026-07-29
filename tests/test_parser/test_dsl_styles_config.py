"""Tests for style completeness, branding, terminology, workspace config (Phase 5)."""

import json

from pystructurizr.generators.json_export import workspace_to_json
from pystructurizr.models import ColorScheme, IconPosition, LineStyle, Routing
from pystructurizr.parser.dsl import parse_dsl
from pystructurizr.parser.json_parser import parse_json


def _workspace(views: str = "", extra: str = "") -> str:
    return f"""
    workspace "W" "Original description" {{
        model {{
            u = person "User"
            s = softwareSystem "S"
            u -> s "Uses"
        }}
        views {{ {views} }}
        {extra}
    }}
    """


def test_element_style_extended_properties() -> None:
    ws = parse_dsl(
        _workspace(
            """
            styles {
                element "Person" {
                    strokeWidth 3
                    metadata false
                    description false
                    iconPosition Left
                }
            }
            """
        )
    )
    style = ws.views.configuration.styles.element_styles[0]
    assert style.stroke_width == 3
    assert style.metadata is False
    assert style.description is False
    assert style.icon_position == IconPosition.LEFT


def test_element_style_light_dark_variants() -> None:
    ws = parse_dsl(
        _workspace(
            """
            styles {
                element "Person" {
                    background #ffffff
                    light {
                        background #eeeeee
                    }
                    dark {
                        background #111111
                        color #ffffff
                    }
                }
            }
            """
        )
    )
    styles = ws.views.configuration.styles.element_styles
    assert len(styles) == 3
    base = styles[0]
    assert base.background == "#ffffff"
    assert base.color_scheme is None
    by_scheme = {s.color_scheme: s for s in styles[1:]}
    assert by_scheme[ColorScheme.LIGHT].background == "#eeeeee"
    assert by_scheme[ColorScheme.DARK].background == "#111111"
    assert by_scheme[ColorScheme.DARK].color == "#ffffff"
    assert all(s.tag == "Person" for s in styles)


def test_relationship_style_extended_properties() -> None:
    ws = parse_dsl(
        _workspace(
            """
            styles {
                relationship "Relationship" {
                    style dotted
                    routing Orthogonal
                    jump false
                    position 40
                    opacity 80
                }
            }
            """
        )
    )
    style = ws.views.configuration.styles.relationship_styles[0]
    assert style.style == LineStyle.DOTTED
    assert style.routing == Routing.ORTHOGONAL
    assert style.jump is False
    assert style.position == 40
    assert style.opacity == 80


def test_style_extensions_round_trip_to_json() -> None:
    dsl = _workspace(
        """
        styles {
            element "Person" {
                iconPosition Top
                dark {
                    background #000000
                }
            }
            relationship "Relationship" {
                style dashed
                routing Curved
                jump true
            }
        }
        """
    )
    data = workspace_to_json(parse_dsl(dsl))
    styles = data["workspace"]["views"]["configuration"]["styles"]
    elements = styles["elements"]
    assert elements[0]["iconPosition"] == "Top"
    assert any(e.get("colorScheme") == "Dark" for e in elements)
    rel = styles["relationships"][0]
    assert rel["style"] == "Dashed"
    assert rel["routing"] == "Curved"
    assert rel["jump"] is True
    # And the JSON importer restores them.
    ws2 = parse_json(json.dumps(data))
    rel_style = ws2.views.configuration.styles.relationship_styles[0]
    assert rel_style.style == LineStyle.DASHED
    assert rel_style.routing == Routing.CURVED
    dark = next(
        s
        for s in ws2.views.configuration.styles.element_styles
        if s.color_scheme == ColorScheme.DARK
    )
    assert dark.background == "#000000"


def test_branding_parsed() -> None:
    ws = parse_dsl(
        _workspace(
            """
            branding {
                logo "https://example.com/logo.png"
                font "Open Sans"
            }
            """
        )
    )
    branding = ws.views.configuration.branding
    assert branding is not None
    assert branding.logo == "https://example.com/logo.png"
    assert branding.font.name == "Open Sans"


def test_terminology_parsed_and_exported() -> None:
    ws = parse_dsl(
        _workspace(
            """
            terminology {
                person "Human"
                softwareSystem "App"
                relationship "Flow"
            }
            """
        )
    )
    terminology = ws.views.configuration.terminology
    assert terminology.person == "Human"
    assert terminology.software_system == "App"
    assert terminology.relationship == "Flow"
    # container keeps its default
    assert terminology.container == "Container"
    # Export regression: terminology previously never reached the JSON.
    data = workspace_to_json(ws)
    exported = data["workspace"]["views"]["configuration"]["terminology"]
    assert exported == {
        "person": "Human",
        "softwareSystem": "App",
        "relationship": "Flow",
    }


def test_workspace_configuration_block() -> None:
    ws = parse_dsl(
        _workspace(
            extra="""
            configuration {
                scope softwaresystem
                visibility private
                users {
                    geoff write
                    "guest user" read
                }
            }
            """
        )
    )
    config = ws.workspace_configuration
    assert config.scope == "softwaresystem"
    assert config.visibility == "private"
    assert [(u.username, u.role) for u in config.users] == [
        ("geoff", "write"),
        ("guest user", "read"),
    ]
    data = workspace_to_json(ws)
    exported = data["workspace"]["configuration"]
    assert exported["scope"] == "softwaresystem"
    assert exported["users"] == [
        {"username": "geoff", "role": "write"},
        {"username": "guest user", "role": "read"},
    ]
    ws2 = parse_json(json.dumps(data))
    assert ws2.workspace_configuration.scope == "softwaresystem"
    assert ws2.workspace_configuration.users[0].username == "geoff"


def test_workspace_body_name_description_properties() -> None:
    ws = parse_dsl(
        _workspace(
            extra="""
            name "Renamed"
            description "New description"
            properties {
                "ws.key" "ws.value"
            }
            """
        )
    )
    assert ws.name == "Renamed"
    assert ws.description == "New description"
    assert ws.views.configuration.properties == {"ws.key": "ws.value"}
