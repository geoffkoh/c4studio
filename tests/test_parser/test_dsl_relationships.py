"""Tests for relationship metadata and `this` references (Phase 1 of DSL parity)."""

from c4studio.generators.json_export import workspace_to_json
from c4studio.parser.dsl import parse_dsl


def test_relationship_positional_tags() -> None:
    dsl = """
    workspace "W" {
        model {
            u = person "User"
            s = softwareSystem "S"
            u -> s "Uses" "HTTPS" "tag one,tag two"
        }
    }
    """
    ws = parse_dsl(dsl)
    rel = ws.relationships[0]
    assert rel.description == "Uses"
    assert rel.technology == "HTTPS"
    assert rel.tags == ["tag one", "tag two"]


def test_relationship_nested_block() -> None:
    dsl = """
    workspace "W" {
        model {
            u = person "User"
            s = softwareSystem "S"
            u -> s "Uses" {
                tags "Async" "Critical"
                url "https://example.com/spec"
                properties {
                    "protocol" "amqp"
                }
                perspectives {
                    "Security" "mTLS"
                }
            }
        }
    }
    """
    ws = parse_dsl(dsl)
    rel = ws.relationships[0]
    assert "Async" in rel.tags
    assert "Critical" in rel.tags
    assert rel.url == "https://example.com/spec"
    assert rel.properties == {"protocol": "amqp"}
    assert len(rel.perspectives) == 1
    assert rel.perspectives[0].name == "Security"
    assert rel.perspectives[0].description == "mTLS"


def test_relationship_positional_tags_combine_with_nested() -> None:
    dsl = """
    workspace "W" {
        model {
            u = person "User"
            s = softwareSystem "S"
            u -> s "Uses" "HTTPS" "positional" {
                tags "nested"
            }
        }
    }
    """
    ws = parse_dsl(dsl)
    rel = ws.relationships[0]
    assert "positional" in rel.tags
    assert "nested" in rel.tags


def test_this_as_relationship_source() -> None:
    dsl = """
    workspace "W" {
        model {
            u = person "User"
            s = softwareSystem "S" {
                web = container "Web" {
                    this -> u "Notifies"
                }
            }
        }
    }
    """
    ws = parse_dsl(dsl)
    rel = ws.relationships[0]
    assert rel.source_id == ws.software_systems[0].containers[0].id
    assert rel.destination_id == ws.people[0].id
    assert rel.description == "Notifies"


def test_this_as_relationship_destination() -> None:
    dsl = """
    workspace "W" {
        model {
            u = person "User"
            s = softwareSystem "S" {
                u -> this "Uses"
            }
        }
    }
    """
    ws = parse_dsl(dsl)
    rel = ws.relationships[0]
    assert rel.source_id == ws.people[0].id
    assert rel.destination_id == ws.software_systems[0].id


def test_implicit_source_arrow_in_element_body() -> None:
    dsl = """
    workspace "W" {
        model {
            db = softwareSystem "Database"
            s = softwareSystem "S" {
                -> db "Reads from"
            }
        }
    }
    """
    ws = parse_dsl(dsl)
    rel = ws.relationships[0]
    assert rel.source_id == ws.software_systems[1].id
    assert rel.destination_id == ws.software_systems[0].id
    assert rel.description == "Reads from"


def test_dynamic_view_step_block_does_not_leak() -> None:
    dsl = """
    workspace "W" {
        model {
            u = person "User"
            s = softwareSystem "S"
            u -> s "Uses"
        }
        views {
            dynamic s "dyn" {
                u -> s "Requests" {
                    url "https://example.com"
                }
                autoLayout lr
            }
        }
    }
    """
    ws = parse_dsl(dsl)
    view = ws.views[0]
    assert len(view.relationship_views) == 1
    # autoLayout after the step block must still be recognised.
    assert view.auto_layout is not None


def test_relationship_metadata_round_trips_to_json() -> None:
    dsl = """
    workspace "W" {
        model {
            u = person "User"
            s = softwareSystem "S"
            u -> s "Uses" "HTTPS" "Critical" {
                url "https://example.com/spec"
                properties {
                    "protocol" "amqp"
                }
            }
        }
    }
    """
    ws = parse_dsl(dsl)
    data = workspace_to_json(ws)
    people = data["workspace"]["model"]["people"]
    rels = people[0]["relationships"]
    assert rels[0]["technology"] == "HTTPS"
    assert "Critical" in rels[0]["tags"]
    assert rels[0]["url"] == "https://example.com/spec"
    assert rels[0]["properties"] == {"protocol": "amqp"}
