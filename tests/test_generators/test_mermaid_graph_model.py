"""Mermaid output is derived from the shared view graph (PP-88).

The generator used to filter *elements* by view visibility but emit
relationships raw, so a diagram could reference aliases it never declared.
These tests pin the contract that made that impossible: every ``Rel()``
endpoint is an entity the same diagram declares, because both come from
:func:`c4studio.graph.view_graph.build_view_graph`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from c4studio.generators.mermaid import MermaidGenerator
from c4studio.models import Styles, Workspace
from c4studio.parser.dsl import parse_dsl, parse_dsl_file

SAMPLES = Path(__file__).parent.parent.parent / "samples"
FIXTURES = Path(__file__).parent.parent / "fixtures"

# A macro call at the start of a line: `Person(u, "User", "")`, and the
# opening line of a boundary block. Both declare their first argument.
_DECLARATION = re.compile(r"^\s*(\w+)\(([^,)]+)")
_REL = re.compile(r"^\s*Rel\(([^,]+),\s*([^,]+),")


@pytest.fixture(autouse=True)
def _no_remote_themes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the sample sweep offline.

    ``samples/hedge_fund`` references a remote AWS theme, and the graph
    builder resolves themes to style nodes. Mermaid output carries no
    styling, so stubbing the fetch changes nothing being asserted.
    """
    monkeypatch.setattr(
        "c4studio.graph.view_graph.theme_styles", lambda workspace: Styles()
    )


def _declared_aliases(diagram: str) -> set[str]:
    aliases: set[str] = set()
    for line in diagram.splitlines():
        match = _DECLARATION.match(line)
        if match and match.group(1) != "Rel":
            aliases.add(match.group(2).strip())
    return aliases


