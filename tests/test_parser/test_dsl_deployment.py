"""Tests for deployment completeness (Phase 3 of DSL parity)."""

from pystructurizr.generators.json_export import workspace_to_json
from pystructurizr.parser.dsl import parse_dsl


def _workspace(body: str) -> str:
    return f"""
    workspace "W" {{
        model {{
            s = softwareSystem "S" {{
                web = container "Web"
            }}
            {body}
        }}
    }}
    """


def test_deployment_group_declarations() -> None:
    dsl = _workspace(
        """
        deploymentEnvironment "Live" {
            dg1 = deploymentGroup "Service 1"
            deploymentGroup "Service 2"
            dn = deploymentNode "Server" {
                containerInstance web dg1
            }
        }
        """
    )
    ws = parse_dsl(dsl)
    inst = ws.deployment_nodes[0].container_instances[0]
    assert inst.deployment_groups == ["Service 1"]


def test_instance_quoted_deployment_group_list() -> None:
    dsl = _workspace(
        """
        deploymentEnvironment "Live" {
            dg1 = deploymentGroup "Service 1"
            dg2 = deploymentGroup "Service 2"
            dn = deploymentNode "Server" {
                containerInstance web "dg1,dg2"
            }
        }
        """
    )
    ws = parse_dsl(dsl)
    inst = ws.deployment_nodes[0].container_instances[0]
    assert inst.deployment_groups == ["Service 1", "Service 2"]


def test_instance_unknown_string_arg_becomes_tags() -> None:
    dsl = _workspace(
        """
        deploymentEnvironment "Live" {
            dn = deploymentNode "Server" {
                containerInstance web "Tag One,Tag Two"
            }
        }
        """
    )
    ws = parse_dsl(dsl)
    inst = ws.deployment_nodes[0].container_instances[0]
    assert inst.deployment_groups == []
    assert "Tag One" in inst.tags
    assert "Tag Two" in inst.tags


def test_instance_groups_then_tags() -> None:
    dsl = _workspace(
        """
        deploymentEnvironment "Live" {
            dg1 = deploymentGroup "Service 1"
            dn = deploymentNode "Server" {
                softwareSystemInstance s dg1 "Live Tag"
            }
        }
        """
    )
    ws = parse_dsl(dsl)
    inst = ws.deployment_nodes[0].software_system_instances[0]
    assert inst.software_system_id == "s"
    assert inst.deployment_groups == ["Service 1"]
    assert "Live Tag" in inst.tags


def test_instance_positionals_do_not_swallow_next_line() -> None:
    dsl = _workspace(
        """
        deploymentEnvironment "Live" {
            dn = deploymentNode "Server" {
                containerInstance web
                lb = infrastructureNode "LB"
            }
        }
        """
    )
    ws = parse_dsl(dsl)
    node = ws.deployment_nodes[0]
    assert len(node.container_instances) == 1
    assert len(node.infrastructure_nodes) == 1


def test_health_check_full_and_defaults() -> None:
    dsl = _workspace(
        """
        deploymentEnvironment "Live" {
            dn = deploymentNode "Server" {
                containerInstance web {
                    healthCheck "HTTP" "https://example.com/health" 30 5
                }
                softwareSystemInstance s {
                    healthCheck "Ping" "https://example.com/ping"
                }
            }
        }
        """
    )
    ws = parse_dsl(dsl)
    node = ws.deployment_nodes[0]
    hc = node.container_instances[0].health_checks[0]
    assert hc.name == "HTTP"
    assert hc.url == "https://example.com/health"
    assert hc.interval == 30
    assert hc.timeout == 5
    ping = node.software_system_instances[0].health_checks[0]
    assert ping.name == "Ping"
    assert ping.interval == 60
    assert ping.timeout == 0


def test_instance_body_tags_combine_with_positional() -> None:
    dsl = _workspace(
        """
        deploymentEnvironment "Live" {
            dn = deploymentNode "Server" {
                containerInstance web "Positional" {
                    tags "Nested"
                }
            }
        }
        """
    )
    ws = parse_dsl(dsl)
    inst = ws.deployment_nodes[0].container_instances[0]
    assert "Positional" in inst.tags
    assert "Nested" in inst.tags


def test_instance_metadata_round_trips_to_json() -> None:
    dsl = _workspace(
        """
        deploymentEnvironment "Live" {
            dg1 = deploymentGroup "Service 1"
            dn = deploymentNode "Server" {
                containerInstance web dg1 {
                    healthCheck "HTTP" "https://example.com/health"
                }
            }
        }
        """
    )
    ws = parse_dsl(dsl)
    data = workspace_to_json(ws)
    nodes = data["workspace"]["model"]["deploymentNodes"]
    inst = nodes[0]["containerInstances"][0]
    assert inst["deploymentGroups"] == ["Service 1"]
    assert inst["healthChecks"][0]["url"] == "https://example.com/health"
