"""Style-driven metadata and description visibility (PP-90).

Structurizr hides an element's metadata line with the ``metadata`` element
style property and its description with ``description``; relationship
styles carry the same pair. All three were parsed and then ignored.

The rule lives in :mod:`c4studio.graph.view_graph` — suppressed text
is blanked there, so every renderer drops it without knowing the rule. The
one exception is the ``[Kind: Technology]`` line, which renderers compose
from the element kind, so the graph also emits ``showMetadata``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from c4studio.generators.flowchart import FlowchartGenerator
from c4studio.generators.mermaid import MermaidGenerator
from c4studio.graph.view_graph import build_view_graph
from c4studio.models import Styles, View, Workspace
from c4studio.parser.dsl import parse_dsl, parse_dsl_file
from c4studio.webapp.graph import react_flow_graph

SAMPLES = Path(__file__).parent.parent.parent / "samples"


def _workspace(styles: str) -> Workspace:
    return parse_dsl(
        f"""
        workspace "W" {{
            model {{
                u = person "User" "A customer"
                s = softwareSystem "S" "The shop" {{
                    api = container "API" "Order handling" "Java" {{
                        tags "Service"
                    }}
                    db = container "DB" "Order storage" "PostgreSQL"
                }}
                u -> api "Places orders with" "HTTPS" {{
                    tags "Sensitive"
                }}
                api -> db "Reads/writes" "JDBC"
            }}
            views {{
                container s "cont" {{
                    include *
                }}
                styles {{
                    {styles}
                }}
            }}
        }}
        """
    )


def _view(workspace: Workspace, key: str = "cont") -> View:
    return next(v for v in workspace.views if v.key == key)


def _node(workspace: Workspace, node_id: str) -> dict[str, object]:
    data = build_view_graph(workspace, _view(workspace))
    node = next(n for n in data["nodes"] if n["id"] == node_id)
    result: dict[str, object] = node["data"]
    return result


def _edge(workspace: Workspace, source: str, target: str) -> dict[str, object]:
    data = build_view_graph(workspace, _view(workspace))
    edge = next(
        e for e in data["edges"] if e["source"] == source and e["target"] == target
    )
    result: dict[str, object] = edge["data"]
    return result


class TestGraphData:
    def test_metadata_false_blanks_technology_and_flags_the_node(self) -> None:
        workspace = _workspace('element "Container" { metadata false }')
        api = _node(workspace, "api")
        assert api["technology"] == ""
        assert api["showMetadata"] is False
        # Description is a separate switch and stays.
        assert api["description"] == "Order handling"

    def test_description_false_blanks_the_description(self) -> None:
        workspace = _workspace('element "Container" { description false }')
        api = _node(workspace, "api")
        assert api["description"] == ""
        assert api["technology"] == "Java"
        assert "showMetadata" not in api

    def test_styles_match_by_tag_so_other_elements_keep_theirs(self) -> None:
        workspace = _workspace('element "Service" { metadata false }')
        assert _node(workspace, "api")["technology"] == ""
        assert _node(workspace, "db")["technology"] == "PostgreSQL"

    def test_later_style_declarations_win(self) -> None:
        workspace = _workspace(
            """
            element "Element" { metadata false }
            element "Container" { metadata true }
            """
        )
        assert "showMetadata" not in _node(workspace, "api")
        # The Person still matched only the first rule.
        assert _node(workspace, "u")["showMetadata"] is False

    def test_relationship_metadata_and_description_are_honoured(self) -> None:
        workspace = _workspace(
            """
            relationship "Sensitive" { description false }
            relationship "Relationship" { metadata false }
            """
        )
        # `Relationship` is implicit on every relationship, so metadata goes
        # everywhere; the description only where the tag matches.
        assert _edge(workspace, "u", "api") == {"label": "", "technology": ""}
        assert _edge(workspace, "api", "db") == {
            "label": "Reads/writes",
            "technology": "",
        }

    def test_unset_properties_change_nothing(self) -> None:
        workspace = _workspace('element "Container" { background #ff0000 }')
        api = _node(workspace, "api")
        assert api["technology"] == "Java"
        assert api["description"] == "Order handling"
        assert "showMetadata" not in api


class TestRenderers:
    def test_flowchart_drops_the_whole_metadata_line(self) -> None:
        workspace = _workspace('element "Container" { metadata false }')
        diagram = FlowchartGenerator(workspace).generate_view(_view(workspace))
        assert 'api["API<br/>Order handling"]' in diagram
        assert "[Container" not in diagram
        # The unstyled person keeps its metadata line.
        assert "[Person]" in diagram

    def test_flowchart_drops_the_description(self) -> None:
        workspace = _workspace('element "Container" { description false }')
        diagram = FlowchartGenerator(workspace).generate_view(_view(workspace))
        assert 'api["API<br/>[Container: Java]"]' in diagram

    def test_flowchart_drops_relationship_technology_and_label(self) -> None:
        workspace = _workspace(
            """
            relationship "Relationship" { metadata false }
            relationship "Sensitive" { description false }
            """
        )
        diagram = FlowchartGenerator(workspace).generate_view(_view(workspace))
        assert "[HTTPS]" not in diagram and "[JDBC]" not in diagram
        assert "u --> api" in diagram  # no label at all
        assert 'api -->|"Reads/writes"| db' in diagram

    def test_c4_target_emits_empty_technology_and_description(self) -> None:
        workspace = _workspace(
            """
            element "Container" { metadata false description false }
            relationship "Relationship" { metadata false }
            """
        )
        diagram = MermaidGenerator(workspace).generate_view(_view(workspace))
        assert 'Container(api, "API", "", "")' in diagram
        assert 'Rel(u, api, "Places orders with")' in diagram

    def test_webapp_graph_carries_the_flag_to_the_frontend(self) -> None:
        """The React node composes the metadata line, so it needs the flag."""
        workspace = _workspace('element "Container" { metadata false }')
        data = react_flow_graph(workspace, _view(workspace))
        api = next(n for n in data["nodes"] if n["id"] == "api")
        assert api["data"]["showMetadata"] is False
        assert api["data"]["technology"] == ""
        person = next(n for n in data["nodes"] if n["id"] == "u")
        assert "showMetadata" not in person["data"]

    def test_dynamic_step_keeps_its_number_without_a_description(self) -> None:
        workspace = parse_dsl(
            """
            workspace "W" {
                model {
                    u = person "User"
                    s = softwareSystem "S"
                    u -> s "Asks for something"
                }
                views {
                    dynamic s "dyn" {
                        u -> s "Asks for something"
                    }
                    styles {
                        relationship "Relationship" { description false }
                    }
                }
            }
            """
        )
        data = build_view_graph(workspace, _view(workspace, "dyn"))
        assert [e["data"]["label"] for e in data["edges"]] == ["1"]


class TestNoRegression:
    @pytest.mark.parametrize(
        "path",
        [
            SAMPLES / "internet_banking.dsl",
            SAMPLES / "saas_monitoring.dsl",
            SAMPLES / "ecommerce_platform.dsl",
            SAMPLES / "hedge_fund" / "workspace.dsl",
        ],
        ids=lambda p: str(p.name),
    )
    def test_samples_still_show_all_metadata(
        self, path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No sample sets these properties, so nothing may be suppressed."""
        monkeypatch.setattr(
            "c4studio.graph.view_graph.theme_styles", lambda workspace: Styles()
        )
        workspace = parse_dsl_file(path)
        for view in workspace.views:
            for node in build_view_graph(workspace, view)["nodes"]:
                assert "showMetadata" not in node["data"], f"{path.name}:{view.key}"
