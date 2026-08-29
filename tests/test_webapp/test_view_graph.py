"""Tests for the view_graph builder reused by the web app."""

from __future__ import annotations

from pathlib import Path

import pytest

from c4studio.models import (
    Component,
    Container,
    Person,
    Relationship,
    SoftwareSystem,
    View,
    ViewType,
    Workspace,
)
from c4studio.parser.dsl import parse_dsl_file
from c4studio.graph.view_graph import apply_positions, build_view_graph
from typing import Any, cast

JsonDict = dict[str, Any]

FIXTURE = Path(__file__).parent.parent / "fixtures" / "example.dsl"


def _view(workspace: Workspace, view_type: ViewType) -> View:
    for view in workspace.views:
        if view.type == view_type:
            return view
    raise AssertionError(f"fixture has no {view_type} view")


def _node_by_label(data: JsonDict, label: str) -> JsonDict:
    for node in data["nodes"]:
        if node["data"]["label"] == label:
            return cast(JsonDict, node)
    raise AssertionError(f"no node labelled {label!r}")


def _edge_pairs(data: JsonDict) -> set[tuple[str, str]]:
    return {(e["source"], e["target"]) for e in data["edges"]}


@pytest.fixture
def workspace() -> Workspace:
    return parse_dsl_file(FIXTURE)


class TestSystemContextView:
    def test_shows_only_people_and_systems(self, workspace: Workspace) -> None:
        data = build_view_graph(workspace, _view(workspace, ViewType.SYSTEM_CONTEXT))
        kinds = {n["data"]["kind"] for n in data["nodes"]}
        assert "container" not in kinds
        assert "component" not in kinds
        labels = {n["data"]["label"] for n in data["nodes"]}
        assert labels == {
            "Personal Banking Customer",
            "Internet Banking System",
            "E-mail System",
            "Mainframe Banking System",
        }

    def test_lifts_container_relationships_to_the_system(
        self, workspace: Workspace
    ) -> None:
        data = build_view_graph(workspace, _view(workspace, ViewType.SYSTEM_CONTEXT))
        customer = _node_by_label(data, "Personal Banking Customer")["id"]
        bank = _node_by_label(data, "Internet Banking System")["id"]
        email = _node_by_label(data, "E-mail System")["id"]
        pairs = _edge_pairs(data)
        # customer -> spa/webapp lift to a single customer -> bank edge.
        assert (customer, bank) in pairs
        # api -> email lifts to bank -> email.
        assert (bank, email) in pairs
        # No self edges from intra-system relationships (webapp -> spa etc.).
        assert (bank, bank) not in pairs

    def test_has_no_boundary_node(self, workspace: Workspace) -> None:
        data = build_view_graph(workspace, _view(workspace, ViewType.SYSTEM_CONTEXT))
        assert all(n["data"]["kind"] != "boundary" for n in data["nodes"])


class TestContainerView:
    def test_scoped_system_becomes_the_boundary(self, workspace: Workspace) -> None:
        view = _view(workspace, ViewType.CONTAINER)
        data = build_view_graph(workspace, view)
        boundary = data["nodes"][0]
        assert boundary["data"]["kind"] == "boundary"
        assert boundary["id"] == view.element_id
        # The scoped system must not also appear as a leaf node.
        leaves = [n for n in data["nodes"][1:] if n["id"] == view.element_id]
        assert leaves == []

    def test_containers_are_nested_in_the_boundary(self, workspace: Workspace) -> None:
        view = _view(workspace, ViewType.CONTAINER)
        data = build_view_graph(workspace, view)
        containers = [n for n in data["nodes"] if n["data"]["kind"] == "container"]
        assert len(containers) == 4
        assert all(n["parentId"] == view.element_id for n in containers)

    def test_external_elements_stay_outside_the_boundary(
        self, workspace: Workspace
    ) -> None:
        data = build_view_graph(workspace, _view(workspace, ViewType.CONTAINER))
        outside = [
            n
            for n in data["nodes"]
            if n["data"]["kind"] in {"person", "system-external"}
        ]
        assert len(outside) == 3  # customer, email, mainframe
        assert all("parentId" not in n for n in outside)

    def test_edges_connect_leaves_across_the_boundary(
        self, workspace: Workspace
    ) -> None:
        data = build_view_graph(workspace, _view(workspace, ViewType.CONTAINER))
        api = _node_by_label(data, "API Application")["id"]
        email = _node_by_label(data, "E-mail System")["id"]
        pairs = _edge_pairs(data)
        assert (api, email) in pairs

    def test_nodes_carry_technology_and_description(self, workspace: Workspace) -> None:
        data = build_view_graph(workspace, _view(workspace, ViewType.CONTAINER))
        webapp = _node_by_label(data, "Web Application")
        assert webapp["data"]["technology"] == "Java, Spring MVC"
        assert webapp["data"]["description"] == "Serves static content"


