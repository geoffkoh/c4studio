"""Structurizr workspace JSON exporter.

Serialises a :class:`~pystructurizr.models.Workspace` back into the JSON
format produced by the Structurizr tooling, so models authored in DSL (or
edited programmatically) round-trip with structurizr.com, Structurizr
Lite, and this package's own :mod:`~pystructurizr.parser.json_parser`.

Conventions mirror the official exports:

- Relationships are nested under their source element; only relationships
  whose source is not a static-structure element fall back to a top-level
  ``model.relationships`` array (an extension the JSON parser reads).
- ``tags`` are comma-joined strings, and an element's ``location`` is
  carried as an ``Internal``/``External`` tag, which is how the parser
  derives it back.
- Views scoped with ``include *`` and no materialised element list export
  ``"includes": ["*"]`` rather than a computed element list.
- Empty strings, empty collections, and ``None`` are omitted throughout.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pystructurizr.models import (
    Animation,
    AutomaticLayout,
    Component,
    Configuration,
    Container,
    ContainerInstance,
    CustomElement,
    DeploymentNode,
    Documentation,
    ElementStyle,
    HttpHealthCheck,
    InfrastructureNode,
    Location,
    Person,
    Perspective,
    Relationship,
    RelationshipStyle,
    RelationshipView,
    SoftwareSystem,
    SoftwareSystemInstance,
    Font,
    Terminology,
    View,
    ViewType,
    Workspace,
    WorkspaceConfiguration,
)

JsonDict = dict[str, Any]


def _clean(data: JsonDict) -> JsonDict:
    """Drop keys whose values are empty strings, collections, or None."""
    return {
        key: value
        for key, value in data.items()
        if value is not None and value != "" and value != [] and value != {}
    }


def _tags(tags: list[str], location: Location = Location.UNSPECIFIED) -> str:
    """Comma-join tags, appending the location tag the parser derives from."""
    merged = list(tags)
    if location != Location.UNSPECIFIED and location.value not in merged:
        merged.append(location.value)
    return ",".join(merged)


def _perspectives(perspectives: list[Perspective]) -> list[JsonDict]:
    return [
        _clean(
            {
                "name": p.name,
                "description": p.description,
                "value": p.value,
                "url": p.url,
                "title": p.title,
            }
        )
        for p in perspectives
    ]


def _relationship(relationship: Relationship, nested: bool) -> JsonDict:
    data = _clean(
        {
            "id": relationship.id,
            "sourceId": relationship.source_id,
            "destinationId": relationship.destination_id,
            "description": relationship.description,
            "technology": relationship.technology,
            "linkedRelationshipId": relationship.linked_relationship_id,
            "tags": _tags(relationship.tags),
            "url": relationship.url,
            "properties": dict(relationship.properties),
            "perspectives": _perspectives(relationship.perspectives),
        }
    )
    if nested:
        data.pop("sourceId", None)
    return data


class _RelationshipIndex:
    """Relationships grouped by source id, consumed as elements are emitted."""

    def __init__(self, relationships: list[Relationship]) -> None:
        self._by_source: dict[str, list[Relationship]] = {}
        for relationship in relationships:
            self._by_source.setdefault(relationship.source_id, []).append(relationship)

    def take(self, source_id: str) -> list[JsonDict]:
        return [
            _relationship(r, nested=True) for r in self._by_source.pop(source_id, [])
        ]

    def remaining(self) -> list[JsonDict]:
        return [
            _relationship(r, nested=False)
            for group in self._by_source.values()
            for r in group
        ]


def _documentation(documentation: Documentation) -> JsonDict:
    return _clean(
        {
            "sections": [
                _clean(
                    {
                        "content": s.content,
                        "format": s.format.value,
                        "title": s.title,
                        "filename": s.filename,
                        "order": s.order or None,
                        "elementId": s.element_id,
                    }
                )
                for s in documentation.sections
            ],
            "decisions": [
                _clean(
                    {
                        "id": d.id,
                        "title": d.title,
                        "date": d.date,
                        "status": d.status,
                        "content": d.content,
                        "format": d.format.value,
                        "elementId": d.element_id,
                        "links": [
                            _clean({"id": link.id, "description": link.description})
                            for link in d.links
                        ],
                    }
                )
                for d in documentation.decisions
            ],
            "images": [
                _clean({"name": i.name, "content": i.content, "type": i.type})
                for i in documentation.images
            ],
        }
    )


def _person(person: Person, index: _RelationshipIndex) -> JsonDict:
    return _clean(
        {
            "id": person.id,
            "name": person.name,
            "description": person.description,
            "tags": _tags(person.tags, person.location),
            "url": person.url,
            "properties": dict(person.properties),
            "perspectives": _perspectives(person.perspectives),
            "group": person.group,
            "relationships": index.take(person.id),
        }
    )


def _component(component: Component, index: _RelationshipIndex) -> JsonDict:
    return _clean(
        {
            "id": component.id,
            "name": component.name,
            "description": component.description,
            "technology": component.technology,
            "tags": _tags(component.tags),
            "url": component.url,
            "properties": dict(component.properties),
            "perspectives": _perspectives(component.perspectives),
            "group": component.group,
            "documentation": _documentation(component.documentation),
            "relationships": index.take(component.id),
        }
    )


def _container(container: Container, index: _RelationshipIndex) -> JsonDict:
    return _clean(
        {
            "id": container.id,
            "name": container.name,
            "description": container.description,
            "technology": container.technology,
            "tags": _tags(container.tags),
            "url": container.url,
            "properties": dict(container.properties),
            "perspectives": _perspectives(container.perspectives),
            "group": container.group,
            "documentation": _documentation(container.documentation),
            "components": [_component(c, index) for c in container.components],
            "relationships": index.take(container.id),
        }
    )


def _software_system(system: SoftwareSystem, index: _RelationshipIndex) -> JsonDict:
    return _clean(
        {
            "id": system.id,
            "name": system.name,
            "description": system.description,
            "tags": _tags(system.tags, system.location),
            "url": system.url,
            "properties": dict(system.properties),
            "perspectives": _perspectives(system.perspectives),
            "group": system.group,
            "documentation": _documentation(system.documentation),
            "containers": [_container(c, index) for c in system.containers],
            "relationships": index.take(system.id),
        }
    )


def _custom_element(element: CustomElement, index: _RelationshipIndex) -> JsonDict:
    return _clean(
        {
            "id": element.id,
            "name": element.name,
            "description": element.description,
            "metadata": element.metadata,
            "tags": _tags(element.tags),
            "url": element.url,
            "properties": dict(element.properties),
            "perspectives": _perspectives(element.perspectives),
            "group": element.group,
            "relationships": index.take(element.id),
        }
    )


def _health_checks(checks: list[HttpHealthCheck]) -> list[JsonDict]:
    return [
        _clean(
            {
                "name": h.name,
                "url": h.url,
                "interval": h.interval,
                "timeout": h.timeout or None,
                "headers": dict(h.headers),
            }
        )
        for h in checks
    ]


def _software_system_instance(instance: SoftwareSystemInstance) -> JsonDict:
    return _clean(
        {
            "id": instance.id,
            "softwareSystemId": instance.software_system_id,
            "instanceId": instance.instance_id,
            "environment": instance.environment,
            "deploymentGroups": list(instance.deployment_groups),
            "healthChecks": _health_checks(instance.health_checks),
            "tags": _tags(instance.tags),
            "url": instance.url,
            "properties": dict(instance.properties),
            "perspectives": _perspectives(instance.perspectives),
        }
    )


def _container_instance(instance: ContainerInstance) -> JsonDict:
    return _clean(
        {
            "id": instance.id,
            "containerId": instance.container_id,
            "instanceId": instance.instance_id,
            "environment": instance.environment,
            "deploymentGroups": list(instance.deployment_groups),
            "healthChecks": _health_checks(instance.health_checks),
            "tags": _tags(instance.tags),
            "url": instance.url,
            "properties": dict(instance.properties),
            "perspectives": _perspectives(instance.perspectives),
        }
    )


def _infrastructure_node(node: InfrastructureNode) -> JsonDict:
    return _clean(
        {
            "id": node.id,
            "name": node.name,
            "description": node.description,
            "technology": node.technology,
            "tags": _tags(node.tags),
            "url": node.url,
            "properties": dict(node.properties),
            "perspectives": _perspectives(node.perspectives),
            "group": node.group,
            "icon": node.icon,
        }
    )


def _deployment_node(node: DeploymentNode) -> JsonDict:
    return _clean(
        {
            "id": node.id,
            "name": node.name,
            "description": node.description,
            "technology": node.technology,
            "instances": node.instances if node.instances != "1" else None,
            "environment": node.environment,
            "tags": _tags(node.tags),
            "url": node.url,
            "properties": dict(node.properties),
            "perspectives": _perspectives(node.perspectives),
            "group": node.group,
            "icon": node.icon,
            "children": [_deployment_node(c) for c in node.children],
            "infrastructureNodes": [
                _infrastructure_node(n) for n in node.infrastructure_nodes
            ],
            "softwareSystemInstances": [
                _software_system_instance(i) for i in node.software_system_instances
            ],
            "containerInstances": [
                _container_instance(i) for i in node.container_instances
            ],
            "deploymentGroups": list(node.deployment_groups),
        }
    )


def _auto_layout(layout: AutomaticLayout) -> JsonDict:
    return _clean(
        {
            "rankDirection": layout.rank_direction.value,
            "rankSeparation": layout.rank_separation,
            "nodeSeparation": layout.node_separation,
            "edgeSeparation": layout.edge_separation or None,
            "vertices": layout.vertices or None,
        }
    )


def _relationship_view(view: RelationshipView) -> JsonDict:
    return _clean(
        {
            "id": view.id,
            "description": view.description,
            "url": view.url,
            "order": view.order,
            "response": view.response,
            "properties": dict(view.properties),
            "title": view.title,
            "link": view.link,
            "linkElement": view.link_element,
        }
    )


def _animation(animation: Animation) -> JsonDict:
    return _clean(
        {
            "elements": list(animation.element_ids),
            "relationships": list(animation.relationship_ids),
        }
    )


# The JSON key that carries each view type's scope element.
_SCOPE_KEYS: dict[ViewType, str] = {
    ViewType.SYSTEM_CONTEXT: "softwareSystemId",
    ViewType.CONTAINER: "softwareSystemId",
    ViewType.COMPONENT: "containerId",
}


def _view(view: View) -> JsonDict:
    elements: list[JsonDict] = []
    if view.element_views:
        elements = [
            _clean({"id": e.id, "x": e.x, "y": e.y}) for e in view.element_views
        ]
    elif view.included_ids:
        elements = [{"id": element_id} for element_id in view.included_ids]

    data = _clean(
        {
            "key": view.key,
            "title": view.title,
            "description": view.description,
            "elements": elements,
            "relationships": [_relationship_view(r) for r in view.relationship_views],
            "animations": [_animation(a) for a in view.animations],
            "automaticLayout": (
                _auto_layout(view.auto_layout) if view.auto_layout else None
            ),
            "order": view.order or None,
            "properties": dict(view.properties),
            "owner": view.owner,
            "environment": view.environment,
            "externalBoundariesVisible": view.external_boundaries_visible or None,
            "baseViewKey": view.base_view_key,
            "mode": view.filter_mode.value if view.filter_mode else None,
            "tags": list(view.filter_tags),
            "content": view.content,
            "contentLight": view.content_light,
            "contentDark": view.content_dark,
            "contentType": view.content_type,
        }
    )
    if view.element_id:
        data[_SCOPE_KEYS.get(view.type, "elementId")] = view.element_id
    if view.include_all and not elements:
        data["includes"] = ["*"]
    return data


def _element_style(style: ElementStyle) -> JsonDict:
    return _clean(
        {
            "tag": style.tag,
            "width": style.width,
            "height": style.height,
            "background": style.background,
            "stroke": style.stroke,
            "strokeWidth": style.stroke_width,
            "color": style.color,
            "fontSize": style.font_size,
            "shape": style.shape.value if style.shape else None,
            "icon": style.icon,
            "border": style.border.value if style.border else None,
            "opacity": style.opacity,
            "metadata": style.metadata,
            "description": style.description,
            "colorScheme": style.color_scheme.value if style.color_scheme else None,
            "iconPosition": style.icon_position.value if style.icon_position else None,
        }
    )


def _relationship_style(style: RelationshipStyle) -> JsonDict:
    return _clean(
        {
            "tag": style.tag,
            "thickness": style.thickness,
            "color": style.color,
            "fontSize": style.font_size,
            "width": style.width,
            "dashed": style.dashed,
            "style": style.style.value if style.style else None,
            "routing": style.routing.value if style.routing else None,
            "jump": style.jump,
            "position": style.position,
            "opacity": style.opacity,
            "metadata": style.metadata,
            "description": style.description,
            "colorScheme": style.color_scheme.value if style.color_scheme else None,
        }
    )


def _font(font: Font) -> JsonDict | None:
    """Serialise a branding font, or ``None`` when nothing was set."""
    if not font.name and not font.url:
        return None
    return {"name": font.name, **({"url": font.url} if font.url else {})}


def _terminology(terminology: Terminology) -> JsonDict:
    """Serialise only the labels that differ from the defaults."""
    defaults = Terminology()
    labels = {
        "enterprise": (terminology.enterprise, defaults.enterprise),
        "person": (terminology.person, defaults.person),
        "softwareSystem": (terminology.software_system, defaults.software_system),
        "container": (terminology.container, defaults.container),
        "component": (terminology.component, defaults.component),
        "code": (terminology.code, defaults.code),
        "deploymentNode": (terminology.deployment_node, defaults.deployment_node),
        "infrastructureNode": (
            terminology.infrastructure_node,
            defaults.infrastructure_node,
        ),
        "relationship": (terminology.relationship, defaults.relationship),
    }
    return _clean(
        {
            key: (value if value != default else None)
            for key, (value, default) in labels.items()
        }
    )


def _workspace_configuration(configuration: WorkspaceConfiguration) -> JsonDict:
    return _clean(
        {
            "scope": configuration.scope,
            "visibility": configuration.visibility,
            "users": [
                {"username": user.username, "role": user.role}
                for user in configuration.users
            ],
        }
    )


def _configuration(configuration: Configuration) -> JsonDict:
    return _clean(
        {
            "styles": _clean(
                {
                    "elements": [
                        _element_style(s) for s in configuration.styles.element_styles
                    ],
                    "relationships": [
                        _relationship_style(s)
                        for s in configuration.styles.relationship_styles
                    ],
                }
            ),
            "themes": list(configuration.themes),
            "terminology": _terminology(configuration.terminology),
            "defaultView": configuration.default_view,
            "lastSavedView": configuration.last_saved_view,
            "metadataSymbols": configuration.metadata_symbols,
            "properties": dict(configuration.properties),
            "branding": (
                _clean(
                    {
                        "font": _font(configuration.branding.font),
                        "logo": configuration.branding.logo,
                    }
                )
                if configuration.branding
                else None
            ),
            "generatorsAndExporters": dict(configuration.generators_and_exporters),
        }
    )


def workspace_to_json(workspace: Workspace) -> JsonDict:
    """Convert a workspace into a Structurizr-JSON-shaped dict.

    Args:
        workspace: The workspace to serialise.

    Returns:
        A dict with a single ``workspace`` key, matching the envelope this
        package's JSON parser and the Structurizr exports use.
    """
    index = _RelationshipIndex(workspace.relationships)

    model = _clean(
        {
            "people": [_person(p, index) for p in workspace.people],
            "softwareSystems": [
                _software_system(s, index) for s in workspace.software_systems
            ],
            "customElements": [
                _custom_element(c, index) for c in workspace.custom_elements
            ],
            "deploymentNodes": [
                _deployment_node(n) for n in workspace.deployment_nodes
            ],
            "deploymentEnvironments": list(workspace.deployment_environments),
            "enterprise": (
                {"name": workspace.enterprise.name} if workspace.enterprise else None
            ),
            "properties": dict(workspace.model.properties),
            # Sources that are not static-structure elements (e.g. deployment
            # elements) cannot nest; the parser reads this array back.
            "relationships": index.remaining(),
        }
    )

    view_groups: dict[str, list[View]] = {
        "systemLandscapeViews": workspace.views.system_landscape_views,
        "systemContextViews": workspace.views.system_context_views,
        "containerViews": workspace.views.container_views,
        "componentViews": workspace.views.component_views,
        "dynamicViews": workspace.views.dynamic_views,
        "deploymentViews": workspace.views.deployment_views,
        "customViews": workspace.views.custom_views,
        "imageViews": workspace.views.image_views,
        "filteredViews": workspace.views.filtered_views,
    }
    views = _clean(
        {key: [_view(v) for v in group] for key, group in view_groups.items()}
    )
    configuration = _configuration(workspace.views.configuration)
    if configuration:
        views["configuration"] = configuration

    return {
        "workspace": _clean(
            {
                "id": workspace.id,
                "name": workspace.name,
                "description": workspace.description,
                "version": workspace.version if workspace.version != 1 else None,
                "revision": workspace.revision if workspace.revision != 1 else None,
                "lastModifiedDate": workspace.last_modified_date,
                "lastModifiedUser": workspace.last_modified_by,
                "createdDate": workspace.created_date,
                "createdUser": workspace.created_by,
                "model": model,
                "views": views,
                "configuration": _workspace_configuration(
                    workspace.workspace_configuration
                ),
                "documentation": _documentation(workspace.documentation),
            }
        )
    }


def export_json(workspace: Workspace, indent: int = 2) -> str:
    """Serialise a workspace to a Structurizr JSON string.

    Args:
        workspace: The workspace to serialise.
        indent: Pretty-print indentation; keeps exports diff-friendly.

    Returns:
        The JSON document, ending with a newline.
    """
    return json.dumps(workspace_to_json(workspace), indent=indent) + "\n"


def export_json_file(workspace: Workspace, path: str | Path) -> None:
    """Write a workspace to ``path`` as Structurizr JSON."""
    Path(path).write_text(export_json(workspace), encoding="utf-8")
