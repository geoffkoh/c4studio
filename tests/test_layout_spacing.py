"""`autoLayout` separations reach the renderer (PP-102).

They were parsed, stored on the model and serialised into the graph
payload — and then discarded, because `layout.ts` hardcoded its own
spacing. So writing `autoLayout tb 300 200` did nothing at all.
"""

from __future__ import annotations

import pytest

from pystructurizr.models import AutomaticLayout, RankDirection, View, Workspace
from pystructurizr.parser.dsl import parse_dsl
from pystructurizr.webapp.graph import (
    DEFAULT_NODE_SEPARATION,
    DEFAULT_RANK_SEPARATION,
    react_flow_graph,
)

WORKSPACE = """
workspace "W" {{
    model {{
        u = person "User"
        s = softwareSystem "S" {{
            a = container "A"
            b = container "B"
        }}
        u -> a "Uses"
        a -> b "Calls"
    }}
    views {{
        container s "cont" {{
            include *
            {layout}
        }}
    }}
}}
"""


def _payload(layout: str) -> dict[str, object]:
    workspace = parse_dsl(WORKSPACE.format(layout=layout))
    view = next(v for v in workspace.views if v.key == "cont")
    result: dict[str, object] = react_flow_graph(workspace, view)
    return result


class TestModelDefaults:
    def test_defaults_match_structurizr_core(self) -> None:
        """AutomaticLayout.DEFAULT_* upstream is 100 / 50 / 50."""
        layout = AutomaticLayout()
        assert layout.rank_separation == 100
        assert layout.node_separation == 50
        assert layout.edge_separation == 50
        assert layout.rank_direction == RankDirection.TOP_BOTTOM


class TestPayload:
    def test_declared_separations_are_sent(self) -> None:
        payload = _payload("autoLayout tb 300 200")
        assert payload["rankSeparation"] == 300
        assert payload["nodeSeparation"] == 200

    def test_bare_autolayout_sends_the_model_defaults(self) -> None:
        """`autoLayout` with no numbers means Structurizr's own defaults."""
        payload = _payload("autoLayout")
        assert payload["rankSeparation"] == 100
        assert payload["nodeSeparation"] == 50

    def test_a_view_without_autolayout_keeps_the_viewer_defaults(self) -> None:
        """Diagrams that never asked for spacing must not move."""
        payload = _payload("")
        assert payload["rankSeparation"] == DEFAULT_RANK_SEPARATION == 90
        assert payload["nodeSeparation"] == DEFAULT_NODE_SEPARATION == 60

    @pytest.mark.parametrize(
        "direction, expected",
        [("lr", "LR"), ("rl", "RL"), ("bt", "BT"), ("tb", "TB")],
    )
    def test_direction_still_travels_with_the_spacing(
        self, direction: str, expected: str
    ) -> None:
        payload = _payload(f"autoLayout {direction} 150 75")
        assert payload["rankDirection"] == expected
        assert payload["rankSeparation"] == 150
        assert payload["nodeSeparation"] == 75


class TestFilteredViews:
    def test_a_filtered_view_inherits_its_base_view_spacing(self) -> None:
        """It has no layout of its own, as with the direction (PP-92)."""
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
                        autoLayout lr 250 125
                    }
                    filtered land exclude "External System" "internal"
                }
            }
            """
        )
        view: View = next(v for v in workspace.views if v.key == "internal")
        payload = react_flow_graph(workspace, view)
        assert payload["rankSeparation"] == 250
        assert payload["nodeSeparation"] == 125
        assert payload["rankDirection"] == "LR"


def test_every_sample_view_carries_spacing() -> None:
    """The payload contract: these keys are always present."""
    from pathlib import Path

    from pystructurizr.parser.dsl import parse_dsl_file

    samples = Path(__file__).parent.parent / "samples"
    workspace: Workspace = parse_dsl_file(samples / "internet_banking.dsl")
    for view in workspace.views:
        payload = react_flow_graph(workspace, view)
        assert isinstance(payload["rankSeparation"], int)
        assert isinstance(payload["nodeSeparation"], int)
