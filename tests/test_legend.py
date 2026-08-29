"""Legend entries derived once in the graph layer (PP-99).

A legend exists for people who did not build the diagram, which means it
has to survive export — so it is derived here rather than assembled in the
viewer, and both renderers consume the same entries.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pystructurizr.graph.view_graph import build_view_graph, legend_entries
from pystructurizr.models import Styles, View, Workspace
from pystructurizr.parser.dsl import parse_dsl, parse_dsl_file
from pystructurizr.webapp.graph import react_flow_graph

SAMPLES = Path(__file__).parent.parent / "samples"


@pytest.fixture(autouse=True)
def _no_remote_themes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "pystructurizr.graph.view_graph.theme_styles", lambda workspace: Styles()
    )


WORKSPACE = """
workspace "W" {
    model {
        u = person "User"
        admin = person "Admin" {
            tags "Staff"
        }
        s = softwareSystem "S" {
            web = container "Web"
            api = container "API"
            db = container "DB" {
                tags "Datastore"
            }
        }
        ext = softwareSystem "Partner" {
            tags "External System"
        }
        u -> web "Uses"
        api -> db "Reads"
        api -> ext "Calls"
    }
    views {
        container s "cont" { include * }
        systemLandscape "land" { include * }
        styles {
            element "Datastore" {
                shape Cylinder
                background #aa0000
            }
        }
    }
}
"""


def _view(workspace: Workspace, key: str) -> View:
    return next(v for v in workspace.views if v.key == key)


def _labels(workspace: Workspace, key: str) -> list[str]:
    data = build_view_graph(workspace, _view(workspace, key))
    return [entry["label"] for entry in data["legend"]]


class TestEntries:
    def test_one_entry_per_distinct_style(self) -> None:
        workspace = parse_dsl(WORKSPACE)
        labels = _labels(workspace, "cont")
        # Two plain containers collapse into one "Container" entry.
        assert labels.count("Container") == 1
        assert "Datastore" in labels
        assert "Boundary" in labels

    def test_style_tag_wins_over_the_kind_name(self) -> None:
        """A legend should say "Datastore", not "Container"."""
        workspace = parse_dsl(WORKSPACE)
        data = build_view_graph(workspace, _view(workspace, "cont"))
        datastore = next(e for e in data["legend"] if e["label"] == "Datastore")
        assert datastore["colour"] == "#aa0000"
        assert datastore["shape"] == "Cylinder"

    def test_externals_are_named_apart(self) -> None:
        """They carry a different colour, so one shared label would mislead."""
        workspace = parse_dsl(WORKSPACE)
        labels = _labels(workspace, "land")
        assert "Software System (external)" in labels
        assert "Software System" in labels

    def test_boundary_entry_only_when_the_view_draws_one(self) -> None:
        workspace = parse_dsl(WORKSPACE)
        assert "Boundary" in _labels(workspace, "cont")  # system boundary
        assert "Boundary" not in _labels(workspace, "land")  # flat landscape

    def test_order_follows_the_nodes(self) -> None:
        """Ordering by node order, not a set, keeps renders byte-identical."""
        workspace = parse_dsl(WORKSPACE)
        data = build_view_graph(workspace, _view(workspace, "cont"))
        assert data["legend"] == legend_entries(data["nodes"])
        again = build_view_graph(workspace, _view(workspace, "cont"))
        assert again["legend"] == data["legend"]

    def test_entries_carry_what_a_swatch_needs(self) -> None:
        workspace = parse_dsl(WORKSPACE)
        for entry in build_view_graph(workspace, _view(workspace, "cont"))["legend"]:
            assert set(entry) == {"label", "colour", "shape"}
            assert entry["colour"].startswith("#")
            assert entry["shape"]

    def test_boundaries_never_become_element_entries(self) -> None:
        workspace = parse_dsl(WORKSPACE)
        data = build_view_graph(workspace, _view(workspace, "cont"))
        boundary_labels = [
            n["data"]["label"] for n in data["nodes"] if n["data"]["kind"] == "boundary"
        ]
        entry_labels = [e["label"] for e in data["legend"]]
        for label in boundary_labels:
            assert label not in entry_labels


class TestEveryViewType:
    @pytest.mark.parametrize(
        "key", ["Landscape", "OmsContext", "OmsContainers", "PlaceOrder", "OmsProduction"]
    )
    def test_all_view_types_carry_a_legend(self, key: str) -> None:
        """Deployment, dynamic and filtered views take the same path."""
        workspace = parse_dsl_file(SAMPLES / "hedge_fund" / "workspace.dsl")
        data = build_view_graph(workspace, _view(workspace, key))
        assert data["legend"], key
        assert all(e["label"] for e in data["legend"])

    def test_deployment_view_names_instance_kinds(self) -> None:
        workspace = parse_dsl_file(SAMPLES / "hedge_fund" / "workspace.dsl")
        labels = _labels(workspace, "OmsProduction")
        assert "Container Instance" in labels
        assert "Infrastructure Node" in labels or any("Web Services" in x for x in labels)


class TestApi:
    def test_the_viewer_receives_the_same_entries(self) -> None:
        workspace = parse_dsl(WORKSPACE)
        view = _view(workspace, "cont")
        assert react_flow_graph(workspace, view)["legend"] == (
            build_view_graph(workspace, view)["legend"]
        )
