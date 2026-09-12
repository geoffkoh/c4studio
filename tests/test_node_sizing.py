"""Nodes are sized to their text rather than clipping it (PP-118).

The measurement lives in ``packages/diagram-core/src/nodeMetrics.ts`` and
is shared by dagre, the SVG emitter and — through matching CSS clamps —
the web app. There is no JS test harness in this repo, so the contract is
pinned where it is observable: in the SVG a headless render produces.
"""

from __future__ import annotations

import re

import pytest

from c4studio.models import Workspace
from c4studio.parser.dsl import parse_dsl
from c4studio.render import RenderError, node_executable, render_view


def _node_available() -> bool:
    try:
        node_executable()
    except RenderError:
        return False
    return True


needs_node = pytest.mark.skipif(
    not _node_available(), reason="no node available for headless render"
)

LONG_DESCRIPTION = (
    "Reconciles entitlements against subscription state across billing, "
    "CRM and the provisioning pipeline, emitting corrections downstream"
)

DSL = f"""
workspace "Sizing" {{
    model {{
        u = person "User"
        s = softwareSystem "S" {{
            long = container "Customer Entitlement and Subscription Reconciliation Service" "{LONG_DESCRIPTION}" "Java 21, Spring Boot, PostgreSQL"
            short = container "API"
        }}
        u -> long "Uses"
        long -> short "Calls"
    }}
    views {{
        container s C {{
            include *
            autoLayout
        }}
    }}
}}
"""


@pytest.fixture(scope="module")
def workspace() -> Workspace:
    return parse_dsl(DSL)


@pytest.fixture(scope="module")
def svg(workspace: Workspace) -> str:
    view = next(v for v in workspace.views if v.key == "C")
    return render_view(workspace, view)


def _texts(svg: str) -> list[str]:
    return re.findall(r">([^<>]+)</text>", svg)


def _element_boxes(svg: str) -> list[tuple[float, float, float, float]]:
    """Element rects as (x, y, width, height); elements are 200 wide."""
    return [
        (float(x), float(y), float(w), float(h))
        for x, y, w, h in re.findall(
            r'<rect x="([-\d.]+)" y="([-\d.]+)" width="([\d.]+)" height="([\d.]+)"',
            svg,
        )
        if float(w) == 200
    ]


@needs_node
def test_a_long_name_no_longer_starves_the_description(svg: str) -> None:
    """The description used to get only the lines a long name left over.

    With a three-line name it rendered two lines and stopped at
    "subscription state across…"; every line up to "provisioning" is text
    the old box had no room for.
    """
    words = set(LONG_DESCRIPTION.replace(",", "").split())
    lines = [
        text
        for text in _texts(svg)
        if words & set(text.replace(",", "").rstrip("…").split())
    ]
    assert len(lines) >= 4
    assert "provisioning" in " ".join(lines)


@needs_node
def test_the_technology_is_not_cut_mid_word(svg: str) -> None:
    """It read `[Container: Java 21, Spring…`; the metadata line now wraps."""
    assert "PostgreSQL" in " ".join(_texts(svg))


@needs_node
def test_the_wordy_node_grows_and_the_terse_one_does_not(svg: str) -> None:
    heights = {h for _, _, _, h in _element_boxes(svg)}
    # The short container sits on the 110px floor; the wordy one is taller.
    assert 110 in heights
    assert max(heights) > 110


@needs_node
def test_no_node_overlaps_another(svg: str) -> None:
    """The point of measuring: a tall box must not land on its neighbour."""
    boxes = _element_boxes(svg)
    for i, (x, y, w, h) in enumerate(boxes):
        for other_x, other_y, other_w, other_h in boxes[i + 1 :]:
            overlaps_x = x < other_x + other_w and other_x < x + w
            overlaps_y = y < other_y + other_h and other_y < y + h
            assert not (overlaps_x and overlaps_y), (
                f"node at ({x}, {y}, {w}x{h}) overlaps "
                f"({other_x}, {other_y}, {other_w}x{other_h})"
            )
