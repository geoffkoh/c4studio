"""
Structurizr JSON parser.

Reads the JSON export format produced by the Structurizr tooling and converts
it into the pystructurizr model.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from pystructurizr.models import (
    Animation,
    AutomaticLayout,
    Border,
    Branding,
    ColorScheme,
    Component,
    Configuration,
    Container,
    ContainerInstance,
    CustomElement,
    Decision,
    DecisionLink,
    DeploymentNode,
    Documentation,
    ElementStyle,
    Enterprise,
    Font,
    FilterMode,
    Format,
    HttpHealthCheck,
    IconPosition,
    Image,
    InfrastructureNode,
    LineStyle,
    Location,
    Model,
    Person,
    Perspective,
    Section,
    RankDirection,
    Relationship,
    RelationshipStyle,
    RelationshipView,
    Routing,
    Shape,
    SoftwareSystem,
    SoftwareSystemInstance,
    Styles,
    Terminology,
    User,
    View,
    ViewSet,
    ViewType,
    Workspace,
    WorkspaceConfiguration,
)


def _enum_or_none(enum_cls: Any, value: Any) -> Any:
    """Return the enum member for ``value`` or None when absent/unknown."""
    if not value:
        return None
    try:
        return enum_cls(value)
    except ValueError:
        return None


def _tags(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [t.strip() for t in raw.split(",") if t.strip()]


def _properties(raw: dict[str, Any] | None) -> dict[str, str]:
    if not raw:
        return {}
    return {str(k): str(v) for k, v in raw.items()}


def _perspectives(raw: list[dict[str, Any]] | None) -> list[Perspective]:
    if not raw:
        return []
    return [
        Perspective(
            name=p.get("name", ""),
            description=p.get("description", ""),
            value=p.get("value", ""),
            url=p.get("url", ""),
            title=p.get("title", ""),
        )
        for p in raw
    ]


def _location(tag_list: list[str]) -> Location:
    if "External" in tag_list:
        return Location.EXTERNAL
    if "Internal" in tag_list:
        return Location.INTERNAL
    return Location.UNSPECIFIED


def _parse_person(data: dict[str, Any]) -> Person:
    tag_list = _tags(data.get("tags"))
    return Person(
        id=data["id"],
        name=data.get("name", ""),
        description=data.get("description", ""),
        tags=tag_list,
        location=_location(tag_list),
        url=data.get("url", ""),
        properties=_properties(data.get("properties")),
        perspectives=_perspectives(data.get("perspectives")),
        group=data.get("group", ""),
    )


def _parse_component(data: dict[str, Any], parent_id: str = "") -> Component:
    return Component(
        id=data["id"],
        name=data.get("name", ""),
        description=data.get("description", ""),
        technology=data.get("technology", ""),
        tags=_tags(data.get("tags")),
        url=data.get("url", ""),
        properties=_properties(data.get("properties")),
        perspectives=_perspectives(data.get("perspectives")),
        group=data.get("group", ""),
        parent_id=parent_id,
        documentation=_parse_documentation(data.get("documentation")),
    )


def _parse_container(data: dict[str, Any], parent_id: str = "") -> Container:
    container_id = data["id"]
    components = [
        _parse_component(c, parent_id=container_id) for c in data.get("components", [])
    ]
    return Container(
        id=container_id,
        name=data.get("name", ""),
        description=data.get("description", ""),
        technology=data.get("technology", ""),
        components=components,
        tags=_tags(data.get("tags")),
        url=data.get("url", ""),
        properties=_properties(data.get("properties")),
        perspectives=_perspectives(data.get("perspectives")),
        group=data.get("group", ""),
        parent_id=parent_id,
        documentation=_parse_documentation(data.get("documentation")),
    )


def _parse_software_system(data: dict[str, Any]) -> SoftwareSystem:
    tag_list = _tags(data.get("tags"))
    system_id = data["id"]
    containers = [
        _parse_container(c, parent_id=system_id) for c in data.get("containers", [])
    ]
    return SoftwareSystem(
        id=system_id,
        name=data.get("name", ""),
        description=data.get("description", ""),
        containers=containers,
        tags=tag_list,
        location=_location(tag_list),
        url=data.get("url", ""),
        properties=_properties(data.get("properties")),
        perspectives=_perspectives(data.get("perspectives")),
        group=data.get("group", ""),
        documentation=_parse_documentation(data.get("documentation")),
    )


def _parse_custom_element(data: dict[str, Any]) -> CustomElement:
    return CustomElement(
        id=data["id"],
        name=data.get("name", ""),
        description=data.get("description", ""),
        metadata=data.get("metadata", ""),
        tags=_tags(data.get("tags")),
        url=data.get("url", ""),
        properties=_properties(data.get("properties")),
        perspectives=_perspectives(data.get("perspectives")),
        group=data.get("group", ""),
    )


def _parse_relationship(data: dict[str, Any]) -> Relationship:
    return Relationship(
        id=data.get("id", ""),
        source_id=data["sourceId"],
        destination_id=data["destinationId"],
        description=data.get("description", ""),
        technology=data.get("technology", ""),
        tags=_tags(data.get("tags")),
        url=data.get("url", ""),
        linked_relationship_id=data.get("linkedRelationshipId", ""),
        properties=_properties(data.get("properties")),
        perspectives=_perspectives(data.get("perspectives")),
    )


def _parse_health_checks(raw: list[dict[str, Any]] | None) -> list[HttpHealthCheck]:
    if not raw:
        return []
    return [
        HttpHealthCheck(
            name=h.get("name", ""),
            url=h.get("url", ""),
            interval=int(h.get("interval", 60)),
            timeout=int(h.get("timeout", 0)),
            headers=_properties(h.get("headers")),
        )
        for h in raw
    ]


def _parse_software_system_instance(data: dict[str, Any]) -> SoftwareSystemInstance:
    return SoftwareSystemInstance(
        id=data["id"],
        software_system_id=data.get("softwareSystemId", ""),
        instance_id=int(data.get("instanceId", 1)),
        environment=data.get("environment", ""),
        deployment_groups=data.get("deploymentGroups", []),
        health_checks=_parse_health_checks(data.get("healthChecks")),
        tags=_tags(data.get("tags")),
        url=data.get("url", ""),
        properties=_properties(data.get("properties")),
        perspectives=_perspectives(data.get("perspectives")),
    )


def _parse_container_instance(data: dict[str, Any]) -> ContainerInstance:
    return ContainerInstance(
        id=data["id"],
        container_id=data.get("containerId", ""),
        instance_id=int(data.get("instanceId", 1)),
        environment=data.get("environment", ""),
        deployment_groups=data.get("deploymentGroups", []),
        health_checks=_parse_health_checks(data.get("healthChecks")),
        tags=_tags(data.get("tags")),
        url=data.get("url", ""),
        properties=_properties(data.get("properties")),
        perspectives=_perspectives(data.get("perspectives")),
    )


def _parse_infrastructure_node(
    data: dict[str, Any], parent_id: str = ""
) -> InfrastructureNode:
    return InfrastructureNode(
        id=data["id"],
        name=data.get("name", ""),
        description=data.get("description", ""),
        technology=data.get("technology", ""),
        tags=_tags(data.get("tags")),
        url=data.get("url", ""),
        properties=_properties(data.get("properties")),
        perspectives=_perspectives(data.get("perspectives")),
        group=data.get("group", ""),
        parent_id=parent_id,
        icon=data.get("icon", ""),
    )


def _parse_deployment_node(data: dict[str, Any], parent_id: str = "") -> DeploymentNode:
    node_id = data["id"]
    children = [
        _parse_deployment_node(c, parent_id=node_id) for c in data.get("children", [])
    ]
    infrastructure_nodes = [
        _parse_infrastructure_node(n, parent_id=node_id)
        for n in data.get("infrastructureNodes", [])
    ]
    software_system_instances = [
        _parse_software_system_instance(i)
        for i in data.get("softwareSystemInstances", [])
    ]
    container_instances = [
        _parse_container_instance(i) for i in data.get("containerInstances", [])
    ]
    return DeploymentNode(
        id=node_id,
        name=data.get("name", ""),
        description=data.get("description", ""),
        technology=data.get("technology", ""),
        instances=str(data.get("instances", "1")),
        environment=data.get("environment", ""),
        tags=_tags(data.get("tags")),
        url=data.get("url", ""),
        properties=_properties(data.get("properties")),
        perspectives=_perspectives(data.get("perspectives")),
        group=data.get("group", ""),
        parent_id=parent_id,
        icon=data.get("icon", ""),
        children=children,
        infrastructure_nodes=infrastructure_nodes,
        software_system_instances=software_system_instances,
        container_instances=container_instances,
        deployment_groups=data.get("deploymentGroups", []),
    )


def _parse_auto_layout(data: dict[str, Any] | None) -> AutomaticLayout | None:
    if data is None:
        return None
    _RANK_MAP: dict[str, RankDirection] = {
        "TopBottom": RankDirection.TOP_BOTTOM,
        "BottomTop": RankDirection.BOTTOM_TOP,
        "LeftRight": RankDirection.LEFT_RIGHT,
        "RightLeft": RankDirection.RIGHT_LEFT,
    }
    rank_dir = _RANK_MAP.get(data.get("rankDirection", ""), RankDirection.TOP_BOTTOM)
    return AutomaticLayout(
        rank_direction=rank_dir,
        rank_separation=int(data.get("rankSeparation", 300)),
        node_separation=int(data.get("nodeSeparation", 300)),
        edge_separation=int(data.get("edgeSeparation", 0)),
        vertices=bool(data.get("vertices", False)),
    )


def _parse_relationship_view(data: dict[str, Any]) -> RelationshipView:
    return RelationshipView(
        id=data.get("id", ""),
        description=data.get("description", ""),
        url=data.get("url", ""),
        order=str(data.get("order", "")),
        response=data.get("response"),
        properties=_properties(data.get("properties")),
        title=data.get("title", ""),
        link=data.get("link"),
        link_element=data.get("linkElement"),
    )


def _parse_animation(data: dict[str, Any], order: int) -> Animation:
    return Animation(
        order=order,
        element_ids=data.get("elements", []),
        relationship_ids=data.get("relationships", []),
    )


def _filter_mode(raw: str | None) -> Optional[FilterMode]:
    if raw == FilterMode.INCLUDE.value:
        return FilterMode.INCLUDE
    if raw == FilterMode.EXCLUDE.value:
        return FilterMode.EXCLUDE
    return None


def _parse_view(data: dict[str, Any], view_type: ViewType) -> View:
    included_ids = [e["id"] for e in data.get("elements", [])]
    include_all = "*" in data.get("includes", [])
    relationship_views = [
        _parse_relationship_view(r) for r in data.get("relationships", [])
    ]
    animations = [
        _parse_animation(a, i + 1) for i, a in enumerate(data.get("animations", []))
    ]
    return View(
        type=view_type,
        key=data.get("key", ""),
        element_id=data.get(
            "softwareSystemId", data.get("containerId", data.get("elementId", ""))
        ),
        title=data.get("title", ""),
        description=data.get("description", ""),
        include_all=include_all or bool(included_ids),
        included_ids=included_ids,
        auto_layout=_parse_auto_layout(data.get("automaticLayout")),
        order=int(data.get("order", 0)),
        properties=_properties(data.get("properties")),
        relationship_views=relationship_views,
        animations=animations,
        owner=data.get("owner", ""),
        disable_automatic_layout=bool(data.get("disableAutomaticLayout", False)),
        hide_element_metadata=bool(data.get("hideElementMetadata", False)),
        hide_relationship_metadata=bool(data.get("hideRelationshipMetadata", False)),
        environment=data.get("environment", ""),
        external_boundaries_visible=bool(data.get("externalBoundariesVisible", False)),
        base_view_key=data.get("baseViewKey", ""),
        filter_mode=_filter_mode(data.get("mode")),
        filter_tags=_tags(",".join(data.get("tags", [])))
        if isinstance(data.get("tags"), list)
        else _tags(data.get("tags")),
        content=data.get("content", ""),
        content_light=data.get("contentLight", ""),
        content_dark=data.get("contentDark", ""),
        content_type=data.get("contentType", ""),
    )


def _shape(raw: str | None) -> Optional[Shape]:
    if raw is None:
        return None
    try:
        return Shape(raw)
    except ValueError:
        return None


def _border(raw: str | None) -> Optional[Border]:
    if raw is None:
        return None
    try:
        return Border(raw)
    except ValueError:
        return None


def _parse_element_style(data: dict[str, Any]) -> ElementStyle:
    return ElementStyle(
        tag=data.get("tag", ""),
        background=data.get("background", ""),
        stroke=data.get("stroke", ""),
        color=data.get("color", ""),
        shape=_shape(data.get("shape")),
        border=_border(data.get("border")),
        icon=data.get("icon", ""),
        width=data.get("width"),
        height=data.get("height"),
        stroke_width=data.get("strokeWidth"),
        font_size=data.get("fontSize"),
        opacity=data.get("opacity"),
        metadata=data.get("metadata"),
        description=data.get("description"),
        color_scheme=_enum_or_none(ColorScheme, data.get("colorScheme")),
        icon_position=_enum_or_none(IconPosition, data.get("iconPosition")),
    )


def _parse_relationship_style(data: dict[str, Any]) -> RelationshipStyle:
    return RelationshipStyle(
        tag=data.get("tag", ""),
        color=data.get("color", ""),
        thickness=data.get("thickness"),
        font_size=data.get("fontSize"),
        width=data.get("width"),
        dashed=data.get("dashed"),
        style=_enum_or_none(LineStyle, data.get("style")),
        routing=_enum_or_none(Routing, data.get("routing")),
        jump=data.get("jump"),
        position=data.get("position"),
        opacity=data.get("opacity"),
        metadata=data.get("metadata"),
        description=data.get("description"),
        color_scheme=_enum_or_none(ColorScheme, data.get("colorScheme")),
    )


def _parse_branding(data: dict[str, Any] | None) -> Optional[Branding]:
    if not data:
        return None
    font = data.get("font") or {}
    if isinstance(font, str):  # pre-Font exports stored a bare family name
        font = {"name": font}
    return Branding(
        font=Font(name=font.get("name", ""), url=font.get("url", "")),
        logo=data.get("logo", ""),
    )


def _parse_configuration(data: dict[str, Any] | None) -> Configuration:
    if not data:
        return Configuration()
    styles_data = data.get("styles", {})
    element_styles = [_parse_element_style(s) for s in styles_data.get("elements", [])]
    relationship_styles = [
        _parse_relationship_style(s) for s in styles_data.get("relationships", [])
    ]
    terminology_data = data.get("terminology", {})
    default_terminology = Terminology()
    terminology = Terminology(
        enterprise=terminology_data.get("enterprise", default_terminology.enterprise),
        person=terminology_data.get("person", default_terminology.person),
        software_system=terminology_data.get(
            "softwareSystem", default_terminology.software_system
        ),
        container=terminology_data.get("container", default_terminology.container),
        component=terminology_data.get("component", default_terminology.component),
        code=terminology_data.get("code", default_terminology.code),
        deployment_node=terminology_data.get(
            "deploymentNode", default_terminology.deployment_node
        ),
        infrastructure_node=terminology_data.get(
            "infrastructureNode", default_terminology.infrastructure_node
        ),
        relationship=terminology_data.get(
            "relationship", default_terminology.relationship
        ),
    )
    return Configuration(
        styles=Styles(
            element_styles=element_styles, relationship_styles=relationship_styles
        ),
        themes=data.get("themes", []),
        terminology=terminology,
        default_view=data.get("defaultView", ""),
        last_saved_view=data.get("lastSavedView", ""),
        metadata_symbols=data.get("metadataSymbols", ""),
        properties=_properties(data.get("properties")),
        branding=_parse_branding(data.get("branding")),
        generators_and_exporters=_properties(data.get("generatorsAndExporters")),
    )


def _format(raw: str | None) -> Format:
    if raw == Format.ASCIIDOC.value:
        return Format.ASCIIDOC
    return Format.MARKDOWN


def _parse_documentation(data: dict[str, Any] | None) -> Documentation:
    if not data:
        return Documentation()
    sections = [
        Section(
            content=s.get("content", ""),
            format=_format(s.get("format")),
            title=s.get("title", ""),
            filename=s.get("filename", ""),
            order=int(s.get("order", 0)),
            element_id=str(s.get("elementId", "")),
        )
        for s in data.get("sections", [])
    ]
    decisions = [
        Decision(
            id=str(d.get("id", "")),
            title=d.get("title", ""),
            date=d.get("date", ""),
            status=d.get("status", ""),
            content=d.get("content", ""),
            format=_format(d.get("format")),
            element_id=str(d.get("elementId", "")),
            links=[
                DecisionLink(
                    id=str(link.get("id", "")), description=link.get("description", "")
                )
                for link in d.get("links", [])
            ],
        )
        for d in data.get("decisions", [])
    ]
    images = [
        Image(
            name=img.get("name", ""),
            content=img.get("content", ""),
            type=img.get("type", ""),
        )
        for img in data.get("images", [])
    ]
    return Documentation(sections=sections, decisions=decisions, images=images)


def parse_json(source: str) -> Workspace:
    """Parse a Structurizr JSON string and return a Workspace."""
    data = json.loads(source)
    return _parse_json_dict(data)


def parse_json_file(path: str | Path) -> Workspace:
    """Read a .json file and parse it."""
    return parse_json(Path(path).read_text(encoding="utf-8"))


def _parse_workspace_configuration(
    data: dict[str, Any] | None,
) -> WorkspaceConfiguration:
    if not data:
        return WorkspaceConfiguration()
    return WorkspaceConfiguration(
        scope=data.get("scope", ""),
        visibility=data.get("visibility", ""),
        users=[
            User(username=u.get("username", ""), role=u.get("role", "read"))
            for u in data.get("users", [])
        ],
    )


def _parse_json_dict(data: dict[str, Any]) -> Workspace:
    ws_data = data.get("workspace", data)
    model_data = ws_data.get("model", {})
    views_data = ws_data.get("views", {})

    people = [_parse_person(p) for p in model_data.get("people", [])]
    software_systems = [
        _parse_software_system(s) for s in model_data.get("softwareSystems", [])
    ]
    custom_elements = [
        _parse_custom_element(c) for c in model_data.get("customElements", [])
    ]
    deployment_nodes = [
        _parse_deployment_node(n) for n in model_data.get("deploymentNodes", [])
    ]
    deployment_environments = list(model_data.get("deploymentEnvironments", []))

    relationships: list[Relationship] = []
    for r in model_data.get("relationships", []):
        relationships.append(_parse_relationship(r))
    for person in model_data.get("people", []):
        for r in person.get("relationships", []):
            r["sourceId"] = person["id"]
            relationships.append(_parse_relationship(r))
    for custom in model_data.get("customElements", []):
        for r in custom.get("relationships", []):
            r["sourceId"] = custom["id"]
            relationships.append(_parse_relationship(r))
    for system in model_data.get("softwareSystems", []):
        for r in system.get("relationships", []):
            r["sourceId"] = system["id"]
            relationships.append(_parse_relationship(r))
        for container in system.get("containers", []):
            for r in container.get("relationships", []):
                r["sourceId"] = container["id"]
                relationships.append(_parse_relationship(r))
            for component in container.get("components", []):
                for r in component.get("relationships", []):
                    r["sourceId"] = component["id"]
                    relationships.append(_parse_relationship(r))

    view_set = ViewSet(
        system_landscape_views=[
            _parse_view(v, ViewType.SYSTEM_LANDSCAPE)
            for v in views_data.get("systemLandscapeViews", [])
        ],
        system_context_views=[
            _parse_view(v, ViewType.SYSTEM_CONTEXT)
            for v in views_data.get("systemContextViews", [])
        ],
        container_views=[
            _parse_view(v, ViewType.CONTAINER)
            for v in views_data.get("containerViews", [])
        ],
        component_views=[
            _parse_view(v, ViewType.COMPONENT)
            for v in views_data.get("componentViews", [])
        ],
        dynamic_views=[
            _parse_view(v, ViewType.DYNAMIC) for v in views_data.get("dynamicViews", [])
        ],
        deployment_views=[
            _parse_view(v, ViewType.DEPLOYMENT)
            for v in views_data.get("deploymentViews", [])
        ],
        custom_views=[
            _parse_view(v, ViewType.CUSTOM) for v in views_data.get("customViews", [])
        ],
        image_views=[
            _parse_view(v, ViewType.IMAGE) for v in views_data.get("imageViews", [])
        ],
        filtered_views=[
            _parse_view(v, ViewType.FILTERED)
            for v in views_data.get("filteredViews", [])
        ],
        configuration=_parse_configuration(views_data.get("configuration")),
    )

    enterprise_data = model_data.get("enterprise")
    enterprise = (
        Enterprise(name=enterprise_data.get("name", ""))
        if isinstance(enterprise_data, dict)
        else None
    )

    workspace_model = Model(
        people=people,
        software_systems=software_systems,
        custom_elements=custom_elements,
        relationships=relationships,
        deployment_nodes=deployment_nodes,
        deployment_environments=deployment_environments,
        enterprise=enterprise,
        properties=_properties(model_data.get("properties")),
    )

    return Workspace(
        name=ws_data.get("name", ""),
        description=ws_data.get("description", ""),
        model=workspace_model,
        views=view_set,
        id=str(ws_data.get("id", "")),
        version=int(ws_data.get("version", 1)),
        revision=int(ws_data.get("revision", 1)),
        last_modified_date=ws_data.get("lastModifiedDate", ""),
        last_modified_by=ws_data.get(
            "lastModifiedUser", ws_data.get("lastModifiedBy", "")
        ),
        created_date=ws_data.get("createdDate", ""),
        created_by=ws_data.get("createdUser", ws_data.get("createdBy", "")),
        documentation=_parse_documentation(ws_data.get("documentation")),
        workspace_configuration=_parse_workspace_configuration(
            ws_data.get("configuration")
        ),
    )
