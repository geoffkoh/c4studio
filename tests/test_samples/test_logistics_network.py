"""The logistics sample keeps the wide end of the DSL working.

``samples/logistics_network.dsl`` deliberately exercises the keywords the
other samples never touch — groups, custom elements, ``this ->``,
relationship bodies, the bulk ``!element``/``!elements``/``!relationships``
directives, deployment groups, software-system instances, health checks,
view animation and properties, branding and terminology. Each check here
pins one of those keywords to its documented effect on the model
(``docs/dsl-support.md``), so a parser regression breaks a test instead of
quietly hollowing out the sample.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from c4studio.graph.view_graph import build_view_graph
from c4studio.models import Workspace
from c4studio.models.enums import ColorScheme
from c4studio.parser.dsl import parse_dsl_file

SAMPLE = Path(__file__).parent.parent.parent / "samples" / "logistics_network.dsl"


@pytest.fixture(scope="module")
def workspace() -> Workspace:
    return parse_dsl_file(SAMPLE)


def test_the_sample_parses_without_a_single_warning(workspace: Workspace) -> None:
    """A sample that warns is teaching the reader to ignore warnings."""
    assert workspace.diagnostics == []


def test_every_view_builds_a_graph(workspace: Workspace) -> None:
    """Every view in the sample renders to nodes and edges."""
    for view in workspace.views:
        graph = build_view_graph(workspace, view)
        assert graph["nodes"], f"view {view.key} produced no nodes"


def test_groups_land_on_people_and_containers(workspace: Workspace) -> None:
    """Model-level and nested ``group`` blocks assign the group name."""
    people = {p.name: p.group for p in workspace.model.people}
    assert people["Shipper"] == "Customers & Partners"
    assert people["Courier"] == "Operations"
    platform = next(
        s for s in workspace.model.software_systems if s.name == "Delivery Platform"
    )
    containers = {c.name: c.group for c in platform.containers}
    assert containers["Booking Portal"] == "Customer Channels"
    assert containers["Booking API"] == "Core Services"
    # Group context must not leak onto siblings declared outside the group.
    assert containers["Shipment Database"] == ""


def test_the_custom_element_round_trips(workspace: Workspace) -> None:
    custom = workspace.model.custom_elements
    assert [(e.name, e.metadata) for e in custom] == [("Telematics Unit", "IoT Device")]


def test_this_arrow_creates_the_relationship(workspace: Workspace) -> None:
    """``this ->`` inside the Booking API body targets the database."""
    rel = next(
        r
        for r in workspace.model.relationships
        if r.source_id == "bookingApi" and r.destination_id == "shipmentDb"
    )
    assert rel.technology == "SQL/TCP"


def test_the_relationship_body_attaches_everything(workspace: Workspace) -> None:
    """tags, url, properties and perspectives all stick to a relationship."""
    rel = next(
        r
        for r in workspace.model.relationships
        if r.source_id == "tracking" and r.destination_id == "eventBus"
    )
    assert "Async" in rel.tags
    assert rel.url == "https://wiki.northwind.example/tracking/consumers"
    assert rel.properties["consumerGroup"] == "tracking-v2"
    assert [p.name for p in rel.perspectives] == ["reliability"]


def test_element_body_metadata_lands(workspace: Workspace) -> None:
    """url, properties and perspectives inside an element body."""
    api = workspace.find_element("bookingApi")
    assert api is not None
    assert api.url == "https://api.northwind.example/booking"
    assert api.properties["owner"] == "booking-team"
    assert {p.name for p in api.perspectives} == {"security", "capacity"}


def test_bulk_directives_apply(workspace: Workspace) -> None:
    """!element, !elements and !relationships each modify their targets."""
    app = workspace.find_element("courierApp")
    assert app is not None
    assert app.url == "https://play.example.com/store/apps/northwind-courier"

    db = workspace.find_element("shipmentDb")
    assert db is not None
    assert db.properties["backup"] == "PITR, 35 days"

    # Implied copies (linked_relationship_id set) are derived after the
    # directive runs and inherit tags but not bulk-applied properties, so
    # the pin covers the declared relationships only.
    async_rels = [
        r
        for r in workspace.model.relationships
        if "Async" in r.tags and not r.linked_relationship_id
    ]
    assert async_rels
    assert all(r.properties.get("delivery") == "at-least-once" for r in async_rels)


def test_implied_relationships_reach_the_system(workspace: Workspace) -> None:
    """shipper -> portal implies shipper -> Delivery Platform."""
    assert any(
        r.source_id == "shipper" and r.destination_id == "platform"
        for r in workspace.model.relationships
    )


def test_deployment_groups_instances_and_health_checks(workspace: Workspace) -> None:
    region = next(
        n for n in workspace.model.deployment_nodes if n.name == "AWS eu-west-1"
    )
    eks = next(c for c in region.children if c.name == "EKS Cluster")
    assert eks.instances == "3"

    instances = {i.container_id: i for i in eks.container_instances}
    assert instances["tracking"].deployment_groups == [
        "Primary Region",
        "Failover Region",
    ]
    booking = instances["bookingApi"]
    assert booking.deployment_groups == ["Primary Region"]
    check = booking.health_checks[0]
    assert (check.name, check.interval, check.timeout) == (
        "Booking API liveness",
        30,
        2,
    )

    assert any(
        i.name == "Application Load Balancer" for i in region.infrastructure_nodes
    )

    depot = next(
        n for n in workspace.model.deployment_nodes if n.name == "Depot Edge Server"
    )
    assert depot.instances == "0..N"
    label = depot.software_system_instances[0]
    assert label.software_system_id == "labelSvc"
    assert label.health_checks[0].url == "http://depot.local:7000/health"


def test_view_default_title_properties_and_animation(workspace: Workspace) -> None:
    assert workspace.views.configuration.default_view == "NetworkLandscape"

    context = next(v for v in workspace.views if v.key == "PlatformContext")
    assert context.title == "Delivery Platform in its neighbourhood"
    assert context.properties["audience"] == "new joiners"
    assert [len(step.element_ids) for step in context.animations] == [4, 1, 3]


def test_the_exclude_expression_removes_the_async_edges(workspace: Workspace) -> None:
    """The sync-only container view drops exactly the Async relationships."""
    full = next(v for v in workspace.views if v.key == "PlatformContainers")
    sync = next(v for v in workspace.views if v.key == "PlatformSyncOnly")
    full_edges = len(build_view_graph(workspace, full)["edges"])
    sync_edges = len(build_view_graph(workspace, sync)["edges"])
    assert sync_edges < full_edges


def test_styles_branding_and_terminology(workspace: Workspace) -> None:
    config = workspace.views.configuration

    person_styles = [s for s in config.styles.element_styles if s.tag == "Person"]
    schemes = {s.color_scheme for s in person_styles}
    assert ColorScheme.DARK in schemes

    async_style = next(s for s in config.styles.relationship_styles if s.tag == "Async")
    assert async_style.dashed is True

    assert len(config.themes) == 2

    assert config.branding is not None
    assert config.branding.logo == "https://static.northwind.example/brand/logo.png"
    assert config.branding.font is not None
    assert config.branding.font.name == "Inter"

    assert config.terminology.person == "Actor"
    assert config.terminology.container == "Service"
    assert config.terminology.deployment_node == "Host"


def test_workspace_configuration_parses(workspace: Workspace) -> None:
    config = workspace.workspace_configuration
    assert config.scope == "landscape"
    assert config.visibility == "private"
    assert [(u.username, u.role) for u in config.users] == [("geoff", "write")]


def test_layout_hints_reach_their_boundaries(workspace: Workspace) -> None:
    """Both c4studio.autolayout forms land as rankDirection on boundaries."""
    containers = next(v for v in workspace.views if v.key == "PlatformContainers")
    data = build_view_graph(workspace, containers)
    group = next(
        n for n in data["nodes"] if n["id"] == "__group__platform__Core Services"
    )
    assert group["data"]["rankDirection"] == "LR"

    components = next(v for v in workspace.views if v.key == "RoutingComponents")
    data = build_view_graph(workspace, components)
    routing = next(n for n in data["nodes"] if n["id"] == "routing")
    assert routing["data"]["rankDirection"] == "LR"
