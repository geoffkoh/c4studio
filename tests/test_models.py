"""Tests for all new and updated model dataclasses."""

from pystructurizr.models import (
    Animation,
    AutomaticLayout,
    Component,
    Configuration,
    Container,
    ContainerInstance,
    CustomElement,
    Decision,
    DeploymentNode,
    ElementStyle,
    Enterprise,
    Format,
    HttpHealthCheck,
    InfrastructureNode,
    InteractionStyle,
    Location,
    Model,
    PaperSize,
    Perspective,
    Person,
    RankDirection,
    Relationship,
    RelationshipStyle,
    RelationshipView,
    Section,
    Shape,
    SoftwareSystem,
    SoftwareSystemInstance,
    Styles,
    Terminology,
    Branding,
    Font,
    Documentation,
    Vertex,
    View,
    ViewElement,
    ViewSet,
    ViewType,
    Workspace,
)


# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------


def test_location_enum_values() -> None:
    assert Location.INTERNAL.value == "Internal"
    assert Location.EXTERNAL.value == "External"
    assert Location.UNSPECIFIED.value == "Unspecified"


def test_interaction_style_enum() -> None:
    assert InteractionStyle.SYNCHRONOUS.value == "Synchronous"
    assert InteractionStyle.ASYNCHRONOUS.value == "Asynchronous"


def test_rank_direction_enum() -> None:
    assert RankDirection.TOP_BOTTOM.value == "TopBottom"
    assert RankDirection.LEFT_RIGHT.value == "LeftRight"


def test_shape_enum_has_all_values() -> None:
    assert Shape.BOX.value == "Box"
    assert Shape.PERSON.value == "Person"
    assert Shape.COMPONENT.value == "Component"


def test_view_type_has_new_values() -> None:
    assert ViewType.SYSTEM_LANDSCAPE.value == "systemLandscape"
    assert ViewType.CUSTOM.value == "custom"
    assert ViewType.IMAGE.value == "image"
    assert ViewType.FILTERED.value == "filtered"


def test_paper_size_enum() -> None:
    assert PaperSize.A4_PORTRAIT.value == "A4_Portrait"
    assert PaperSize.SLIDE_16_9.value == "Slide_16_9"


# ---------------------------------------------------------------------------
# Supporting value object tests
# ---------------------------------------------------------------------------


def test_perspective_defaults() -> None:
    p = Perspective(name="Security")
    assert p.description == ""
    assert p.value == ""
    assert p.url == ""
    assert p.title == ""


def test_perspective_with_title() -> None:
    p = Perspective(name="Security", title="Security View")
    assert p.title == "Security View"


def test_enterprise_name() -> None:
    e = Enterprise(name="Acme Corp")
    assert e.name == "Acme Corp"


def test_http_health_check_defaults() -> None:
    h = HttpHealthCheck(name="ping", url="https://example.com/health")
    assert h.interval == 60
    assert h.timeout == 0
    assert h.headers == {}


def test_automatic_layout_defaults() -> None:
    al = AutomaticLayout()
    assert al.rank_direction == RankDirection.TOP_BOTTOM
    assert al.rank_separation == 100
    assert al.node_separation == 100
    assert al.vertices is False


def test_automatic_layout_custom() -> None:
    al = AutomaticLayout(rank_direction=RankDirection.LEFT_RIGHT, rank_separation=200)
    assert al.rank_direction == RankDirection.LEFT_RIGHT
    assert al.rank_separation == 200


def test_vertex() -> None:
    v = Vertex(x=10, y=20)
    assert v.x == 10
    assert v.y == 20


def test_animation() -> None:
    a = Animation(order=1, element_ids=["a", "b"], relationship_ids=["r1"])
    assert a.order == 1
    assert len(a.element_ids) == 2


# ---------------------------------------------------------------------------
# Relationship tests
# ---------------------------------------------------------------------------


