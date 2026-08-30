"""The delta-release sample stays a working answer (PP-109).

``samples/delta_release.dsl`` is the reference for marking elements as new,
existing or deprecated and getting that into the legend. It is
documentation that runs, so it is pinned here: if the legend contract
shifts, this fails rather than the sample quietly teaching the wrong thing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from c4studio.graph.view_graph import build_view_graph
from c4studio.models import View, Workspace
from c4studio.parser.dsl import parse_dsl_file

SAMPLE = Path(__file__).parent.parent.parent / "samples" / "delta_release.dsl"


@pytest.fixture(scope="module")
def workspace() -> Workspace:
    return parse_dsl_file(SAMPLE)


@pytest.fixture(scope="module")
def delta(workspace: Workspace) -> View:
    return next(v for v in workspace.views if v.key == "Delta")


def _legend(workspace: Workspace, view: View) -> dict[str, dict[str, str]]:
    entries: list[dict[str, str]] = build_view_graph(workspace, view)["legend"]
    return {e["label"]: e for e in entries}


def test_the_sample_parses_without_a_single_warning(workspace: Workspace) -> None:
    """A sample that warns is teaching the reader to ignore warnings."""
    assert workspace.diagnostics == []


def test_the_legend_names_the_lifecycle_not_the_c4_kind(
    workspace: Workspace, delta: View
) -> None:
    """The whole point: rows read New/Existing, never New/Container."""
    labels = set(_legend(workspace, delta))
    assert {"Existing", "New", "Deprecated"} <= labels
    assert "Container" not in labels


def test_each_lifecycle_row_is_visually_distinct(
    workspace: Workspace, delta: View
) -> None:
    """Two rows that look identical explain nothing."""
    legend = _legend(workspace, delta)
    swatches = [
        (legend[label]["colour"], legend[label]["shape"], legend[label]["border"])
        for label in ("Existing", "New", "Deprecated", "External")
    ]
    assert len(set(swatches)) == len(swatches)


def test_deprecated_is_separable_from_external_without_opacity(
    workspace: Workspace, delta: View
) -> None:
    """The swatch carries no opacity, so the fade alone cannot carry it.

    Both are grey; the dotted border is what makes the legend rows tell
    them apart, and the sample's comment says so.
    """
    legend = _legend(workspace, delta)
    assert legend["Deprecated"]["border"] == "Dotted"
    assert legend["External"]["border"] == ""


def test_the_new_containers_carry_the_outline_to_the_renderer(
    workspace: Workspace, delta: View
) -> None:
    nodes = {n["id"]: n["data"] for n in build_view_graph(workspace, delta)["nodes"]}
    assert nodes["fraud"]["border"] == "Dashed"
    assert nodes["fraud"]["strokeWidth"] == 3
    assert nodes["batch"]["opacity"] == 55


def test_composed_tags_take_shape_from_one_rule_and_colour_from_another(
    workspace: Workspace, delta: View
) -> None:
    """The ledger is "Existing, Datastore": blue from one, cylinder from
    the other, and named by the rule declared last."""
    nodes = {n["id"]: n["data"] for n in build_view_graph(workspace, delta)["nodes"]}
    ledger = nodes["ledger"]
    assert ledger["shape"] == "Cylinder"
    assert ledger["background"] == _legend(workspace, delta)["Existing"]["colour"]
    assert ledger["styleTag"] == "Datastore"


def test_the_untagged_actor_falls_back_to_its_kind(
    workspace: Workspace, delta: View
) -> None:
    """Deliberate: the person is not part of the delta."""
    legend = _legend(workspace, delta)
    assert "Person" in legend
    nodes = {n["id"]: n["data"] for n in build_view_graph(workspace, delta)["nodes"]}
    assert "styleTag" not in nodes["analyst"]
