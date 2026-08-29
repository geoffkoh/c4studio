"""Tests for the Mermaid ``flowchart`` target (PP-89).

The flowchart target exists because Mermaid's C4 diagram types are
experimental and GitHub pins its own Mermaid version, so these tests pin
both the structure (subgraph nesting, node-before-edge ordering,
determinism) and the conservatism (escaping, no markup beyond ``<br/>``).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from c4studio.generators.flowchart import FlowchartGenerator
from c4studio.models import Styles, View, ViewType, Workspace
from c4studio.parser.dsl import parse_dsl, parse_dsl_file
from c4studio.parser.json_parser import parse_json

SAMPLES = Path(__file__).parent.parent.parent / "samples"

# A node declaration is an id followed by its shape delimiters; a subgraph
# declares its id too. Both make the id referenceable by an edge.
_NODE = re.compile(r"^\s*(\w+)(?:\[|\(|\{)")
_SUBGRAPH = re.compile(r"^\s*subgraph (\w+)\[")
_EDGE = re.compile(r"^\s*(\w+) -->(?:\|\"(.*)\"\|)? (\w+)$")


@pytest.fixture(autouse=True)
def _no_remote_themes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep sample-based tests offline (hedge_fund references a remote theme)."""
    monkeypatch.setattr(
        "c4studio.graph.view_graph.theme_styles", lambda workspace: Styles()
    )


def _declared(diagram: str) -> set[str]:
    ids: set[str] = set()
    for line in diagram.splitlines():
        subgraph = _SUBGRAPH.match(line)
        if subgraph:
            ids.add(subgraph.group(1))
            continue
        node = _NODE.match(line)
        if node and node.group(1) not in ("subgraph", "classDef", "class", "end"):
            ids.add(node.group(1))
    return ids


def _edges(diagram: str) -> list[tuple[str, str, str]]:
    found = []
    for line in diagram.splitlines():
        match = _EDGE.match(line)
        if match:
            found.append((match.group(1), match.group(3), match.group(2) or ""))
    return found


def _view(workspace: Workspace, key: str) -> View:
    return next(v for v in workspace.views if v.key == key)


def _samples() -> list[tuple[str, Workspace]]:
    paths = sorted(SAMPLES.glob("*.dsl")) + [SAMPLES / "hedge_fund" / "workspace.dsl"]
    return [(p.parent.name + "/" + p.name, parse_dsl_file(p)) for p in paths]


WORKSPACE = """
workspace "W" {
    model {
        u = person "User" "Buys things"
        s = softwareSystem "S" "The shop" {
            group "Frontend" {
                web = container "Web" "Storefront" "React"
            }
            api = container "API" "Order handling" "Java"
            db = container "DB" "Order storage" "PostgreSQL" {
                tags "Database"
            }
        }
        ext = softwareSystem "Payments" "Card processing" {
            tags "External System"
        }
        u -> web "Browses" "HTTPS"
        web -> api "Calls"
        api -> db "Reads/writes" "JDBC"
        api -> ext "Charges cards via"
    }
    views {
        systemLandscape "land" {
            include *
            autoLayout lr
        }
        container s "cont" {
            include *
        }
        styles {
            element "Database" {
                shape Cylinder
                background #ff0000
                color #000000
            }
        }
    }
}
"""


