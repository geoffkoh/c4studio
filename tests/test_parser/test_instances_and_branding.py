"""Deployment instance counts and branding fonts must survive parsing.

Both were parsed and then partly discarded: a range expression collapsed to
the default of 1, and a font's URL was dropped on the floor.
"""

from __future__ import annotations

import json

from pystructurizr.models import DeploymentNode
from pystructurizr.generators.json_export import export_json
from pystructurizr.parser.dsl import parse_dsl
from pystructurizr.parser.json_parser import parse_json


def _deployment_node(source: str) -> DeploymentNode:
    return parse_dsl(source).deployment_nodes[0]


def test_instance_range_expression_is_preserved() -> None:
    """Structurizr allows ``"0..N"``; it used to collapse to 1."""
    node = _deployment_node(
        'workspace "T" {\n'
        "    model {\n"
        '        deploymentEnvironment "P" {\n'
        '            n = deploymentNode "N" "desc" "tech" "Tag" "0..N"\n'
        "        }\n"
        "    }\n"
        "}\n"
    )

    assert node.instances == "0..N"


def test_plain_instance_count_still_works() -> None:
    node = _deployment_node(
        'workspace "T" {\n'
        "    model {\n"
        '        deploymentEnvironment "P" {\n'
        '            n = deploymentNode "N" "desc" "tech" "Tag" 3\n'
        "        }\n"
        "    }\n"
        "}\n"
    )

    assert node.instances == "3"


def test_instances_round_trip_through_workspace_json() -> None:
    workspace = parse_dsl(
        'workspace "T" {\n'
        "    model {\n"
        '        deploymentEnvironment "P" {\n'
        '            n = deploymentNode "N" "desc" "tech" "Tag" "0..N"\n'
        "        }\n"
        "    }\n"
        "}\n"
    )

    reparsed = parse_json(export_json(workspace))

    assert reparsed.deployment_nodes[0].instances == "0..N"


def test_branding_font_keeps_its_url() -> None:
    workspace = parse_dsl(
        'workspace "T" {\n'
        "    model {\n"
        "    }\n"
        "    views {\n"
        "        branding {\n"
        '            logo "https://example.com/logo.png"\n'
        '            font "Open Sans" "https://example.com/font.css"\n'
        "        }\n"
        "    }\n"
        "}\n"
    )

    branding = workspace.views.configuration.branding
    assert branding is not None
    assert branding.font.name == "Open Sans"
    assert branding.font.url == "https://example.com/font.css"


def test_branding_font_without_a_url() -> None:
    workspace = parse_dsl(
        'workspace "T" {\n'
        "    model {\n"
        "    }\n"
        "    views {\n"
        "        branding {\n"
        '            font "Open Sans"\n'
        "        }\n"
        "    }\n"
        "}\n"
    )

    branding = workspace.views.configuration.branding
    assert branding is not None
    assert branding.font.name == "Open Sans"
    assert branding.font.url == ""


def test_branding_round_trips_through_workspace_json() -> None:
    workspace = parse_dsl(
        'workspace "T" {\n'
        "    model {\n"
        "    }\n"
        "    views {\n"
        "        branding {\n"
        '            logo "https://example.com/logo.png"\n'
        '            font "Open Sans" "https://example.com/font.css"\n'
        "        }\n"
        "    }\n"
        "}\n"
    )

    exported = json.loads(export_json(workspace))
    branding = exported["workspace"]["views"]["configuration"]["branding"]
    assert branding["font"] == {
        "name": "Open Sans",
        "url": "https://example.com/font.css",
    }

    reparsed = parse_json(export_json(workspace))
    assert reparsed.views.configuration.branding is not None
    assert reparsed.views.configuration.branding.font.url == (
        "https://example.com/font.css"
    )
