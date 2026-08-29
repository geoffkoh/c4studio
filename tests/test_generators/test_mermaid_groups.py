"""Tests for group boundaries in Mermaid output (Phase 2 of DSL parity)."""

from c4studio.generators.mermaid import MermaidGenerator
from c4studio.parser.dsl import parse_dsl


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
    # Group boundary ids come from the shared view graph, which embeds the
    # parent id so identically named groups under different parents stay
    # distinct; the label is what the diagram shows.
    assert 'Boundary(__group____Internal, "Internal")' in output
    boundary_start = output.index("Boundary(__group____Internal")
    # Grouped elements appear inside the boundary block.
    assert output.index("Person(u", boundary_start) > boundary_start
    assert output.index('System(s, "S"', boundary_start) > boundary_start
    # `ext` has no relationship to the scoped system, so C4 context
    # semantics leave it out of the view entirely.
    assert "System(ext" not in output


def test_container_view_groups_containers_inside_system_boundary() -> None:
    ws = parse_dsl(GROUPED_DSL)
    view = next(v for v in ws.views if v.key == "cont")
    output = MermaidGenerator(ws).generate_view(view)
    system_boundary = output.index("System_Boundary(s")
    group_boundary = output.index('Boundary(__group__s__Backend, "Backend")')
    assert group_boundary > system_boundary
    assert output.index("Container(api", group_boundary) > group_boundary
    # Ungrouped containers stay directly inside the system boundary.
    assert 'Container(web, "Web"' in output


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