class TestStructure:
    def test_front_matter_title_and_direction(self) -> None:
        workspace = parse_dsl(WORKSPACE)
        diagram = FlowchartGenerator(workspace).generate_view(_view(workspace, "land"))
        assert diagram.startswith('---\ntitle: "System Landscape"\n---\n')
        # autoLayout lr on the view, not the default TB.
        assert "flowchart LR" in diagram

    def test_boundary_becomes_a_subgraph_with_nested_groups(self) -> None:
        workspace = parse_dsl(WORKSPACE)
        diagram = FlowchartGenerator(workspace).generate_view(_view(workspace, "cont"))
        lines = diagram.splitlines()
        system = next(
            i for i, x in enumerate(lines) if x.strip().startswith("subgraph s[")
        )
        group = next(i for i, x in enumerate(lines) if "Frontend" in x)
        web = next(i for i, x in enumerate(lines) if x.strip().startswith("web["))
        ends = [i for i, x in enumerate(lines) if x.strip() == "end"]
        # The group subgraph nests inside the system subgraph, and the
        # container inside the group; indentation deepens accordingly.
        assert system < group < web < min(ends)
        assert _indent(lines[system]) < _indent(lines[group]) < _indent(lines[web])
        assert 'subgraph s["S<br/>[Software System]"]' in diagram

    def test_every_node_is_declared_before_the_first_edge(self) -> None:
        """An edge naming an undeclared id creates a node outside its subgraph."""
        workspace = parse_dsl_file(SAMPLES / "hedge_fund" / "workspace.dsl")
        generator = FlowchartGenerator(workspace)
        for view in workspace.views:
            diagram = generator.generate_view(view)
            lines = diagram.splitlines()
            edge_lines = [i for i, x in enumerate(lines) if " --> " in x]
            node_lines = [i for i, x in enumerate(lines) if _NODE.match(x)]
            if not edge_lines or not node_lines:
                continue
            assert max(node_lines) < min(edge_lines), view.key

    def test_filtered_view_inherits_the_base_view_direction(self) -> None:
        """A filtered view holds no layout of its own."""
        workspace = parse_dsl(
            """
            workspace "W" {
                model {
                    u = person "User"
                    s = softwareSystem "S"
                    u -> s "Uses"
                }
                views {
                    systemLandscape "land" {
                        include *
                        autoLayout lr
                    }
                    filtered land exclude "External System" "internal"
                }
            }
            """
        )
        diagram = FlowchartGenerator(workspace).generate_view(
            _view(workspace, "internal")
        )
        assert "flowchart LR" in diagram

    def test_element_label_carries_name_metadata_and_description(self) -> None:
        workspace = parse_dsl(WORKSPACE)
        diagram = FlowchartGenerator(workspace).generate_view(_view(workspace, "cont"))
        assert 'api["API<br/>[Container: Java]<br/>Order handling"]' in diagram
        assert 'u(["User<br/>[Person]<br/>Buys things"])' in diagram

    def test_empty_boundaries_are_dropped(self) -> None:
        """A tag filter can empty a boundary; an empty subgraph renders badly."""
        workspace = parse_dsl(
            """
            workspace "W" {
                model {
                    u = person "User"
                    s = softwareSystem "S" {
                        web = container "Web"
                    }
                    u -> web "Uses"
                }
                views {
                    container s "cont" { include * }
                    filtered cont exclude "Container" "noContainers"
                }
            }
            """
        )
        diagram = FlowchartGenerator(workspace).generate_view(
            _view(workspace, "noContainers")
        )
        assert "subgraph" not in diagram
        assert "end" not in diagram


class TestAllViewTypes:
    @pytest.mark.parametrize("name, workspace", _samples())
    def test_no_view_falls_back_to_the_unsupported_comment(
        self, name: str, workspace: Workspace
    ) -> None:
        generator = FlowchartGenerator(workspace)
        for view in workspace.views:
            diagram = generator.generate_view(view)
            assert "not yet supported" not in diagram, f"{name}:{view.key}"
            assert diagram.startswith("---"), f"{name}:{view.key}"

    @pytest.mark.parametrize("name, workspace", _samples())
    def test_every_edge_endpoint_is_declared(
        self, name: str, workspace: Workspace
    ) -> None:
        """The PP-88 invariant, held for this target too."""
        generator = FlowchartGenerator(workspace)
        for view in workspace.views:
            diagram = generator.generate_view(view)
            declared = _declared(diagram)
            for source, target, _ in _edges(diagram):
                assert source in declared, f"{name}:{view.key} {source}"
                assert target in declared, f"{name}:{view.key} {target}"

    def test_dynamic_view_keeps_step_order(self) -> None:
        workspace = parse_dsl_file(SAMPLES / "hedge_fund" / "workspace.dsl")
        diagram = FlowchartGenerator(workspace).generate_view(
            _view(workspace, "PlaceOrder")
        )
        labels = [label for _, _, label in _edges(diagram)]
        orders = [int(label.split(".")[0]) for label in labels]
        assert orders == sorted(orders)
        assert orders[0] == 1

    def test_deployment_view_nests_deployment_nodes(self) -> None:
        workspace = parse_dsl_file(SAMPLES / "hedge_fund" / "workspace.dsl")
        diagram = FlowchartGenerator(workspace).generate_view(
            _view(workspace, "OmsProduction")
        )
        lines = diagram.splitlines()
        indents = {
            line.strip().split("[")[0].removeprefix("subgraph ").strip(): _indent(line)
            for line in lines
            if line.strip().startswith("subgraph ")
        }
        # AWS region > EKS cluster > namespace, each nested in the previous.
        assert indents["aws_us_east_1"] < indents["eks_cluster"]
        assert indents["eks_cluster"] < indents["oms_namespace"]
        assert "[Deployment Node: Kubernetes 1.31]" in diagram
        # Infrastructure nodes take the hexagon shape.
        assert re.search(r"^\s*alb\{\{", diagram, re.M)

    def test_custom_and_image_views_are_unsupported(self) -> None:
        workspace = parse_dsl(
            """
            workspace "W" {
                model { s = softwareSystem "S" }
                views {
                    image s "img" {
                        image "https://example.com/x.png"
                    }
                }
            }
            """
        )
        view = next(v for v in workspace.views if v.type == ViewType.IMAGE)
        assert "not yet supported" in FlowchartGenerator(workspace).generate_view(view)


