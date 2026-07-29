"""Tests for group membership and custom elements (Phase 2 of DSL parity)."""

from pystructurizr.generators.json_export import workspace_to_json
from pystructurizr.parser.dsl import parse_dsl


def test_flat_group_membership() -> None:
    dsl = """
    workspace "W" {
        model {
            group "Internal" {
                u = person "User"
                s = softwareSystem "S"
            }
            e = softwareSystem "External"
        }
    }
    """
    ws = parse_dsl(dsl)
    assert ws.people[0].group == "Internal"
    groups = {s.name: s.group for s in ws.software_systems}
    assert groups == {"S": "Internal", "External": ""}


def test_nested_groups_join_with_separator() -> None:
    dsl = """
    workspace "W" {
        model {
            group "Company" {
                group "Engineering" {
                    s = softwareSystem "S"
                }
            }
        }
    }
    """
    ws = parse_dsl(dsl)
    assert ws.software_systems[0].group == "Company/Engineering"
    assert ws.model.properties.get("structurizr.groupSeparator") == "/"


def test_flat_groups_set_no_separator_property() -> None:
    dsl = """
    workspace "W" {
        model {
            group "Only" {
                s = softwareSystem "S"
            }
        }
    }
    """
    ws = parse_dsl(dsl)
    assert "structurizr.groupSeparator" not in ws.model.properties


def test_group_inside_software_system_body_sets_container_group() -> None:
    dsl = """
    workspace "W" {
        model {
            s = softwareSystem "S" {
                group "Backend" {
                    api = container "API"
                }
                web = container "Web"
            }
        }
    }
    """
    ws = parse_dsl(dsl)
    containers = {c.name: c.group for c in ws.software_systems[0].containers}
    assert containers == {"API": "Backend", "Web": ""}


def test_group_membership_exported_to_json() -> None:
    dsl = """
    workspace "W" {
        model {
            group "Internal" {
                u = person "User"
            }
        }
    }
    """
    ws = parse_dsl(dsl)
    data = workspace_to_json(ws)
    assert data["workspace"]["model"]["people"][0]["group"] == "Internal"


def test_custom_element_positional_args() -> None:
    dsl = """
    workspace "W" {
        model {
            box = element "Box" "metadata kind" "A custom thing" "Tag1,Tag2"
        }
    }
    """
    ws = parse_dsl(dsl)
    assert len(ws.custom_elements) == 1
    ce = ws.custom_elements[0]
    assert ce.id == "box"
    assert ce.name == "Box"
    assert ce.metadata == "metadata kind"
    assert ce.description == "A custom thing"
    assert "Tag1" in ce.tags and "Tag2" in ce.tags


def test_custom_element_body_and_relationships() -> None:
    dsl = """
    workspace "W" {
        model {
            s = softwareSystem "S"
            box = element "Box" {
                description "Overridden"
                url "https://example.com"
                properties {
                    "kind" "queue"
                }
            }
            box -> s "Feeds"
        }
    }
    """
    ws = parse_dsl(dsl)
    ce = ws.custom_elements[0]
    assert ce.description == "Overridden"
    assert ce.url == "https://example.com"
    assert ce.properties == {"kind": "queue"}
    rel = ws.relationships[0]
    assert rel.source_id == ce.id
    assert rel.destination_id == ws.software_systems[0].id


def test_custom_element_in_group() -> None:
    dsl = """
    workspace "W" {
        model {
            group "Infra" {
                box = element "Box"
            }
        }
    }
    """
    ws = parse_dsl(dsl)
    assert ws.custom_elements[0].group == "Infra"


def test_group_context_does_not_cross_parent_boundaries() -> None:
    dsl = """
    workspace "W" {
        model {
            group "Internal" {
                s = softwareSystem "S" {
                    group "Backend" {
                        api = container "API"
                    }
                }
            }
        }
    }
    """
    ws = parse_dsl(dsl)
    system = ws.software_systems[0]
    assert system.group == "Internal"
    # The container's group is scoped to the system, not the outer group.
    assert system.containers[0].group == "Backend"
    assert "structurizr.groupSeparator" not in ws.model.properties