class TestComponentView:
    @pytest.fixture
    def component_workspace(self) -> Workspace:
        """A workspace with components, built in code (fixture DSL has none)."""
        ws = Workspace(name="Shop")
        ctrl = Component(id="ctrl", name="Order Controller", technology="Spring MVC")
        svc = Component(id="svc", name="Order Service")
        api = Container(id="api", name="API", components=[ctrl, svc])
        db = Container(id="db", name="Database", technology="PostgreSQL")
        unrelated = Container(id="cache", name="Cache")
        ws.model.software_systems.append(
            SoftwareSystem(id="shop", name="Shop", containers=[api, db, unrelated])
        )
        ws.model.software_systems.append(
            SoftwareSystem(id="pay", name="Payment Provider")
        )
        ws.model.software_systems.append(
            SoftwareSystem(
                id="obs",
                name="Observability",
                containers=[Container(id="logStore", name="Log Store")],
            )
        )
        ws.model.people.append(Person(id="user", name="Customer"))
        ws.model.relationships.extend(
            [
                Relationship(source_id="user", destination_id="ctrl", id="r1"),
                Relationship(source_id="ctrl", destination_id="svc", id="r2"),
                Relationship(source_id="svc", destination_id="db", id="r3"),
                Relationship(source_id="svc", destination_id="pay", id="r4"),
                Relationship(source_id="svc", destination_id="logStore", id="r5"),
            ]
        )
        ws.views.append(
            View(type=ViewType.COMPONENT, key="components", element_id="api")
        )
        return ws

    def test_scoped_container_becomes_the_boundary(
        self, component_workspace: Workspace
    ) -> None:
        view = component_workspace.views[0]
        data = build_view_graph(component_workspace, view)
        boundary = data["nodes"][0]
        assert boundary["data"]["kind"] == "boundary"
        assert boundary["id"] == "api"

    def test_components_nest_and_related_peers_show(
        self, component_workspace: Workspace
    ) -> None:
        data = build_view_graph(component_workspace, component_workspace.views[0])
        by_id = {n["id"]: n for n in data["nodes"]}
        assert by_id["ctrl"]["parentId"] == "api"
        assert by_id["svc"]["parentId"] == "api"
        # Related sibling container, external system and person are outside.
        assert "parentId" not in by_id["db"]
        assert "pay" in by_id
        assert "user" in by_id
        # The unrelated sibling container and parent system are not shown.
        assert "cache" not in by_id
        assert "shop" not in by_id

    def test_peer_appears_at_declared_level_only(
        self, component_workspace: Workspace
    ) -> None:
        data = build_view_graph(component_workspace, component_workspace.views[0])
        by_id = {n["id"]: n for n in data["nodes"]}
        # svc -> logStore is declared against the container, so the container
        # shows and its parent system must NOT also appear as a floater.
        assert "logStore" in by_id
        assert "obs" not in by_id

    def test_cross_boundary_edges_survive(self, component_workspace: Workspace) -> None:
        data = build_view_graph(component_workspace, component_workspace.views[0])
        pairs = _edge_pairs(data)
        assert pairs == {
            ("user", "ctrl"),
            ("ctrl", "svc"),
            ("svc", "db"),
            ("svc", "pay"),
            ("svc", "logStore"),
        }


