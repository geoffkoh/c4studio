"""Tests for the unified element body parser (Phase 0 of DSL parity)."""

from pystructurizr.parser.dsl import parse_dsl


def test_person_body_metadata_and_no_leak():
    dsl = """
    workspace "W" {
        model {
            u = person "User" {
                description "The end user"
                tags "VIP" "Customer"
                url "https://example.com/users"
            }
            s = softwareSystem "S"
            u -> s "Uses"
        }
    }
    """
    ws = parse_dsl(dsl)
    assert len(ws.people) == 1
    person = ws.people[0]
    assert person.description == "The end user"
    assert "VIP" in person.tags
    assert "Customer" in person.tags
    assert person.url == "https://example.com/users"
    # Elements after the body must still be parsed at model level.
    assert len(ws.software_systems) == 1
    assert len(ws.relationships) == 1


def test_element_properties_and_perspectives():
    dsl = """
    workspace "W" {
        model {
            s = softwareSystem "S" {
                properties {
                    "owner" "team-a"
                    criticality high
                }
                perspectives {
                    "Security" "TLS everywhere" "A"
                }
            }
        }
    }
    """
    ws = parse_dsl(dsl)
    system = ws.software_systems[0]
    assert system.properties == {"owner": "team-a", "criticality": "high"}
    assert len(system.perspectives) == 1
    perspective = system.perspectives[0]
    assert perspective.name == "Security"
    assert perspective.description == "TLS everywhere"
    assert perspective.value == "A"


def test_comma_separated_tags_line_in_body():
    dsl = """
    workspace "W" {
        model {
            s = softwareSystem "S" {
                tags "Tag One,Tag Two"
            }
        }
    }
    """
    ws = parse_dsl(dsl)
    assert "Tag One" in ws.software_systems[0].tags
    assert "Tag Two" in ws.software_systems[0].tags


def test_component_body_parsed():
    dsl = """
    workspace "W" {
        model {
            s = softwareSystem "S" {
                c = container "API" {
                    comp = component "Handler" {
                        description "Handles requests"
                        technology "FastAPI"
                    }
                }
            }
        }
    }
    """
    ws = parse_dsl(dsl)
    component = ws.software_systems[0].containers[0].components[0]
    assert component.description == "Handles requests"
    assert component.technology == "FastAPI"


def test_infrastructure_node_body_parsed():
    dsl = """
    workspace "W" {
        model {
            deploymentEnvironment "Live" {
                dn = deploymentNode "Server" {
                    lb = infrastructureNode "LB" {
                        description "Load balancer"
                        tags "Networking"
                    }
                }
            }
        }
    }
    """
    ws = parse_dsl(dsl)
    node = ws.deployment_nodes[0]
    assert len(node.infrastructure_nodes) == 1
    infra = node.infrastructure_nodes[0]
    assert infra.description == "Load balancer"
    assert "Networking" in infra.tags


def test_container_instance_body_does_not_leak():
    dsl = """
    workspace "W" {
        model {
            s = softwareSystem "S" {
                web = container "Web"
            }
            deploymentEnvironment "Live" {
                dn = deploymentNode "Server" {
                    containerInstance web {
                        tags "Live Instance"
                    }
                }
            }
        }
    }
    """
    ws = parse_dsl(dsl)
    node = ws.deployment_nodes[0]
    assert len(node.container_instances) == 1
    assert "Live Instance" in node.container_instances[0].tags
    # The body must not have been misparsed into extra deployment nodes.
    assert len(node.children) == 0
    assert len(ws.deployment_nodes) == 1


def test_deployment_node_instance_count_before_body():
    dsl = """
    workspace "W" {
        model {
            deploymentEnvironment "Live" {
                dn = deploymentNode "Server" "desc" "tech" "Tag" 4 {
                    lb = infrastructureNode "LB"
                }
            }
        }
    }
    """
    ws = parse_dsl(dsl)
    node = ws.deployment_nodes[0]
    assert node.instances == "4"
    # The body must attach to the node, not leak to the environment level.
    assert len(node.infrastructure_nodes) == 1
    assert len(ws.deployment_nodes) == 1


def test_group_inside_software_system_body():
    dsl = """
    workspace "W" {
        model {
            s = softwareSystem "S" {
                group "Backend" {
                    api = container "API"
                }
            }
            u = person "User"
            u -> api "Uses"
        }
    }
    """
    ws = parse_dsl(dsl)
    system = ws.software_systems[0]
    assert [c.name for c in system.containers] == ["API"]
    # Elements after the group-bearing system must still parse correctly.
    assert len(ws.people) == 1
    assert len(ws.relationships) == 1


def test_relationship_inside_element_body_still_resolves():
    dsl = """
    workspace "W" {
        model {
            u = person "User"
            s = softwareSystem "S" {
                web = container "Web" {
                    u -> web "Uses"
                }
            }
        }
    }
    """
    ws = parse_dsl(dsl)
    assert len(ws.relationships) == 1
    rel = ws.relationships[0]
    assert rel.source_id == ws.people[0].id
    assert rel.destination_id == ws.software_systems[0].containers[0].id