def test_relationship_new_fields() -> None:
    r = Relationship(source_id="a", destination_id="b")
    assert r.id == ""
    assert r.interaction_style == InteractionStyle.SYNCHRONOUS
    assert r.linked_relationship_id == ""
    assert r.url == ""
    assert r.properties == {}
    assert r.perspectives == []


def test_relationship_async() -> None:
    r = Relationship(
        source_id="a",
        destination_id="b",
        interaction_style=InteractionStyle.ASYNCHRONOUS,
    )
    assert r.interaction_style == InteractionStyle.ASYNCHRONOUS


# ---------------------------------------------------------------------------
# Static element field tests
# ---------------------------------------------------------------------------


def test_person_new_fields() -> None:
    p = Person(id="u1", name="Alice")
    assert p.location == Location.UNSPECIFIED
    assert p.url == ""
    assert p.properties == {}
    assert p.perspectives == []
    assert p.group == ""


def test_person_external_location() -> None:
    p = Person(id="u1", name="Alice", location=Location.EXTERNAL)
    assert p.location == Location.EXTERNAL


def test_software_system_new_fields() -> None:
    s = SoftwareSystem(id="s1", name="My System")
    assert s.location == Location.UNSPECIFIED
    assert s.url == ""
    assert s.properties == {}
    assert s.group == ""


def test_container_new_fields() -> None:
    c = Container(id="c1", name="API")
    assert c.url == ""
    assert c.properties == {}
    assert c.perspectives == []
    assert c.group == ""


def test_component_new_fields() -> None:
    comp = Component(id="comp1", name="Controller")
    assert comp.url == ""
    assert comp.properties == {}
    assert comp.group == ""


def test_custom_element() -> None:
    ce = CustomElement(id="ce1", name="My Box", metadata="box")
    assert ce.metadata == "box"
    assert ce.tags == []
    assert ce.group == ""


# ---------------------------------------------------------------------------
# Deployment element tests
# ---------------------------------------------------------------------------


def test_infrastructure_node_defaults() -> None:
    n = InfrastructureNode(id="lb1", name="Load Balancer")
    assert n.technology == ""
    assert n.properties == {}
    assert n.group == ""


def test_software_system_instance_defaults() -> None:
    i = SoftwareSystemInstance(id="ssi1", software_system_id="ss1")
    assert i.instance_id == 1
    assert i.environment == ""
    assert i.health_checks == []
    assert i.deployment_groups == []


def test_container_instance_defaults() -> None:
    i = ContainerInstance(id="ci1", container_id="c1")
    assert i.instance_id == 1
    assert i.health_checks == []


def test_deployment_node_defaults() -> None:
    dn = DeploymentNode(id="dn1", name="AWS")
    assert dn.technology == ""
    assert dn.instances == "1"
    assert dn.environment == ""
    assert dn.children == []
    assert dn.infrastructure_nodes == []
    assert dn.software_system_instances == []
    assert dn.container_instances == []


def test_deployment_node_nesting() -> None:
    child = DeploymentNode(id="child", name="EC2")
    parent = DeploymentNode(id="parent", name="AWS", children=[child])
    assert len(parent.children) == 1
    assert parent.children[0].name == "EC2"


def test_parent_id_defaults_empty() -> None:
    assert Container(id="c1", name="API").parent_id == ""
    assert Component(id="cmp1", name="X").parent_id == ""
    assert DeploymentNode(id="dn1", name="AWS").parent_id == ""
    assert InfrastructureNode(id="i1", name="LB").parent_id == ""


def test_parent_id_can_be_set() -> None:
    c = Container(id="c1", name="API", parent_id="sys1")
    assert c.parent_id == "sys1"
    cmp = Component(id="cmp1", name="X", parent_id="c1")
    assert cmp.parent_id == "c1"
    dn = DeploymentNode(id="dn2", name="EC2", parent_id="dn1")
    assert dn.parent_id == "dn1"
    infra = InfrastructureNode(id="i1", name="LB", parent_id="dn1")
    assert infra.parent_id == "dn1"


