"""Tests for include/exclude expressions and bulk directives (Phase 8)."""

from c4studio.graph.view_graph import build_view_graph
from c4studio.models import View, Workspace
from c4studio.parser.dsl import parse_dsl

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


WILDCARD_RELATIONSHIPS = """
workspace "W" {{
    model {{
        a = softwareSystem "A"
        b = softwareSystem "B"
        c = softwareSystem "C"
        a -> b "one"
        b -> c "two"
        !relationships {expression} {{
            tags "bulk"
        }}
    }}
}}
"""


def _tagged(expression: str) -> list[str]:
    ws = parse_dsl(WILDCARD_RELATIONSHIPS.format(expression=expression))
    return [r.description for r in ws.relationships if "bulk" in r.tags]


def test_bare_wildcard_matches_every_relationship() -> None:
    """`!relationships *` means every relationship, not every element.

    The bare wildcard produced an element-only result, so the relationship
    half of the outcome stayed empty and the block applied to nothing.
    Upstream rewrites the token literally to `*->*` for this reason.
    """
    assert _tagged("*") == ["one", "two"]


def test_quoted_wildcard_arrow_matches_every_relationship() -> None:
    """`"*->*"` is quoted, so the arrow never reaches the tokenizer.

    It used to fall through to the identifier branch and be looked up as an
    element literally named `*->*`.
    """
    assert _tagged('"*->*"') == ["one", "two"]


def test_wildcard_endpoints_match_one_side() -> None:
    """Half-wildcards were not in the report, and had the same cause."""
    assert _tagged("a -> *") == ["one"]
    assert _tagged('"*->c"') == ["two"]
    # And a fully-specified pair still means just that pair.
    assert _tagged("a -> b") == ["one"]


def test_an_expression_matching_nothing_is_reported() -> None:
    """Silence made a typo and a correctly-empty match indistinguishable."""
    ws = parse_dsl(WILDCARD_RELATIONSHIPS.format(expression="nothing -> here"))

    [diagnostic] = ws.diagnostics
    assert diagnostic.code == "no-relationships-matched"


def test_quoted_relationship_expressions_work_in_views_too() -> None:
    """Adjacent to the reported bug, and the same cause.

    A quoted expression has no ARROW *token*, so `is_expression_term` never
    routed it to the engine: `exclude "a->b"` looked for an element named
    `a->b`. Unquoted `exclude a -> b` always worked, which is what made this
    hard to see.
    """
    dsl = """
    workspace "W" {{
        model {{
            a = softwareSystem "A"
            b = softwareSystem "B"
            a -> b "one"
        }}
        views {{
            systemLandscape "L" {{
                include *
                exclude {expression}
            }}
        }}
    }}
    """
    for expression in ("a -> b", '"a->b"', '"*->*"', '"a->*"'):
        ws = parse_dsl(dsl.format(expression=expression))
        assert ws.views[0].excluded_relationship_ids, expression
