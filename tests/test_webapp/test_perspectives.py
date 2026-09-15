"""Perspectives carried through the graph layer (PP-173).

The viewer's perspective overlay needs three things from the backend: the
names to offer, each node's and edge's perspectives, and the paint any
``Perspective:`` style gives them. Upstream behaviour is in
``structurizr-application``'s ``structurizr-diagram.js`` (``runFilter``,
``getPerspectiveForElement``, ``findStyleForPerspective``).
"""

from __future__ import annotations

from typing import Any

import pytest

from c4studio.graph.view_graph import build_view_graph, perspective_names
from c4studio.models import Styles, Workspace
from c4studio.parser.dsl import parse_dsl
from c4studio.webapp.graph import react_flow_graph

JsonDict = dict[str, Any]


@pytest.fixture(autouse=True)
def _no_remote_themes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "c4studio.graph.view_graph.theme_styles", lambda workspace: Styles()
    )


DSL = """
workspace "W" {
    model {
        u = person "User" {
            perspectives {
                "Ownership" "End users" "External"
            }
        }
        s = softwareSystem "S" {
            perspectives {
                "Security" "TLS everywhere" "High"
            }
            group "Backend" {
                api = container "API" {
                    perspectives {
                        perspective "Security" {
                            description "mTLS"
                            value "Low"
                        }
                    }
                }
                db = container "DB"
            }
            web = container "Web"
        }
        u -> web "Uses" {
            perspectives {
                "Security" "Login over HTTPS" "High"
            }
        }
        web -> api "Calls" {
            perspectives {
                "Latency" "p99 50ms"
            }
        }
        api -> db "Reads" {
            perspectives {
                "Security" "Encrypted" "High"
            }
        }
        live = deploymentEnvironment "Live" {
            deploymentNode "Server" {
                apiInstance = containerInstance api {
                    perspectives {
                        "Cost" "Reserved" "Low"
                    }
                }
                dbInstance = containerInstance db
            }
        }
    }
    views {
        systemLandscape Landscape {
            include *
        }
        container s Containers {
            include *
        }
        deployment s "Live" Deployment {
            include *
        }
        dynamic s Steps {
            u -> web "Signs in"
            web -> api "Calls"
        }
        styles {
            element "Perspective:Security" {
                background #ffcc00
            }
            element "Perspective:Security[value==High]" {
                background #d32f2f
                color #ffffff
                stroke #7f0000
                dark {
                    color #eeeeee
                    background #b71c1c
                }
            }
            relationship "Perspective:Security[value==High]" {
                color #d32f2f
            }
        }
    }
}
"""


@pytest.fixture()
def workspace() -> Workspace:
    return parse_dsl(DSL)


def _graph(workspace: Workspace, key: str, **kwargs: Any) -> JsonDict:
    view = next(v for v in workspace.views if v.key == key)
    return build_view_graph(workspace, view, **kwargs)


def _node(data: JsonDict, node_id: str) -> JsonDict:
    return next(n for n in data["nodes"] if n["id"] == node_id)


def _edge(data: JsonDict, source: str, target: str) -> JsonDict:
    return next(
        e for e in data["edges"] if (e["source"], e["target"]) == (source, target)
    )


def test_names_cover_elements_and_relationships_sorted(workspace: Workspace) -> None:
    assert perspective_names(workspace) == ["Cost", "Latency", "Ownership", "Security"]


def test_node_carries_its_perspectives_and_resolved_paint(
    workspace: Workspace,
) -> None:
    data = _graph(workspace, "Landscape")
    # The value style replaces the base style whole; the dark variant is
    # skipped, as for every style the viewer resolves.
    assert _node(data, "s")["data"]["perspectives"] == [
        {
            "name": "Security",
            "description": "TLS everywhere",
            "value": "High",
            "background": "#d32f2f",
            "textColor": "#ffffff",
            "stroke": "#7f0000",
        }
    ]
    assert _node(data, "u")["data"]["perspectives"] == [
        {"name": "Ownership", "description": "End users", "value": "External"}
    ]


