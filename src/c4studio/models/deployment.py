"""Deployment elements: nodes, instances, and infrastructure."""

from __future__ import annotations

from dataclasses import dataclass, field

from c4studio.models.elements import Perspective


@dataclass
class HttpHealthCheck:
    """HTTP health check endpoint on a deployed instance."""

    name: str
    url: str
    interval: int = 60
    timeout: int = 0
    headers: dict[str, str] = field(default_factory=dict)


@dataclass
class InfrastructureNode:
    """An infrastructure node within a deployment node (e.g. load balancer, firewall)."""

    id: str
    name: str
    description: str = ""
    technology: str = ""
    tags: list[str] = field(default_factory=list)
    url: str = ""
    properties: dict[str, str] = field(default_factory=dict)
    perspectives: list[Perspective] = field(default_factory=list)
    group: str = ""
    parent_id: str = ""
    icon: str = ""


@dataclass
class SoftwareSystemInstance:
    """A deployed instance of a SoftwareSystem within a DeploymentNode."""

    id: str
    software_system_id: str
    instance_id: int = 1
    environment: str = ""
    deployment_groups: list[str] = field(default_factory=list)
    health_checks: list[HttpHealthCheck] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    url: str = ""
    properties: dict[str, str] = field(default_factory=dict)
    perspectives: list[Perspective] = field(default_factory=list)


@dataclass
class ContainerInstance:
    """A deployed instance of a Container within a DeploymentNode."""

    id: str
    container_id: str
    instance_id: int = 1
    environment: str = ""
    deployment_groups: list[str] = field(default_factory=list)
    health_checks: list[HttpHealthCheck] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    url: str = ""
    properties: dict[str, str] = field(default_factory=dict)
    perspectives: list[Perspective] = field(default_factory=list)


@dataclass
class DeploymentNode:
    """Hierarchical deployment infrastructure node (e.g. AWS region, Kubernetes cluster, VM)."""

    id: str
    name: str
    description: str = ""
    technology: str = ""
    # A string, not an int: Structurizr allows range expressions such as
    # "0..N" or "1..3" as well as a plain count, and an int silently
    # discarded them.
    instances: str = "1"
    environment: str = ""
    tags: list[str] = field(default_factory=list)
    url: str = ""
    properties: dict[str, str] = field(default_factory=dict)
    perspectives: list[Perspective] = field(default_factory=list)
    group: str = ""
    parent_id: str = ""
    icon: str = ""
    children: list[DeploymentNode] = field(default_factory=list)
    infrastructure_nodes: list[InfrastructureNode] = field(default_factory=list)
    software_system_instances: list[SoftwareSystemInstance] = field(
        default_factory=list
    )
    container_instances: list[ContainerInstance] = field(default_factory=list)
    deployment_groups: list[str] = field(default_factory=list)