def _rel_endpoints(diagram: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for line in diagram.splitlines():
        match = _REL.match(line)
        if match:
            pairs.append((match.group(1).strip(), match.group(2).strip()))
    return pairs


def _sample_workspaces() -> list[tuple[str, Workspace]]:
    paths = sorted(SAMPLES.glob("*.dsl")) + [SAMPLES / "hedge_fund" / "workspace.dsl"]
    return [(p.parent.name + "/" + p.name, parse_dsl_file(p)) for p in paths]


class TestNoUndeclaredAliases:
    """The defect PP-88 fixes, asserted across every sample view."""

    @pytest.mark.parametrize("name, workspace", _sample_workspaces())
    def test_every_rel_endpoint_is_declared(
        self, name: str, workspace: Workspace
    ) -> None:
        generator = MermaidGenerator(workspace)
        for view in workspace.views:
            diagram = generator.generate_view(view)
            declared = _declared_aliases(diagram)
            for source, target in _rel_endpoints(diagram):
                assert source in declared, f"{name}:{view.key} source {source}"
                assert target in declared, f"{name}:{view.key} target {target}"

    def test_internet_banking_context_declares_no_containers(self) -> None:
        """The original reproduction: container aliases on a context view."""
        workspace = parse_dsl_file(SAMPLES / "internet_banking.dsl")
        generator = MermaidGenerator(workspace)
        context = next(v for v in workspace.views if v.type.value == "systemContext")
        diagram = generator.generate_view(context)
        assert "Container(" not in diagram
        assert _rel_endpoints(diagram)  # the view does have relationships


CONTEXT_DSL = """
workspace "W" {
    model {
        u = person "User"
        s = softwareSystem "S" {
            web = container "Web"
            api = container "API"
        }
        ext = softwareSystem "External"
        u -> web "Uses"
        u -> api "Also uses"
        api -> ext "Calls"
    }
    views {
        systemContext s "ctx" {
            include *
        }
    }
}
"""


class TestEndpointLifting:
    def test_container_relationships_lift_to_the_parent_system(self) -> None:
        workspace = parse_dsl(CONTEXT_DSL)
        diagram = MermaidGenerator(workspace).generate_view(workspace.views[0])
        # Two person -> container relationships collapse into one edge to the
        # system, and the container aliases never appear.
        assert _rel_endpoints(diagram) == [("u", "s"), ("s", "ext")]
        assert "web" not in _declared_aliases(diagram)

    def test_excluded_relationship_is_omitted(self) -> None:
        workspace = parse_dsl(
            """
            workspace "W" {
                model {
                    u = person "User"
                    s = softwareSystem "S"
                    t = softwareSystem "T"
                    u -> s "Uses"
                    u -> t "Ignores"
                }
                views {
                    systemLandscape "land" {
                        include *
                        exclude u -> t
                    }
                }
            }
            """
        )
        diagram = MermaidGenerator(workspace).generate_view(workspace.views[0])
        assert ("u", "s") in _rel_endpoints(diagram)
        assert ("u", "t") not in _rel_endpoints(diagram)

    def test_implied_relationships_are_not_doubled(self) -> None:
        workspace = parse_dsl(
            """
            workspace "W" {
                !impliedRelationships true
                model {
                    u = person "User"
                    s = softwareSystem "S" {
                        web = container "Web"
                    }
                    u -> web "Uses"
                }
                views {
                    systemContext s "ctx" { include * }
                }
            }
            """
        )
        diagram = MermaidGenerator(workspace).generate_view(workspace.views[0])
        # Lifting u -> web already yields u -> s; the implied relationship
        # must not add a second identical edge.
        assert _rel_endpoints(diagram) == [("u", "s")]


class TestSystemLandscape:
    def test_landscape_renders_with_the_enterprise_boundary(self) -> None:
        workspace = parse_dsl(
            """
            workspace "W" {
                model {
                    enterprise "Acme" {
                        u = person "Staff"
                        s = softwareSystem "S"
                    }
                    partner = softwareSystem "Partner" {
                        tags "External System"
                    }
                    u -> s "Uses"
                    s -> partner "Calls"
                }
                views {
                    systemLandscape "land" { include * }
                }
            }
            """
        )
        diagram = MermaidGenerator(workspace).generate_view(workspace.views[0])
        assert diagram.startswith("C4Context")
        assert "title System Landscape" in diagram
        boundary = diagram.index('Enterprise_Boundary(__enterprise__, "Acme")')
        # Internal elements sit inside the enterprise boundary; the external
        # partner sits outside it.
        assert diagram.index('Person(u, "Staff"', boundary) > boundary
        assert diagram.index("System_Ext(partner") > diagram.index("}", boundary)
        assert ("s", "partner") in _rel_endpoints(diagram)

    def test_landscape_was_previously_unsupported(self) -> None:
        """Regression guard: landscape must not fall back to the comment."""
        workspace = parse_dsl(
            """
            workspace "W" {
                model { s = softwareSystem "S" }
                views { systemLandscape "land" { include * } }
            }
            """
        )
        diagram = MermaidGenerator(workspace).generate_view(workspace.views[0])
        assert "not yet supported" not in diagram


class TestPeerElements:
    def test_peer_container_on_a_component_view_renders_as_external(self) -> None:
        """A component view surfaces peers at the level they were declared.

        The relationship is declared against another system's container, so
        that container is the peer — and being outside the view's boundary it
        renders as ``Container_Ext``. (On a *container* view the same
        relationship surfaces the peer system instead, which is why the
        ``_Ext`` decision follows boundary membership rather than the kind.)
        """
        workspace = parse_dsl(
            """
            workspace "W" {
                model {
                    s = softwareSystem "S" {
                        api = container "API" "The API" "Java" {
                            handler = component "Handler" "Entry point" "Spring MVC"
                        }
                    }
                    t = softwareSystem "T" {
                        gateway = container "Gateway" "Edge" "nginx"
                    }
                    handler -> gateway "Calls"
                }
                views {
                    component api "comp" { include * }
                }
            }
            """
        )
        diagram = MermaidGenerator(workspace).generate_view(workspace.views[0])
        assert 'Component(handler, "Handler", "Spring MVC", "Entry point")' in diagram
        assert 'Container_Ext(gateway, "Gateway", "nginx", "Edge")' in diagram
        assert ("handler", "gateway") in _rel_endpoints(diagram)

    def test_unsupported_view_types_still_comment(self) -> None:
        workspace = parse_dsl_file(SAMPLES / "hedge_fund" / "workspace.dsl")
        generator = MermaidGenerator(workspace)
        for key in ("PlaceOrder", "ProductionDeployment", "InternalOnly"):
            view = next(v for v in workspace.views if v.key == key)
            assert "not yet supported" in generator.generate_view(view)