def test_value_without_its_own_style_falls_back_to_the_base_style(
    workspace: Workspace,
) -> None:
    data = _graph(workspace, "Containers")
    [security] = _node(data, "api")["data"]["perspectives"]
    assert security == {
        "name": "Security",
        "description": "mTLS",
        "value": "Low",
        "background": "#ffcc00",
    }
    assert "perspectives" not in _node(data, "db")["data"]
    assert "perspectives" not in _node(data, "web")["data"]


def test_direct_edge_carries_perspectives_lifted_edge_does_not(
    workspace: Workspace,
) -> None:
    containers = _graph(workspace, "Containers")
    assert _edge(containers, "u", "web")["data"]["perspectives"] == [
        {
            "name": "Security",
            "description": "Login over HTTPS",
            "value": "High",
            "color": "#d32f2f",
        }
    ]
    # u -> web lifts to u -> s on the landscape: one edge standing for
    # however many relationships, so it claims none of their perspectives.
    landscape = _graph(workspace, "Landscape")
    assert "perspectives" not in _edge(landscape, "u", "s")["data"]


def test_edge_lifted_onto_a_collapsed_group_drops_perspectives(
    workspace: Workspace,
) -> None:
    data = _graph(workspace, "Containers", collapse={"__group__s__Backend"})
    assert "perspectives" not in _edge(data, "web", "__group__s__Backend")["data"]


def test_container_instance_inherits_and_keeps_its_own(workspace: Workspace) -> None:
    data = _graph(workspace, "Deployment")
    names = [p["name"] for p in _node(data, "apiInstance")["data"]["perspectives"]]
    assert names == ["Cost", "Security"]
    # A replicated instance relationship is still that one relationship.
    assert (
        _edge(data, "apiInstance", "dbInstance")["data"]["perspectives"][0]["name"]
        == "Security"
    )


def test_instance_perspective_shadows_the_inherited_one() -> None:
    ws = parse_dsl(
        """
        workspace "W" {
            model {
                s = softwareSystem "S" {
                    c = container "C" {
                        perspectives {
                            "Cost" "Container says" "High"
                        }
                    }
                }
                deploymentEnvironment "Live" {
                    deploymentNode "N" {
                        ci = containerInstance c {
                            perspectives {
                                "Cost" "Instance says" "Low"
                            }
                        }
                    }
                }
            }
            views {
                deployment s "Live" D {
                    include *
                }
            }
        }
        """
    )
    data = _graph(ws, "D")
    assert _node(data, "ci")["data"]["perspectives"] == [
        {"name": "Cost", "description": "Instance says", "value": "Low"}
    ]


def test_dynamic_step_carries_the_model_relationship_perspectives(
    workspace: Workspace,
) -> None:
    data = _graph(workspace, "Steps")
    assert [p["name"] for p in _edge(data, "web", "api")["data"]["perspectives"]] == [
        "Latency"
    ]


def test_react_flow_payload_carries_names_and_edge_perspectives(
    workspace: Workspace,
) -> None:
    view = next(v for v in workspace.views if v.key == "Containers")
    payload = react_flow_graph(workspace, view)
    assert payload["perspectives"] == ["Cost", "Latency", "Ownership", "Security"]
    edge = next(
        e for e in payload["edges"] if (e["source"], e["target"]) == ("u", "web")
    )
    assert edge["perspectives"][0]["value"] == "High"
    node = next(n for n in payload["nodes"] if n["id"] == "api")
    assert node["data"]["perspectives"][0]["value"] == "Low"


def test_workspace_without_perspectives_adds_nothing() -> None:
    ws = parse_dsl(
        """
        workspace "W" {
            model {
                a = softwareSystem "A"
                b = softwareSystem "B"
                a -> b "Uses"
            }
            views {
                systemLandscape L {
                    include *
                }
            }
        }
        """
    )
    view = next(iter(ws.views))
    payload = react_flow_graph(ws, view)
    assert payload["perspectives"] == []
    assert all("perspectives" not in n["data"] for n in payload["nodes"])
    assert all("perspectives" not in e for e in payload["edges"])
