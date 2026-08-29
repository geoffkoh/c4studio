"""Tests for new DSL parser features: deployment elements, enterprise, autolayout params."""

from c4studio.models import AutomaticLayout, Location, RankDirection, ViewType
from c4studio.parser.dsl import parse_dsl


def test_parse_enterprise() -> None:
    dsl = """
    workspace "W" {
        model {
            enterprise "Acme Corp" {
                u = person "User"
            }
        }
        views { systemContext u "v" { include * } }
    }
    """
    ws = parse_dsl(dsl)
    assert ws.enterprise is not None
    assert ws.enterprise.name == "Acme Corp"
    assert len(ws.people) == 1


def test_parse_external_person_sets_location() -> None:
    dsl = """
    workspace "W" {
        model {
            u = person "External User" "" "External"
        }
        views {}
    }
    """
    ws = parse_dsl(dsl)
    assert ws.people[0].location == Location.EXTERNAL


def test_parse_autolayout_default_direction() -> None:
    dsl = """
    workspace "W" {
        model { s = softwareSystem "S" }
        views {
            systemContext s "v" {
                include *
                autolayout
            }
        }
    }
    """
    ws = parse_dsl(dsl)
    view = ws.views[0]
    assert isinstance(view.auto_layout, AutomaticLayout)
    assert view.auto_layout.rank_direction == RankDirection.TOP_BOTTOM


def test_parse_autolayout_lr_direction() -> None:
    dsl = """
    workspace "W" {
        model { s = softwareSystem "S" }
        views {
            systemContext s "v" {
                include *
                autolayout lr
            }
        }
    }
    """
    ws = parse_dsl(dsl)
    assert ws.views[0].auto_layout is not None
    assert ws.views[0].auto_layout.rank_direction == RankDirection.LEFT_RIGHT


def test_parse_system_landscape_view() -> None:
    dsl = """
    workspace "W" {
        model {
            u = person "User"
            s = softwareSystem "System"
        }
        views {
            systemLandscape "landscape" {
                include *
            }
        }
    }
    """
    ws = parse_dsl(dsl)
    assert len(ws.views) == 1
    assert ws.views[0].type == ViewType.SYSTEM_LANDSCAPE


def test_parse_deployment_node() -> None:
    dsl = """
    workspace "W" {
        model {
            s = softwareSystem "System" {
                webapp = container "Web App"
            }
            deploymentEnvironment "Live" {
                dn = deploymentNode "AWS" "" "Amazon Web Services" {
                    ec2 = deploymentNode "EC2" {
                        containerInstance webapp
                    }
                }
            }
        }
        views {}
    }
    """
    ws = parse_dsl(dsl)
    assert len(ws.deployment_nodes) == 1
    aws = ws.deployment_nodes[0]
    assert aws.name == "AWS"
    assert aws.technology == "Amazon Web Services"
    assert len(aws.children) == 1
    ec2 = aws.children[0]
    assert ec2.name == "EC2"
    assert len(ec2.container_instances) == 1


def test_parse_infrastructure_node() -> None:
    dsl = """
    workspace "W" {
        model {
            deploymentEnvironment "Live" {
                dn = deploymentNode "AWS" {
                    lb = infrastructureNode "Load Balancer" "" "nginx"
                }
            }
        }
        views {}
    }
    """
    ws = parse_dsl(dsl)
    aws = ws.deployment_nodes[0]
    assert len(aws.infrastructure_nodes) == 1
    assert aws.infrastructure_nodes[0].name == "Load Balancer"
    assert aws.infrastructure_nodes[0].technology == "nginx"


def test_dsl_container_and_component_parent_id() -> None:
    dsl = """
    workspace "W" {
        model {
            s = softwareSystem "System" {
                api = container "API" {
                    ctrl = component "Controller"
                }
            }
        }
        views {}
    }
    """
    ws = parse_dsl(dsl)
    api = ws.software_systems[0].containers[0]
    assert api.parent_id == ws.software_systems[0].id
    assert api.components[0].parent_id == api.id


def test_dsl_deployment_and_infra_parent_id() -> None:
    dsl = """
    workspace "W" {
        model {
            deploymentEnvironment "Live" {
                dn = deploymentNode "AWS" {
                    lb = infrastructureNode "LB"
                    ec2 = deploymentNode "EC2"
                }
            }
        }
        views {}
    }
    """
    ws = parse_dsl(dsl)
    aws = ws.deployment_nodes[0]
    assert aws.parent_id == ""
    assert aws.infrastructure_nodes[0].parent_id == aws.id
    assert aws.children[0].parent_id == aws.id


def test_deployment_node_find_element() -> None:
    dsl = """
    workspace "W" {
        model {
            deploymentEnvironment "Live" {
                dn = deploymentNode "AWS" {
                    lb = infrastructureNode "Load Balancer"
                }
            }
        }
        views {}
    }
    """
    ws = parse_dsl(dsl)
    dn = ws.find_element("dn")
    lb = ws.find_element("lb")
    assert dn is not None
    assert lb is not None
