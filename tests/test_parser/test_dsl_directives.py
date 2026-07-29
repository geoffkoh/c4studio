"""Tests for the bang-directive dispatcher and the parse-warnings channel."""

import pytest

from pystructurizr.generators.json_export import workspace_to_json
from pystructurizr.parser.dsl import UnsupportedFeatureWarning, parse_dsl


def test_identifiers_directive_is_consumed_silently() -> None:
    dsl = """
    workspace "W" {
        !identifiers hierarchical
        model {
            u = person "User"
            s = softwareSystem "S"
            u -> s "Uses"
        }
    }
    """
    ws = parse_dsl(dsl)
    assert len(ws.people) == 1
    assert len(ws.software_systems) == 1
    assert len(ws.relationships) == 1
    assert ws.parse_warnings == []


def test_unknown_directive_with_argument_warns_and_skips() -> None:
    dsl = """
    workspace "W" {
        model {
            !someUnknownDirective false
            u = person "User"
            s = softwareSystem "S"
            u -> s "Uses"
        }
    }
    """
    with pytest.warns(UnsupportedFeatureWarning, match="someUnknownDirective"):
        ws = parse_dsl(dsl)
    assert len(ws.people) == 1
    assert len(ws.relationships) == 1
    assert any("someUnknownDirective" in w for w in ws.parse_warnings)


def test_unknown_directive_with_block_is_skipped() -> None:
    dsl = """
    workspace "W" {
        model {
            u = person "User"
            !plugin com.example.Plugin {
                key value
            }
            s = softwareSystem "S"
        }
    }
    """
    with pytest.warns(UnsupportedFeatureWarning, match="plugin"):
        ws = parse_dsl(dsl)
    assert [p.name for p in ws.people] == ["User"]
    assert [s.name for s in ws.software_systems] == ["S"]


def test_unknown_directive_inside_views_and_view_body() -> None:
    dsl = """
    workspace "W" {
        model {
            s = softwareSystem "S"
        }
        views {
            !script groovy {
                foo bar
            }
            systemContext s "ctx" {
                !unknownViewDirective
                include *
            }
        }
    }
    """
    with pytest.warns(UnsupportedFeatureWarning):
        ws = parse_dsl(dsl)
    assert len(ws.views) == 1
    assert ws.views[0].key == "ctx"
    assert ws.views[0].include_all is True


def test_parse_warnings_empty_by_default() -> None:
    dsl = """
    workspace "W" {
        model {
            u = person "User"
        }
    }
    """
    ws = parse_dsl(dsl)
    assert ws.parse_warnings == []


def test_parse_warnings_not_included_in_json_export() -> None:
    dsl = """
    workspace "W" {
        model {
            !plugin com.example.Plugin
            u = person "User"
        }
    }
    """
    with pytest.warns(UnsupportedFeatureWarning):
        ws = parse_dsl(dsl)
    assert ws.parse_warnings
    data = workspace_to_json(ws)
    assert "parse_warnings" not in data
    assert "parseWarnings" not in data
