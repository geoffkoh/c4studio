"""Tests for !impliedRelationships and !element/!relationship extension (Phase 7)."""

from c4studio.generators.json_export import workspace_to_json
from c4studio.parser.dsl import parse_dsl
from c4studio.graph.view_graph import build_view_graph
from c4studio.models import Workspace


MODEL = """
        model {
            u = person "User"
            s = softwareSystem "S" {
                web = container "Web" {
                    handler = component "Handler"
                }
            }
            ext = softwareSystem "External"
            u -> web "Uses"
            handler -> ext "Calls"
        }
"""


def _pairs(ws: Workspace) -> set[tuple[str, str]]:
    return {(r.source_id, r.destination_id) for r in ws.relationships}


def test_implied_relationships_off_by_default() -> None:
    ws = parse_dsl(f'workspace "W" {{ {MODEL} }}')
    assert _pairs(ws) == {("u", "web"), ("handler", "ext")}


def test_implied_relationships_creates_parent_levels() -> None:
    ws = parse_dsl(f'workspace "W" {{ !impliedRelationships true {MODEL} }}')
    pairs = _pairs(ws)
    # u -> web implies u -> s
    assert ("u", "s") in pairs
    # handler -> ext implies web -> ext and s -> ext
    assert ("web", "ext") in pairs
    assert ("s", "ext") in pairs
    # no self or ancestor/descendant pairs
    assert ("s", "s") not in pairs
    implied = next(
        r for r in ws.relationships if (r.source_id, r.destination_id) == ("u", "s")
    )
    assert implied.description == "Uses"
    assert implied.linked_relationship_id


def test_implied_skips_existing_pairs() -> None:
    ws = parse_dsl(
        """
        workspace "W" {
            !impliedRelationships true
            model {
                u = person "User"
                s = softwareSystem "S" {
                    web = container "Web"
                }
                u -> s "Direct usage"
                u -> web "Uses web"
            }
        }
        """
    )
    rels = [
        r for r in ws.relationships if (r.source_id, r.destination_id) == ("u", "s")
    ]
    assert len(rels) == 1
    assert rels[0].description == "Direct usage"


def test_implied_relationships_false_is_noop() -> None:
    ws = parse_dsl(f'workspace "W" {{ !impliedRelationships false {MODEL} }}')
    assert _pairs(ws) == {("u", "web"), ("handler", "ext")}


def test_implied_relationships_export_linked_id() -> None:
    ws = parse_dsl(f'workspace "W" {{ !impliedRelationships true {MODEL} }}')
    data = workspace_to_json(ws)
    people = data["workspace"]["model"]["people"]
    rels = people[0]["relationships"]
    linked = [r for r in rels if r.get("linkedRelationshipId")]
    assert linked, "implied relationships must carry linkedRelationshipId"


def test_no_duplicate_edges_in_webapp_with_implied_on() -> None:
    ws = parse_dsl(
        f"""
        workspace "W" {{
            !impliedRelationships true
            {MODEL}
            views {{
                systemContext s "ctx" {{
                    include *
                }}
            }}
        }}
        """
    )
    data = build_view_graph(ws, ws.views[0])
    pairs = [(e["source"], e["target"]) for e in data["edges"]]
    assert len(pairs) == len(set(pairs)), f"duplicate edges: {pairs}"


def test_bang_element_extends_existing() -> None:
    ws = parse_dsl(
        """
        workspace "W" {
            model {
                s = softwareSystem "S"
                !element s {
                    tags "Extended"
                    url "https://example.com"
                    description "Updated"
                }
            }
        }
        """
    )
    system = ws.software_systems[0]
    assert "Extended" in system.tags
    assert system.url == "https://example.com"
    assert system.description == "Updated"


def test_bang_element_can_add_children() -> None:
    ws = parse_dsl(
        """
        workspace "W" {
            model {
                s = softwareSystem "S"
                !element s {
                    api = container "API"
                }
            }
        }
        """
    )
    assert [c.name for c in ws.software_systems[0].containers] == ["API"]


def test_relationship_alias_and_bang_relationship() -> None:
    ws = parse_dsl(
        """
        workspace "W" {
            model {
                u = person "User"
                s = softwareSystem "S"
                rel = u -> s "Uses"
                !relationship rel {
                    tags "Important"
                    url "https://example.com/spec"
                }
            }
        }
        """
    )
    rel = ws.relationships[0]
    assert rel.description == "Uses"
    assert "Important" in rel.tags
    assert rel.url == "https://example.com/spec"
