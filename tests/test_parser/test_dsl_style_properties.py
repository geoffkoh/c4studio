"""``properties { … }`` inside a style block (PP-175).

A style is a ``PropertyHolder`` upstream (``AbstractStyle``), and
``StructurizrDslParser`` accepts the block in both element and
relationship style contexts. c4studio dropped it silently, which also cost
the workspace's own properties on a JSON round-trip.
"""

from __future__ import annotations

import warnings

from c4studio.generators.json_export import export_json
from c4studio.parser.dsl import parse_dsl
from c4studio.parser.json_parser import parse_json

DSL = """
workspace "W" {
    model {
        a = softwareSystem "A" {
            tags "Datastore"
        }
        b = softwareSystem "B"
        a -> b "Uses" "" "New"
    }
    views {
        systemLandscape L {
            include *
        }
        styles {
            element "Datastore" {
                shape Cylinder
                properties {
                    "c4studio.legend" "Durable store"
                    "owner" "team-a"
                }
            }
            relationship "New" {
                color #2e7d32
                properties {
                    "c4studio.legend" "Added in release 24"
                }
            }
        }
    }
}
"""


def test_properties_are_parsed_on_both_style_kinds() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # the block must not warn
        workspace = parse_dsl(DSL)
    styles = workspace.views.configuration.styles
    assert styles.element_styles[0].properties == {
        "c4studio.legend": "Durable store",
        "owner": "team-a",
    }
    assert styles.relationship_styles[0].properties == {
        "c4studio.legend": "Added in release 24"
    }
    assert workspace.diagnostics == []


def test_the_rest_of_the_style_still_parses_around_the_block() -> None:
    styles = parse_dsl(DSL).views.configuration.styles
    assert styles.element_styles[0].shape is not None
    assert styles.relationship_styles[0].color == "#2e7d32"


def test_properties_survive_a_json_round_trip() -> None:
    workspace = parse_json(export_json(parse_dsl(DSL)))
    styles = workspace.views.configuration.styles
    assert styles.element_styles[0].properties["owner"] == "team-a"
    assert (
        styles.relationship_styles[0].properties["c4studio.legend"]
        == "Added in release 24"
    )


def test_a_style_without_properties_exports_none() -> None:
    """`_clean` drops empty collections, so nothing new appears."""
    workspace = parse_dsl(
        """
        workspace "W" {
            model {
                a = softwareSystem "A"
            }
            views {
                systemLandscape L {
                    include *
                }
                styles {
                    element "Software System" {
                        background #ff0000
                    }
                }
            }
        }
        """
    )
    exported = export_json(workspace)
    assert '"properties"' not in exported
