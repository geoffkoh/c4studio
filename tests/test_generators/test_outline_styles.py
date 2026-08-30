"""Outline element-style properties reach the renderers (PP-107).

``border``, ``stroke``, ``strokeWidth`` and ``opacity`` parsed into
:class:`ElementStyle` and were then dropped by
:func:`c4studio.graph.view_graph.build_view_graph`, so they never reached a
renderer. The legend still reacted to the tag, which made it worse than a
plain gap: ``element "Deprecated" { border dashed }`` produced a legend row
whose swatch was indistinguishable from the default one, asserting a
distinction the diagram did not draw.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from c4studio.graph.view_graph import build_view_graph
from c4studio.models import View, Workspace
from c4studio.parser.dsl import parse_dsl
from c4studio.webapp.graph import react_flow_graph

SAMPLES = Path(__file__).parent.parent.parent / "samples"


def _workspace(styles: str) -> Workspace:
    return parse_dsl(
        f"""
        workspace "W" {{
            model {{
                s = softwareSystem "S" {{
                    api = container "API" "Existing" "Java"
                    new = container "Fraud" "Added" "Go" {{
                        tags "New"
                    }}
                }}
                api -> new "Screens via"
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


def _view(workspace: Workspace) -> View:
    return next(v for v in workspace.views if v.key == "cont")


def _node(workspace: Workspace, node_id: str) -> dict[str, object]:
    data = build_view_graph(workspace, _view(workspace))
    node = next(n for n in data["nodes"] if n["id"] == node_id)
    result: dict[str, object] = node["data"]
    return result


def _legend(workspace: Workspace) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = build_view_graph(workspace, _view(workspace))[
        "legend"
    ]
    return entries


class TestGraphData:
    @pytest.mark.parametrize(
        "keyword, expected",
        [("dashed", "Dashed"), ("dotted", "Dotted"), ("solid", "Solid")],
    )
    def test_border_reaches_the_node(self, keyword: str, expected: str) -> None:
        workspace = _workspace(f'element "New" {{ border {keyword} }}')
        assert _node(workspace, "new")["border"] == expected

    def test_stroke_and_width_reach_the_node(self) -> None:
        workspace = _workspace('element "New" { stroke #ff0000 strokeWidth 4 }')
        new = _node(workspace, "new")
        assert new["stroke"] == "#ff0000"
        assert new["strokeWidth"] == 4

    def test_opacity_reaches_the_node(self) -> None:
        workspace = _workspace('element "New" { opacity 40 }')
        assert _node(workspace, "new")["opacity"] == 40

    def test_untagged_elements_are_untouched(self) -> None:
        workspace = _workspace('element "New" { border dashed opacity 40 }')
        api = _node(workspace, "api")
        assert "border" not in api
        assert "opacity" not in api

    def test_unset_properties_add_nothing(self) -> None:
        """A style that sets only a background must not invent an outline."""
        workspace = _workspace('element "New" { background #2e7d32 }')
        new = _node(workspace, "new")
        assert new["background"] == "#2e7d32"
        for key in ("border", "stroke", "strokeWidth", "opacity"):
            assert key not in new

    def test_the_webapp_graph_carries_them_to_the_frontend(self) -> None:
        workspace = _workspace('element "New" { border dashed strokeWidth 2 }')
        data = react_flow_graph(workspace, _view(workspace))
        new = next(n for n in data["nodes"] if n["id"] == "new")
        assert new["data"]["border"] == "Dashed"
        assert new["data"]["strokeWidth"] == 2


class TestLegend:
    def test_border_is_carried_into_the_entry(self) -> None:
        workspace = _workspace('element "New" { border dashed }')
        new = next(e for e in _legend(workspace) if e["label"] == "New")
        assert new["border"] == "Dashed"

    def test_the_bug_border_only_no_longer_yields_a_twin_swatch(self) -> None:
        """The original reproduction.

        `New` differs from the default container by border alone. Before
        PP-107 both rows carried the same colour and shape with nothing to
        tell them apart; now the border distinguishes them.
        """
        workspace = _workspace('element "New" { border dashed }')
        entries = _legend(workspace)
        container = next(e for e in entries if e["label"] == "Container")
        new = next(e for e in entries if e["label"] == "New")
        assert (new["colour"], new["shape"]) == (
            container["colour"],
            container["shape"],
        )
        assert new["border"] != container["border"]

    def test_every_entry_has_the_same_keys(self) -> None:
        workspace = _workspace('element "New" { background #2e7d32 }')
        entries = _legend(workspace)
        assert entries, "the view has styles, so it must have a legend"
        for entry in entries:
            assert set(entry) == {"label", "colour", "shape", "border"}

    def test_two_tags_differing_only_by_border_are_two_rows(self) -> None:
        workspace = parse_dsl(
            """
            workspace "W" {
                model {
                    s = softwareSystem "S" {
                        a = container "A" { tags "New" }
                        b = container "B" { tags "Planned" }
                    }
                    a -> b "Calls"
                }
                views {
                    container s "cont" { include * }
                    styles {
                        element "New" { border solid }
                        element "Planned" { border dashed }
                    }
                }
            }
            """
        )
        entries = build_view_graph(workspace, workspace.views[0])["legend"]
        borders = {e["label"]: e["border"] for e in entries}
        assert borders["New"] == "Solid"
        assert borders["Planned"] == "Dashed"


class TestNoRegression:
    @pytest.mark.parametrize(
        "path",
        [
            SAMPLES / "internet_banking.dsl",
            SAMPLES / "saas_monitoring.dsl",
            SAMPLES / "ecommerce_platform.dsl",
        ],
        ids=lambda p: str(p.name),
    )
    def test_samples_without_outline_styles_gain_no_outline(self, path: Path) -> None:
        from c4studio.parser.dsl import parse_dsl_file

        workspace = parse_dsl_file(path)
        for view in workspace.views:
            for node in build_view_graph(workspace, view)["nodes"]:
                for key in ("border", "stroke", "strokeWidth", "opacity"):
                    assert key not in node["data"], f"{path.name}:{view.key}"