# ---------------------------------------------------------------------------
# View model tests
# ---------------------------------------------------------------------------


def test_view_new_fields() -> None:
    v = View(type=ViewType.SYSTEM_CONTEXT, key="ctx")
    assert v.auto_layout is None
    assert v.order == 0
    assert v.properties == {}
    assert v.paper_size is None
    assert v.relationship_views == []
    assert v.animations == []


def test_view_with_auto_layout() -> None:
    v = View(
        type=ViewType.SYSTEM_CONTEXT,
        key="ctx",
        auto_layout=AutomaticLayout(rank_direction=RankDirection.LEFT_RIGHT),
    )
    assert v.auto_layout is not None
    assert v.auto_layout.rank_direction == RankDirection.LEFT_RIGHT


def test_relationship_view_defaults() -> None:
    rv = RelationshipView(id="r1")
    assert rv.description == ""
    assert rv.order == ""
    assert rv.response is None
    assert rv.vertices == []
    assert rv.routing is None


# ---------------------------------------------------------------------------
# Styling model tests
# ---------------------------------------------------------------------------


def test_element_style_defaults() -> None:
    es = ElementStyle(tag="Person")
    assert es.width is None
    assert es.background == ""
    assert es.shape is None
    assert es.opacity is None


def test_relationship_style_defaults() -> None:
    rs = RelationshipStyle(tag="Relationship")
    assert rs.thickness is None
    assert rs.dashed is None
    assert rs.routing is None


def test_styles_empty() -> None:
    s = Styles()
    assert s.element_styles == []
    assert s.relationship_styles == []


def test_terminology_defaults() -> None:
    t = Terminology()
    assert t.enterprise == "Enterprise"
    assert t.person == "Person"
    assert t.software_system == "Software System"
    assert t.container == "Container"
    assert t.component == "Component"
    assert t.code == "Code"
    assert t.deployment_node == "Deployment Node"
    assert t.infrastructure_node == "Infrastructure Node"
    assert t.relationship == "Relationship"


def test_configuration_defaults() -> None:
    c = Configuration()
    assert c.themes == []
    assert c.default_view == ""
    assert c.view_sort_order is None


# ---------------------------------------------------------------------------
# Workspace tests
# ---------------------------------------------------------------------------


def test_workspace_new_fields() -> None:
    ws = Workspace(name="Test")
    assert ws.deployment_nodes == []
    assert ws.deployment_environments == []
    assert ws.enterprise is None
    assert isinstance(ws.configuration, Configuration)


def test_workspace_metadata_defaults() -> None:
    ws = Workspace(name="Test")
    assert ws.id == ""
    assert ws.version == 1
    assert ws.revision == 1
    assert ws.last_modified_date == ""
    assert ws.last_modified_by == ""
    assert ws.created_date == ""
    assert ws.created_by == ""


def test_workspace_metadata_set() -> None:
    ws = Workspace(
        name="Test",
        id="42",
        version=7,
        revision=3,
        last_modified_date="2026-06-21T10:00:00Z",
        last_modified_by="alice",
        created_date="2026-01-01T00:00:00Z",
        created_by="bob",
    )
    assert ws.id == "42"
    assert ws.version == 7
    assert ws.last_modified_by == "alice"
    assert ws.created_by == "bob"


def test_view_element_customization_fields() -> None:
    ve = ViewElement(id="e1", title="Custom", description="d", width=120, height=80)
    assert ve.title == "Custom"
    assert ve.description == "d"
    assert ve.width == 120
    assert ve.height == 80


def test_relationship_view_link_fields() -> None:
    rv = RelationshipView(id="r1", title="Calls", link=True, link_element=2)
    assert rv.title == "Calls"
    assert rv.link is True
    assert rv.link_element == 2


def test_view_control_flag_defaults() -> None:
    v = View(type=ViewType.SYSTEM_CONTEXT, key="k")
    assert v.owner == ""
    assert v.disable_automatic_layout is False
    assert v.hide_element_metadata is False
    assert v.hide_relationship_metadata is False


