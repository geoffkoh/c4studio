"""Tests for group boundaries in Mermaid output (Phase 2 of DSL parity)."""

from pystructurizr.generators.mermaid import MermaidGenerator
from pystructurizr.parser.dsl import parse_dsl


GROUPED_DSL = """
workspace "W" {
    model {
        group "Internal" {
            u = person "User"
            s = softwareSystem "S" {
                group "Backend" {
                    api = container "API"
                }
                web = container "Web"
            }
        }
        ext = softwareSystem "External"
        u -> s "Uses"
    }
    views {
        systemContext s "ctx" {
            include *
        }
        container s "cont" {
            include *
        }
    }
}
"""


def test_system_context_emits_group_boundary() -> None:
    ws = parse_dsl(GROUPED_DSL)
    view = next(v for v in ws.views if v.key == "ctx")
    output = MermaidGenerator(ws).generate_view(view)
    assert 'Boundary(group_Internal, "Internal")' in output
    boundary_start = output.index("Boundary(group_Internal")
    # Grouped elements appear after the boundary opens; ungrouped before it.
    assert output.index("Person(u", boundary_start) > boundary_start
    assert output.index('System(s, "S"', boundary_start) > boundary_start
    assert output.index("System(ext") < boundary_start


def test_container_view_groups_containers_inside_system_boundary() -> None:
    ws = parse_dsl(GROUPED_DSL)
    view = next(v for v in ws.views if v.key == "cont")
    output = MermaidGenerator(ws).generate_view(view)
    system_boundary = output.index("System_Boundary(s")
    group_boundary = output.index('Boundary(group_Backend, "Backend")')
    assert group_boundary > system_boundary
    assert output.index("Container(api", group_boundary) > group_boundary


def test_no_group_boundary_without_groups() -> None:
    ws = parse_dsl(
        """
        workspace "W" {
            model {
                u = person "User"
                s = softwareSystem "S"
                u -> s "Uses"
            }
            views {
                systemContext s "ctx" { include * }
            }
        }
        """
    )
    output = MermaidGenerator(ws).generate_view(ws.views[0])
    assert "Boundary(group_" not in output