SPLIT_DEPLOY_DSL = """
workspace "Deploy" {
    model {
        u = person "User"
        s = softwareSystem "Shop" {
            web = container "Web" "storefront" "React"
            api = container "API" "backend" "Python" {
                orders = component "Orders" "order endpoints" "FastAPI"
                items  = component "Items" "catalogue endpoints" "FastAPI"
            }
        }
        other = softwareSystem "Analytics" {
            etl = container "ETL" "" "Python"
        }
        u -> web "Uses"
        web -> orders "Calls"
        orders -> items "Reads"
        api -> etl "Feeds"

        deploymentEnvironment "Production" {
            deploymentNode "Cloud" "" "AWS" {
                deploymentNode "Cluster" "" "EKS" {
                    webInst = containerInstance web
                    apiInst = containerInstance api
                }
                lb = infrastructureNode "Load Balancer" "" "ALB"
            }
            deploymentNode "Warehouse" "" "GCP" {
                etlInst = containerInstance etl
            }
            lb -> webInst "Forwards to"
        }
    }
    views {
        container s Containers { include * }
        deployment * "Production" Prod {
            include *
        }
        deployment s "Production" ShopProd {
            include *
        }
    }
}
"""


class TestDeploymentView:
    @pytest.fixture
    def deploy_workspace(self, tmp_path: Path) -> Workspace:
        path = tmp_path / "deploy.dsl"
        path.write_text(SPLIT_DEPLOY_DSL, encoding="utf-8")
        return parse_dsl_file(path)

    def test_nodes_nest_and_instances_take_container_identity(
        self, deploy_workspace: Workspace
    ) -> None:
        view = next(v for v in deploy_workspace.views if v.key == "Prod")
        data = build_view_graph(deploy_workspace, view)
        by_id = {n["id"]: n for n in data["nodes"]}
        assert by_id["cluster"]["parentId"] == "cloud"
        assert by_id["webInst"]["parentId"] == "cluster"
        assert by_id["webInst"]["data"]["kind"] == "container-instance"
        assert by_id["webInst"]["data"]["label"] == "Web"
        assert by_id["webInst"]["data"]["technology"] == "React"
        assert by_id["lb"]["data"]["kind"] == "infrastructure"
        boundaries = [n for n in data["nodes"] if n["data"]["kind"] == "boundary"]
        assert all(n["data"]["boundaryLabel"] == "Deployment Node" for n in boundaries)

    def test_edges_derive_from_model_and_declared_relationships(
        self, deploy_workspace: Workspace
    ) -> None:
        view = next(v for v in deploy_workspace.views if v.key == "Prod")
        data = build_view_graph(deploy_workspace, view)
        pairs = _edge_pairs(data)
        # web -> orders (component of api) derives webInst -> apiInst.
        assert ("webInst", "apiInst") in pairs
        # api -> etl derives apiInst -> etlInst across deployment nodes.
        assert ("apiInst", "etlInst") in pairs
        # Declared infrastructure relationship survives as-is.
        assert ("lb", "webInst") in pairs

    def test_scoped_deployment_prunes_unrelated_branches(
        self, deploy_workspace: Workspace
    ) -> None:
        view = next(v for v in deploy_workspace.views if v.key == "ShopProd")
        data = build_view_graph(deploy_workspace, view)
        ids = {n["id"] for n in data["nodes"]}
        assert "webInst" in ids and "apiInst" in ids
        # The GCP branch only hosts Analytics, so it is pruned entirely.
        assert "warehouse" not in ids
        assert "etlInst" not in ids


class TestContainerExpansion:
    @pytest.fixture
    def deploy_workspace(self, tmp_path: Path) -> Workspace:
        path = tmp_path / "deploy.dsl"
        path.write_text(SPLIT_DEPLOY_DSL, encoding="utf-8")
        return parse_dsl_file(path)

    def test_containers_with_components_are_flagged_expandable(
        self, deploy_workspace: Workspace
    ) -> None:
        view = next(v for v in deploy_workspace.views if v.key == "Containers")
        data = build_view_graph(deploy_workspace, view)
        by_id = {n["id"]: n for n in data["nodes"]}
        assert by_id["api"]["data"].get("expandable") is True
        assert "expandable" not in by_id["web"]["data"]

    def test_expanded_container_becomes_nested_boundary(
        self, deploy_workspace: Workspace
    ) -> None:
        view = next(v for v in deploy_workspace.views if v.key == "Containers")
        data = build_view_graph(deploy_workspace, view, expand={"api"})
        by_id = {n["id"]: n for n in data["nodes"]}
        assert by_id["api"]["data"]["kind"] == "boundary"
        assert by_id["api"]["data"]["expanded"] is True
        assert by_id["api"]["parentId"] == "s"
        assert by_id["orders"]["parentId"] == "api"
        assert by_id["items"]["parentId"] == "api"
        # Edges re-attach at component level inside the expansion.
        pairs = _edge_pairs(data)
        assert ("web", "orders") in pairs
        assert ("orders", "items") in pairs

    def test_expanding_unknown_or_component_free_ids_is_a_noop(
        self, deploy_workspace: Workspace
    ) -> None:
        view = next(v for v in deploy_workspace.views if v.key == "Containers")
        plain = build_view_graph(deploy_workspace, view)
        expanded = build_view_graph(deploy_workspace, view, expand={"web", "nope"})
        assert [n["id"] for n in plain["nodes"]] == [n["id"] for n in expanded["nodes"]]


