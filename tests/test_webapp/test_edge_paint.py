"""Relationship-style paint on edges (PP-116).

Matching relationship styles resolve to ``color``/``lineStyle``/
``thickness``/``opacity`` on the edge data — only what a style actually
set, so the renderers keep the defaults (dashed, 2px, ``#444444``, the
upstream Structurizr house style) for everything else.
"""

from __future__ import annotations

from typing import Any

from c4studio.graph.view_graph import build_view_graph
from c4studio.parser.dsl import parse_dsl
from c4studio.webapp.graph import react_flow_graph

JsonDict = dict[str, Any]

DSL = """
workspace "W" {
    model {
        u = person "User"
        s = softwareSystem "S" {
            api = container "API"
            db = container "DB"
        }
        u -> api "Uses" "HTTPS"
        api -> db "Streams to" "Kafka" "Async"
        deploymentEnvironment "Production" {
            deploymentNode "Host" {
                apiInst = containerInstance api
                dbInst = containerInstance db
            }
        }
    }
    views {
        container s Containers {
            include *
        }
        dynamic s Flow {
            u -> api "Calls"
            api -> db "Streams"
            autoLayout
        }
        deployment * "Production" Prod {
            include *
        }
        styles {
            relationship "Async" {
                style dotted
                color #7b1fa2
                thickness 4
                opacity 80
                dark {
                    color #ff0000
                }
            }
            relationship "Legacy" {
                dashed false
            }
        }
    }
}
"""


def _edges(key: str) -> dict[tuple[str, str], JsonDict]:
    ws = parse_dsl(DSL)
    view = next(v for v in ws.views if v.key == key)
    data = build_view_graph(ws, view)
    return {(e["source"], e["target"]): e["data"] for e in data["edges"]}


def test_matching_style_paints_the_edge() -> None:
    edge = _edges("Containers")[("api", "db")]
    assert edge["lineStyle"] == "dotted"
    assert edge["color"] == "#7b1fa2"
    assert edge["thickness"] == 4
    assert edge["opacity"] == 80


def test_unstyled_edges_carry_no_paint_fields() -> None:
    """Defaults live in the renderers, not the payload."""
    edge = _edges("Containers")[("u", "api")]
    assert not {"color", "lineStyle", "thickness", "opacity"} & set(edge)


def test_dark_scheme_variants_are_skipped() -> None:
    """The viewer paints one scheme; the dark override must not win."""
    assert _edges("Containers")[("api", "db")]["color"] == "#7b1fa2"


def test_legacy_dashed_false_means_solid() -> None:
    ws = parse_dsl(DSL.replace('"Streams to" "Kafka" "Async"', '"x" "" "Legacy"'))
    view = next(v for v in ws.views if v.key == "Containers")
    data = build_view_graph(ws, view)
    edge = next(e for e in data["edges"] if e["source"] == "api")
    assert edge["data"]["lineStyle"] == "solid"


def test_dynamic_and_deployment_edges_carry_paint() -> None:
    flow = _edges("Flow")[("api", "db")]
    assert flow["lineStyle"] == "dotted"

    prod = _edges("Prod")
    instance_edge = next(
        data for (src, _), data in prod.items() if src.startswith("api")
    )
    assert instance_edge["color"] == "#7b1fa2"


def test_react_flow_reshape_passes_paint_through() -> None:
    ws = parse_dsl(DSL)
    view = next(v for v in ws.views if v.key == "Containers")
    payload = react_flow_graph(ws, view)
    styled = next(e for e in payload["edges"] if e["source"] == "api")
    plain = next(e for e in payload["edges"] if e["source"] == "u")
    assert (styled["lineStyle"], styled["color"]) == ("dotted", "#7b1fa2")
    assert "lineStyle" not in plain and "color" not in plain
