"""Tests for include/exclude expressions and bulk directives (Phase 8)."""

from pystructurizr.parser.dsl import parse_dsl
from pystructurizr.graph.view_graph import build_view_graph
from pystructurizr.models import View, Workspace


WORKSPACE = """
workspace "W" {{
    model {{
        u = person "User" "" "VIP"
        admin = person "Admin"
        s = softwareSystem "S" {{
            web = container "Web"
            db = container "Database" "" "" "Datastore"
        }}
        ext = softwareSystem "External" "" "Legacy"
        u -> s "Uses"
        admin -> s "Administers" "" "AdminOnly"
        s -> ext "Calls"
    }}
    views {{
        {view}
    }}
}}
"""


def _view(ws: Workspace, key: str = "v") -> View:
    return next(v for v in ws.views if v.key == key)


def test_include_by_element_type() -> None:
    ws = parse_dsl(
        WORKSPACE.format(view='systemLandscape "v" { include element.type==Person }')
    )
    assert set(_view(ws).included_ids) == {"u", "admin"}


def test_include_by_element_tag() -> None:
    ws = parse_dsl(
        WORKSPACE.format(view='systemLandscape "v" { include element.tag==Legacy }')
    )
    assert set(_view(ws).included_ids) == {"ext"}


def test_include_by_implicit_tag() -> None:
    ws = parse_dsl(
        WORKSPACE.format(
            view='systemLandscape "v" { include "element.tag==Software System" }'
        )
    )
    assert set(_view(ws).included_ids) == {"s", "ext"}


def test_element_tag_requires_all_tags() -> None:
    ws = parse_dsl(
        WORKSPACE.format(view='systemLandscape "v" { include element.tag==Person,VIP }')
    )
    assert set(_view(ws).included_ids) == {"u"}


def test_include_by_parent() -> None:
    ws = parse_dsl(
        WORKSPACE.format(view='container s "v" { include element.parent==s }')
    )
    assert set(_view(ws).included_ids) == {"web", "db"}


def test_exclude_by_tag_expression() -> None:
    ws = parse_dsl(
        WORKSPACE.format(
            view='systemLandscape "v" { include * \n exclude element.tag==Legacy }'
        )
    )
    view = _view(ws)
    assert "ext" in view.excluded_ids


def test_afferent_efferent_expressions() -> None:
    ws = parse_dsl(WORKSPACE.format(view='systemLandscape "v" { include ->s-> }'))
    # s plus everything related to it in either direction
    assert set(_view(ws).included_ids) == {"u", "admin", "s", "ext"}
    ws2 = parse_dsl(WORKSPACE.format(view='systemLandscape "v" { include s-> }'))
    assert set(_view(ws2).included_ids) == {"s", "ext"}
    ws3 = parse_dsl(WORKSPACE.format(view='systemLandscape "v" { include ->ext }'))
    assert set(_view(ws3).included_ids) == {"ext", "s"}


def test_mixed_identifiers_and_expressions_on_one_line() -> None:
    ws = parse_dsl(
        WORKSPACE.format(
            view='systemLandscape "v" { include ext element.type==Person }'
        )
    )
    assert set(_view(ws).included_ids) == {"ext", "u", "admin"}


def test_exclude_relationship_between() -> None:
    ws = parse_dsl(
        WORKSPACE.format(view='systemLandscape "v" { include * \n exclude admin -> s }')
    )
    view = _view(ws)
    assert view.excluded_relationship_ids
    data = build_view_graph(ws, view)
    labels = {e["label"] if "label" in e else e["data"]["label"] for e in data["edges"]}
    assert "Administers" not in labels
    assert "Uses" in labels


def test_exclude_relationship_by_tag() -> None:
    ws = parse_dsl(
        WORKSPACE.format(
            view='systemLandscape "v" { include * \n exclude relationship.tag==AdminOnly }'
        )
    )
    view = _view(ws)
    data = build_view_graph(ws, view)
    labels = {e["data"]["label"] for e in data["edges"]}
    assert "Administers" not in labels
    assert "Uses" in labels


def test_exclude_all_relationships() -> None:
    ws = parse_dsl(
        WORKSPACE.format(
            view='systemLandscape "v" { include * \n exclude relationship==* }'
        )
    )
    data = build_view_graph(ws, _view(ws))
    assert data["edges"] == []


def test_exclude_relationship_by_source() -> None:
    ws = parse_dsl(
        WORKSPACE.format(
            view='systemLandscape "v" { include * \n exclude relationship.source==admin }'
        )
    )
    data = build_view_graph(ws, _view(ws))
    labels = {e["data"]["label"] for e in data["edges"]}
    assert "Administers" not in labels


def test_plain_include_lines_unchanged() -> None:
    ws = parse_dsl(
        WORKSPACE.format(view='systemLandscape "v" { include u s \n exclude s }')
    )
    view = _view(ws)
    assert view.included_ids == ["u", "s"]
    assert view.excluded_ids == ["s"]


def test_expressions_resolve_forward_references() -> None:
    dsl = """
    workspace "W" {
        views {
            systemLandscape "v" {
                include element.type==Person
            }
        }
        model {
            u = person "User"
        }
    }
    """
    ws = parse_dsl(dsl)
    assert set(_view(ws).included_ids) == {"u"}


def test_bang_elements_bulk_mutation() -> None:
    ws = parse_dsl(
        """
        workspace "W" {
            model {
                s = softwareSystem "S" {
                    web = container "Web"
                    db = container "Database"
                }
                !elements element.type==Container {
                    tags "Bulk"
                }
            }
        }
        """
    )
    containers = ws.software_systems[0].containers
    assert all("Bulk" in c.tags for c in containers)


def test_bang_relationships_bulk_mutation() -> None:
    ws = parse_dsl(
        """
        workspace "W" {
            model {
                u = person "User"
                s = softwareSystem "S"
                ext = softwareSystem "External"
                u -> s "Uses"
                s -> ext "Calls"
                !relationships relationship.source==s {
                    tags "Outbound"
                }
            }
        }
        """
    )
    by_desc = {r.description: r for r in ws.relationships}
    assert "Outbound" in by_desc["Calls"].tags
    assert "Outbound" not in by_desc["Uses"].tags