class TestTagBasedStyles:
    @pytest.fixture
    def styled_workspace(self, tmp_path: Path) -> Workspace:
        dsl = """
        workspace "Styled" {
            model {
                u = person "User"
                s = softwareSystem "Shop" {
                    web = container "Web" "" "React"
                    db = container "DB" "" "PostgreSQL" "Database"
                }
                u -> web "Uses"
                web -> db "Reads"
            }
            views {
                container s Containers {
                    include *
                }
                styles {
                    element "Person" {
                        background #08427b
                        color #ffffff
                    }
                    element "Database" {
                        shape Cylinder
                        background #2e7d32
                    }
                }
            }
        }
        """
        path = tmp_path / "styled.dsl"
        path.write_text(dsl, encoding="utf-8")
        return parse_dsl_file(path)

    def test_styles_overlay_matching_nodes(self, styled_workspace: Workspace) -> None:
        view = styled_workspace.views[0]
        data = build_view_graph(styled_workspace, view)
        by_id = {n["id"]: n for n in data["nodes"]}
        assert by_id["u"]["data"]["background"] == "#08427b"
        assert by_id["u"]["data"]["textColor"] == "#ffffff"
        assert by_id["db"]["data"]["shape"] == "Cylinder"
        assert by_id["db"]["data"]["background"] == "#2e7d32"
        # Unstyled elements carry no overrides.
        assert "background" not in by_id["web"]["data"]
        assert "shape" not in by_id["web"]["data"]

    def test_view_graph_prefers_style_background_over_palette(
        self, styled_workspace: Workspace
    ) -> None:
        from c4studio.webapp.graph import react_flow_graph

        data = react_flow_graph(styled_workspace, styled_workspace.views[0])
        by_id = {n["id"]: n for n in data["nodes"]}
        assert by_id["db"]["data"]["color"] == "#2e7d32"
        assert by_id["web"]["data"]["color"] == "#43a047"  # palette fallback


class TestSystemLandscapeView:
    @pytest.fixture
    def landscape_workspace(self, tmp_path: Path) -> Workspace:
        dsl = """
        workspace "Land" {
            model {
                enterprise "Acme"
                staff = person "Staff"
                visitor = person "Visitor" "" "External Person"
                core = softwareSystem "Core" {
                    api = container "API"
                }
                vendor = softwareSystem "Vendor" "" "External System"
                staff -> api "Uses"
                visitor -> core "Browses"
                core -> vendor "Calls"
            }
            views {
                systemLandscape Landscape "The Landscape" {
                    include *
                    autoLayout
                }
            }
        }
        """
        path = tmp_path / "land.dsl"
        path.write_text(dsl, encoding="utf-8")
        return parse_dsl_file(path)

    def test_key_is_not_swallowed_as_scope(
        self, landscape_workspace: Workspace
    ) -> None:
        view = landscape_workspace.views[0]
        assert view.key == "Landscape"
        assert view.element_id == ""
        assert view.title == "The Landscape"

    def test_shows_all_people_and_systems_only(
        self, landscape_workspace: Workspace
    ) -> None:
        data = build_view_graph(landscape_workspace, landscape_workspace.views[0])
        kinds = {n["id"]: n["data"]["kind"] for n in data["nodes"]}
        assert "api" not in kinds  # containers never appear
        assert kinds["staff"] == "person"
        assert kinds["vendor"] == "system-external"

    def test_enterprise_boundary_nests_internal_elements(
        self, landscape_workspace: Workspace
    ) -> None:
        data = build_view_graph(landscape_workspace, landscape_workspace.views[0])
        by_id = {n["id"]: n for n in data["nodes"]}
        boundary = by_id["__enterprise__"]
        assert boundary["data"]["kind"] == "boundary"
        assert boundary["data"]["label"] == "Acme"
        assert boundary["data"]["boundaryLabel"] == "Enterprise"
        assert by_id["staff"]["parentId"] == "__enterprise__"
        assert by_id["core"]["parentId"] == "__enterprise__"
        assert "parentId" not in by_id["visitor"]
        assert "parentId" not in by_id["vendor"]

    def test_edges_lift_to_systems(self, landscape_workspace: Workspace) -> None:
        data = build_view_graph(landscape_workspace, landscape_workspace.views[0])
        pairs = _edge_pairs(data)
        assert pairs == {
            ("staff", "core"),
            ("visitor", "core"),
            ("core", "vendor"),
        }