class TestReservedIds:
    def test_keyword_aliases_are_suffixed(self) -> None:
        """A bare `end` node id would close the enclosing subgraph."""
        workspace = parse_dsl(
            """
            workspace "W" {
                model {
                    graph = person "Analyst"
                    s = softwareSystem "S" {
                        end = container "Endpoint"
                        style = container "Styling"
                    }
                    graph -> end "Calls"
                }
                views {
                    container s "cont" { include * }
                }
            }
            """
        )
        diagram = FlowchartGenerator(workspace).generate_view(_view(workspace, "cont"))
        assert re.search(r"^\s*end_\[", diagram, re.M)
        assert re.search(r"^\s*style_\[", diagram, re.M)
        # No line may consist of a bare keyword used as a node declaration.
        for line in diagram.splitlines():
            assert not re.match(r"^\s*(end|graph|style|class)[\[\(\{]", line), line
        # Edges use the same mapping, so they still resolve.
        assert ("graph_", "end_", "Calls") in _edges(diagram)


class TestDeterminism:
    @pytest.mark.parametrize("name, workspace", _samples())
    def test_generating_twice_is_byte_identical(
        self, name: str, workspace: Workspace
    ) -> None:
        """Committed diagrams must not churn between runs."""
        first = FlowchartGenerator(workspace).generate_all()
        second = FlowchartGenerator(workspace).generate_all()
        assert first == second

    def test_a_second_generator_instance_matches_the_first(self) -> None:
        """Per-render palette state must not leak between views or instances."""
        workspace = parse_dsl(WORKSPACE)
        generator = FlowchartGenerator(workspace)
        one = generator.generate_view(_view(workspace, "cont"))
        generator.generate_view(_view(workspace, "land"))
        two = generator.generate_view(_view(workspace, "cont"))
        assert one == two


class TestStyling:
    def test_kind_palette_becomes_class_definitions(self) -> None:
        workspace = parse_dsl(WORKSPACE)
        diagram = FlowchartGenerator(workspace).generate_view(_view(workspace, "cont"))
        # Person palette colour, with a darker stroke derived from it.
        assert "classDef c0 fill:#43a047,stroke:#307333,color:#ffffff" in diagram
        assert re.search(r"^\s*class \w+(,\w+)* c0$", diagram, re.M)
        assert "classDef boundary fill:none,stroke:#90a4ae,color:#90a4ae" in diagram

    def test_tag_style_overrides_the_palette_and_the_shape(self) -> None:
        workspace = parse_dsl(WORKSPACE)
        diagram = FlowchartGenerator(workspace).generate_view(_view(workspace, "cont"))
        # The Database element style declares a red background, black text
        # and a cylinder shape.
        assert re.search(r"^\s*db\[\(", diagram, re.M)
        assert "fill:#ff0000,stroke:#b70000,color:#000000" in diagram

    def test_external_elements_take_the_external_palette(self) -> None:
        workspace = parse_dsl(WORKSPACE)
        diagram = FlowchartGenerator(workspace).generate_view(_view(workspace, "land"))
        external = next(
            line for line in diagram.splitlines() if line.strip().startswith("ext[")
        )
        assert "Payments" in external
        assert "fill:#90a4ae" in diagram  # system-external


class TestEscaping:
    def test_hashes_and_angle_brackets_become_entities(self) -> None:
        workspace = parse_dsl(
            """
            workspace "W" {
                model {
                    u = person "User" "Runs #1 <everything>"
                    s = softwareSystem "S"
                    u -> s "Sends 100% <fast>"
                }
                views {
                    systemLandscape "land" { include * }
                }
            }
            """
        )
        diagram = FlowchartGenerator(workspace).generate_view(_view(workspace, "land"))
        assert "#35;1" in diagram
        assert "#lt;everything#gt;" in diagram
        assert "#lt;fast#gt;" in diagram

    def test_quotes_in_names_become_entities(self) -> None:
        """The DSL cannot express an escaped quote, but workspace JSON can."""
        workspace = parse_json(
            json.dumps(
                {
                    "name": "W",
                    "model": {
                        "people": [
                            {"id": "1", "name": 'The "Boss"', "relationships": []}
                        ],
                        "softwareSystems": [{"id": "2", "name": 'S "Prime"'}],
                    },
                    "views": {
                        "systemLandscapeViews": [{"key": "land", "elements": []}]
                    },
                }
            )
        )
        diagram = FlowchartGenerator(workspace).generate_view(_view(workspace, "land"))
        assert "The #quot;Boss#quot;" in diagram
        assert "S #quot;Prime#quot;" in diagram
        # No raw quote may survive inside a label: each node line carries
        # exactly the pair that delimits it.
        for line in diagram.splitlines():
            if _NODE.match(line) and "classDef" not in line:
                assert line.count('"') == 2, line

    def test_labels_use_no_markup_beyond_line_breaks(self) -> None:
        """`<b>`/`<i>` need htmlLabels, which strict renderers disable."""
        workspace = parse_dsl_file(SAMPLES / "hedge_fund" / "workspace.dsl")
        for diagram in FlowchartGenerator(workspace).generate_all().values():
            tags = set(re.findall(r"<[^>]+>", diagram))
            assert tags <= {"<br/>"}


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip())