def test_view_control_flags_set() -> None:
    v = View(
        type=ViewType.SYSTEM_CONTEXT,
        key="k",
        owner="alice",
        disable_automatic_layout=True,
        hide_element_metadata=True,
        hide_relationship_metadata=True,
    )
    assert v.owner == "alice"
    assert v.disable_automatic_layout is True
    assert v.hide_element_metadata is True
    assert v.hide_relationship_metadata is True


def test_deployment_and_infra_icon_default_empty() -> None:
    assert DeploymentNode(id="dn1", name="AWS").icon == ""
    assert InfrastructureNode(id="lb1", name="LB").icon == ""


def test_deployment_and_infra_icon_set() -> None:
    dn = DeploymentNode(id="dn1", name="AWS", icon="aws-logo.png")
    infra = InfrastructureNode(id="lb1", name="LB", icon="nginx.svg")
    assert dn.icon == "aws-logo.png"
    assert infra.icon == "nginx.svg"


def test_workspace_find_element_in_deployment_node() -> None:
    infra = InfrastructureNode(id="lb1", name="LB")
    dn = DeploymentNode(id="dn1", name="AWS", infrastructure_nodes=[infra])
    ws = Workspace(name="W", model=Model(deployment_nodes=[dn]))
    assert ws.find_element("dn1") is dn
    assert ws.find_element("lb1") is infra
    assert ws.find_element("missing") is None


def test_workspace_find_element_nested_deployment() -> None:
    child = DeploymentNode(id="child", name="EC2")
    parent = DeploymentNode(id="parent", name="AWS", children=[child])
    ws = Workspace(name="W", model=Model(deployment_nodes=[parent]))
    assert ws.find_element("child") is child


def test_workspace_enterprise() -> None:
    ws = Workspace(name="W", model=Model(enterprise=Enterprise(name="Acme")))
    assert ws.enterprise is not None
    assert ws.enterprise.name == "Acme"


# ---------------------------------------------------------------------------
# Model and ViewSet (Phase 3 structural refactor)
# ---------------------------------------------------------------------------


def test_model_find_element_walks_hierarchy() -> None:
    comp = Component(id="comp1", name="Ctrl")
    cont = Container(id="c1", name="API", components=[comp])
    sys = SoftwareSystem(id="s1", name="Sys", containers=[cont])
    user = Person(id="u1", name="Alice")
    m = Model(people=[user], software_systems=[sys])
    assert m.find_element("u1") is user
    assert m.find_element("s1") is sys
    assert m.find_element("c1") is cont
    assert m.find_element("comp1") is comp
    assert m.find_element("missing") is None


def test_model_all_relationships_for_filters() -> None:
    r1 = Relationship(source_id="a", destination_id="b")
    r2 = Relationship(source_id="a", destination_id="c")
    m = Model(relationships=[r1, r2])
    assert m.all_relationships_for({"a", "b"}) == [r1]


def test_view_set_append_routes_by_type() -> None:
    vs = ViewSet()
    ctx = View(type=ViewType.SYSTEM_CONTEXT, key="ctx")
    cont = View(type=ViewType.CONTAINER, key="cont")
    deploy = View(type=ViewType.DEPLOYMENT, key="dep")
    vs.append(ctx)
    vs.append(cont)
    vs.append(deploy)
    assert vs.system_context_views == [ctx]
    assert vs.container_views == [cont]
    assert vs.deployment_views == [deploy]


def test_view_set_list_protocol() -> None:
    vs = ViewSet()
    v1 = View(type=ViewType.SYSTEM_CONTEXT, key="a")
    v2 = View(type=ViewType.CONTAINER, key="b")
    vs.append(v1)
    vs.append(v2)
    assert len(vs) == 2
    assert vs[0] is v1
    assert vs[1] is v2
    assert [v.key for v in vs] == ["a", "b"]