class TestDynamicView:
    @pytest.fixture
    def dynamic_workspace(self, tmp_path: Path) -> Workspace:
        dsl = """
        workspace "Dyn" {
            model {
                u = person "User"
                s = softwareSystem "Shop" {
                    web = container "Web"
                    api = container "API"
                    db = container "DB"
                }
                u -> web "Uses"
                web -> api "Calls" "HTTPS"
                api -> db "Reads"
            }
            views {
                dynamic s Checkout "Checkout flow" {
                    u -> web "Adds items to the basket"
                    web -> api "Places the order"
                    api -> db
                    autoLayout lr
                }
            }
        }
        """
        path = tmp_path / "dyn.dsl"
        path.write_text(dsl, encoding="utf-8")
        return parse_dsl_file(path)

    def test_parser_captures_ordered_steps(self, dynamic_workspace: Workspace) -> None:
        view = dynamic_workspace.views[0]
        assert view.key == "Checkout"
        assert [rv.order for rv in view.relationship_views] == ["1", "2", "3"]
        assert view.relationship_views[0].id == "u__web"
        assert view.auto_layout is not None  # autoLayout still parsed after steps

    def test_edges_carry_order_and_numbered_labels(
        self, dynamic_workspace: Workspace
    ) -> None:
        view = dynamic_workspace.views[0]
        data = build_view_graph(dynamic_workspace, view)
        labels = [e["data"]["label"] for e in data["edges"]]
        assert labels[0] == "1. Adds items to the basket"
        assert labels[1] == "2. Places the order"
        # Step without a description falls back to the model relationship's.
        assert labels[2] == "3. Reads"
        assert [e["data"]["order"] for e in data["edges"]] == [1, 2, 3]

    def test_nodes_are_referenced_elements_flat(
        self, dynamic_workspace: Workspace
    ) -> None:
        view = dynamic_workspace.views[0]
        data = build_view_graph(dynamic_workspace, view)
        by_id = {n["id"]: n for n in data["nodes"]}
        assert set(by_id) == {"u", "web", "api", "db"}
        assert all("parentId" not in n for n in data["nodes"])
        assert by_id["web"]["data"]["kind"] == "container"


EXPANSION_DSL = """
workspace "Exp" {
    model {
        enterprise "Acme"
        u = person "User"
        s = softwareSystem "Shop" {
            web = container "Web"
            api = container "API" {
                orders = component "Orders"
                items  = component "Items"
            }
        }
        vendor = softwareSystem "Vendor" "" "External System" {
            vapi = container "Vendor API"
        }
        u -> web "Uses"
        web -> orders "Calls"
        orders -> items "Reads"
        api -> vapi "Fetches prices from"
    }
    views {
        systemLandscape Land "Landscape" {
            include *
        }
        systemContext s Ctx "Context" {
            include *
        }
    }
}
"""


