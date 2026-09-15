"""Tests for ``perspectives { … }`` blocks (PP-172).

Upstream ``PerspectiveParser`` accepts ``<name> <description> [value]`` and
``perspective <name> { description … value … url … }``. The block form used
to be read as a run of one-line perspectives named ``description``,
``value`` and ``url``, with no diagnostic.
"""

import json

import pytest

from c4studio.generators.json_export import export_json
from c4studio.models.elements import Perspective
from c4studio.parser.dsl import UnsupportedFeatureWarning, parse_dsl

ELEMENT = """
workspace "W" {{
    model {{
        s = softwareSystem "S" {{
            perspectives {{
                {body}
            }}
        }}
    }}
}}
"""


def _perspectives(body: str) -> list[Perspective]:
    return parse_dsl(ELEMENT.format(body=body)).software_systems[0].perspectives


def test_block_form_sets_description_value_and_url() -> None:
    [perspective] = _perspectives(
        """perspective "Ownership" {
                    description "Owned by team 1."
                    value "Team 1"
                    url "https://example.com/team-1"
                }"""
    )
    assert perspective == Perspective(
        name="Ownership",
        description="Owned by team 1.",
        value="Team 1",
        url="https://example.com/team-1",
    )


def test_mixed_forms_as_in_upstream_test_dsl() -> None:
    """The shape of ``structurizr-dsl/src/test/resources/dsl/test.dsl``."""
    ws = parse_dsl(
        ELEMENT.format(
            body=""""Security" "A description..."
                perspective Ownership {
                    value "Team 1"
                    description "Owned by team 1."
                }
                Cost "Monthly spend" 3"""
        )
    )
    assert ws.diagnostics == []
    assert ws.software_systems[0].perspectives == [
        Perspective(name="Security", description="A description..."),
        Perspective(name="Ownership", description="Owned by team 1.", value="Team 1"),
        Perspective(name="Cost", description="Monthly spend", value="3"),
    ]


def test_block_form_on_relationship_and_deployment_node() -> None:
    dsl = """
    workspace "W" {
        model {
            a = softwareSystem "A"
            b = softwareSystem "B"
            r = a -> b "Calls" {
                perspectives {
                    perspective "Security" {
                        value "mTLS"
                    }
                }
            }
            !relationship r {
                perspectives {
                    perspective "Latency" {
                        description "p99 under 50ms"
                    }
                }
            }
            deploymentEnvironment "Live" {
                dn = deploymentNode "Server" {
                    perspectives {
                        perspective "Cost" {
                            value "High"
                        }
                    }
                }
            }
        }
    }
    """
    ws = parse_dsl(dsl)
    assert ws.diagnostics == []
    assert ws.relationships[0].perspectives == [
        Perspective(name="Security", value="mTLS"),
        Perspective(name="Latency", description="p99 under 50ms"),
    ]
    assert ws.deployment_nodes[0].perspectives == [
        Perspective(name="Cost", value="High")
    ]


def test_block_form_round_trips_through_json_export() -> None:
    ws = parse_dsl(
        ELEMENT.format(
            body="""perspective "Ownership" {
                    description "Team 1"
                    url "https://example.com"
                }"""
        )
    )
    exported = json.loads(export_json(ws))
    [system] = exported["workspace"]["model"]["softwareSystems"]
    [perspective] = system["perspectives"]
    assert perspective["name"] == "Ownership"
    assert perspective["description"] == "Team 1"
    assert perspective["url"] == "https://example.com"


def test_block_without_keyword_is_reported_and_skipped_whole() -> None:
    """``Ownership { … }`` is not valid upstream; its body must not leak."""
    with pytest.warns(UnsupportedFeatureWarning):
        ws = parse_dsl(
            ELEMENT.format(
                body="""Ownership {
                    description "Owned by team 1."
                    value "Team 1"
                }
                "Security" "TLS" """
            )
        )
    assert ws.software_systems[0].perspectives == [
        Perspective(name="Security", description="TLS")
    ]
    [diagnostic] = ws.diagnostics
    assert diagnostic.code == "invalid-perspective"
    assert "perspective <name>" in diagnostic.message


@pytest.mark.parametrize(
    "body",
    ['"Security"', '"Security" "TLS" "High" "extra"'],
    ids=["name-only", "too-many-tokens"],
)
def test_malformed_line_is_reported_not_kept(body: str) -> None:
    with pytest.warns(UnsupportedFeatureWarning):
        ws = parse_dsl(ELEMENT.format(body=body))
    assert ws.software_systems[0].perspectives == []
    [diagnostic] = ws.diagnostics
    assert diagnostic.code == "invalid-perspective"


def test_unknown_property_in_block_is_reported() -> None:
    with pytest.warns(UnsupportedFeatureWarning):
        ws = parse_dsl(
            ELEMENT.format(
                body="""perspective "Ownership" {
                    owner "Team 1"
                    value "T1"
                }"""
            )
        )
    assert ws.software_systems[0].perspectives == [
        Perspective(name="Ownership", value="T1")
    ]
    [diagnostic] = ws.diagnostics
    assert diagnostic.code == "invalid-perspective"
    assert "owner" in diagnostic.message


def test_duplicate_name_keeps_the_first() -> None:
    """Upstream ``ModelItem.addPerspective`` rejects a name already present."""
    with pytest.warns(UnsupportedFeatureWarning):
        ws = parse_dsl(
            ELEMENT.format(
                body=""""Security" "first"
                perspective "Security" {
                    description "second"
                }"""
            )
        )
    assert ws.software_systems[0].perspectives == [
        Perspective(name="Security", description="first")
    ]
    [diagnostic] = ws.diagnostics
    assert diagnostic.code == "duplicate-perspective"


def test_perspective_as_a_one_line_name_is_still_a_name() -> None:
    """Only ``perspective <name> {`` opens a block, as upstream checks size 3."""
    assert _perspectives('perspective "A perspective called perspective"') == [
        Perspective(name="perspective", description="A perspective called perspective")
    ]