def test_workspace_property_delegates_are_live() -> None:
    ws = Workspace(name="W")
    p = Person(id="u1", name="Alice")
    ws.people.append(p)
    assert ws.model.people == [p]
    ws.model.relationships.append(Relationship(source_id="a", destination_id="b"))
    assert len(ws.relationships) == 1


def test_workspace_configuration_setter_writes_to_view_set() -> None:
    ws = Workspace(name="W")
    new_cfg = Configuration(default_view="ctx")
    ws.configuration = new_cfg
    assert ws.views.configuration is new_cfg


# ---------------------------------------------------------------------------
# Phase 4 — complete features
# ---------------------------------------------------------------------------


def test_custom_element_icon_default_and_set() -> None:
    assert CustomElement(id="ce1", name="Box").icon == ""
    ce = CustomElement(id="ce1", name="Box", icon="logo.svg")
    assert ce.icon == "logo.svg"


def test_branding_defaults() -> None:
    b = Branding()
    assert b.font.name == ""
    assert b.font.url == ""
    assert b.logo == ""


def test_configuration_branding_and_exporters() -> None:
    cfg = Configuration()
    assert cfg.branding is None
    assert cfg.generators_and_exporters == {}
    cfg = Configuration(
        branding=Branding(font=Font(name="Inter"), logo="https://x/logo.png"),
        generators_and_exporters={"plantuml": "exporter.PlantUMLExporter"},
    )
    assert cfg.branding is not None
    assert cfg.branding.font.name == "Inter"
    assert cfg.generators_and_exporters["plantuml"] == "exporter.PlantUMLExporter"


def test_documentation_defaults() -> None:
    d = Documentation()
    assert d.sections == []
    assert d.decisions == []
    assert d.images == []


def test_section_and_format_defaults() -> None:
    s = Section(content="# Overview")
    assert s.content == "# Overview"
    assert s.format is Format.MARKDOWN
    assert Format.ASCIIDOC.value == "AsciiDoc"


def test_workspace_documentation_and_decisions() -> None:
    ws = Workspace(name="W")
    assert ws.documentation.sections == []
    assert ws.documentation.decisions == []
    ws = Workspace(
        name="W",
        documentation=Documentation(
            sections=[Section(content="# Overview")],
            decisions=[
                Decision(id="1", title="ADR-001", status="Accepted"),
                Decision(id="2", title="ADR-002", status="Proposed"),
            ],
        ),
    )
    assert ws.documentation.sections[0].content == "# Overview"
    assert [d.title for d in ws.documentation.decisions] == ["ADR-001", "ADR-002"]


def test_element_documentation() -> None:
    sys = SoftwareSystem(id="1", name="S")
    assert sys.documentation.sections == []
    sys.documentation.sections.append(Section(content="details"))
    assert sys.documentation.sections[0].content == "details"


def test_model_custom_elements_and_properties() -> None:
    ce = CustomElement(id="ce1", name="Box")
    m = Model(custom_elements=[ce], properties={"owner": "team-a"})
    assert m.find_element("ce1") is ce
    assert m.properties["owner"] == "team-a"


def test_workspace_validate_clean() -> None:
    ws = Workspace(name="W")
    ws.views.append(View(type=ViewType.SYSTEM_CONTEXT, key="ctx"))
    ws.views.append(View(type=ViewType.CONTAINER, key="cont"))
    assert ws.validate() == []


def test_workspace_validate_duplicate_view_keys() -> None:
    ws = Workspace(name="W")
    ws.views.append(View(type=ViewType.SYSTEM_CONTEXT, key="dup"))
    ws.views.append(View(type=ViewType.CONTAINER, key="dup"))
    issues = ws.validate()
    assert any("dup" in issue for issue in issues)


def test_workspace_validate_empty_view_key() -> None:
    ws = Workspace(name="W")
    ws.views.append(View(type=ViewType.SYSTEM_CONTEXT, key=""))
    issues = ws.validate()
    assert any("empty key" in issue for issue in issues)