class TestGeneralizedExpansion:
    @pytest.fixture
    def exp_workspace(self, tmp_path: Path) -> Workspace:
        path = tmp_path / "exp.dsl"
        path.write_text(EXPANSION_DSL, encoding="utf-8")
        return parse_dsl_file(path)

    def _view(self, ws: Workspace, key: str) -> View:
        return next(v for v in ws.views if v.key == key)

    def test_system_leaves_are_flagged_expandable(
        self, exp_workspace: Workspace
    ) -> None:
        data = build_view_graph(exp_workspace, self._view(exp_workspace, "Ctx"))
        by_id = {n["id"]: n for n in data["nodes"]}
        assert by_id["s"]["data"].get("expandable") is True
        # External systems with modelled containers are expandable too.
        assert by_id["vendor"]["data"].get("expandable") is True
        assert "expandable" not in by_id["u"]["data"]

    def test_expanding_a_system_in_a_context_view(
        self, exp_workspace: Workspace
    ) -> None:
        view = self._view(exp_workspace, "Ctx")
        data = build_view_graph(exp_workspace, view, expand={"s"})
        by_id = {n["id"]: n for n in data["nodes"]}
        assert by_id["s"]["data"]["kind"] == "boundary"
        assert by_id["s"]["data"]["boundaryLabel"] == "Software System"
        assert by_id["s"]["data"]["expanded"] is True
        assert by_id["web"]["parentId"] == "s"
        assert by_id["api"]["parentId"] == "s"
        # Containers inside the expansion expose their own expandability.
        assert by_id["api"]["data"].get("expandable") is True
        assert "expandable" not in by_id["web"]["data"]
        # Edges re-attach at container level.
        pairs = _edge_pairs(data)
        assert ("u", "web") in pairs
        assert ("api", "vendor") in pairs

    def test_nested_expansion_system_then_container(
        self, exp_workspace: Workspace
    ) -> None:
        view = self._view(exp_workspace, "Ctx")
        data = build_view_graph(exp_workspace, view, expand={"s", "api"})
        by_id = {n["id"]: n for n in data["nodes"]}
        assert by_id["api"]["data"]["kind"] == "boundary"
        assert by_id["api"]["parentId"] == "s"
        assert by_id["orders"]["parentId"] == "api"
        assert by_id["items"]["parentId"] == "api"
        pairs = _edge_pairs(data)
        assert ("web", "orders") in pairs
        assert ("orders", "items") in pairs

    def test_expanding_a_container_requires_its_parent_expanded(
        self, exp_workspace: Workspace
    ) -> None:
        view = self._view(exp_workspace, "Ctx")
        # api is not visible in a context view unless s is expanded, so
        # expanding only api is a no-op.
        data = build_view_graph(exp_workspace, view, expand={"api"})
        ids = {n["id"] for n in data["nodes"]}
        assert "api" not in ids
        assert "orders" not in ids

    def test_expanded_system_nests_inside_enterprise_boundary(
        self, exp_workspace: Workspace
    ) -> None:
        view = self._view(exp_workspace, "Land")
        data = build_view_graph(exp_workspace, view, expand={"s"})
        by_id = {n["id"]: n for n in data["nodes"]}
        assert by_id["s"]["data"]["expanded"] is True
        assert by_id["s"]["parentId"] == "__enterprise__"
        assert by_id["web"]["parentId"] == "s"
        # Externals stay outside both boundaries.
        assert "parentId" not in by_id["vendor"]


class TestRankDirection:
    def test_defaults_to_top_bottom(self, workspace: Workspace) -> None:
        from c4studio.webapp.graph import react_flow_graph

        data = react_flow_graph(workspace, workspace.views[0])
        assert data["rankDirection"] == "TB"

    def test_honours_autolayout_direction(self, tmp_path: Path) -> None:
        from c4studio.webapp.graph import react_flow_graph

        dsl = """
        workspace {
            model {
                u = person "User"
                s = softwareSystem "System"
                u -> s "Uses"
            }
            views {
                systemContext s ctx {
                    include *
                    autoLayout lr
                }
            }
        }
        """
        path = tmp_path / "lr.dsl"
        path.write_text(dsl, encoding="utf-8")
        ws = parse_dsl_file(path)
        data = react_flow_graph(ws, ws.views[0])
        assert data["rankDirection"] == "LR"


def test_apply_positions_round_trip(workspace: Workspace) -> None:
    view = workspace.views[0]
    # Pick two visible node ids from the generated graph so the test does
    # not depend on the specific identifiers in the fixture.
    ids = [n["id"] for n in build_view_graph(workspace, view)["nodes"]][:2]
    assert len(ids) == 2

    apply_positions(view, {ids[0]: (100, 200), ids[1]: (300, 400)})
    assert len(view.element_views) == 2

    data = build_view_graph(workspace, view)
    positioned = {
        node["id"]: node["style"]
        for node in data["nodes"]
        if "style" in node and "x" in node["style"]
    }
    assert positioned[ids[0]] == {"x": 100, "y": 200}
    assert positioned[ids[1]] == {"x": 300, "y": 400}
