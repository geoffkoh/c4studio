"""A relationship style's ``routing Orthogonal`` is drawn (PP-209).

It was parsed and exported but never painted. It now resolves, like the
other style properties, to the edge's ``styleRouting``: kept apart from
``routing``, which is the sidecar's record of a line the user re-routed,
so that a save never writes the model's choice into per-user state and
Reset route never clears it. Both renderers draw it with the router a
re-routed edge uses, so the SVG here is read back and checked segment by
segment.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from c4studio.models import View, Workspace
from c4studio.parser.dsl import parse_dsl
from c4studio.render import RenderError, node_executable
from c4studio.webapp.graph import react_flow_graph


def _dsl(styles: str) -> str:
    return f"""
    workspace "W" {{
        model {{
            u = person "User"
            s = softwareSystem "S" {{
                web = container "Web"
                api = container "API"
            }}
            u -> web "Uses"
            web -> api "Calls" {{
                tags "Internal"
            }}
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


def _view(workspace: Workspace) -> View:
    return next(v for v in workspace.views if v.key == "cont")


def _edges(styles: str) -> dict[str, dict[str, object]]:
    workspace = parse_dsl(_dsl(styles))
    return {
        e["label"]: e for e in react_flow_graph(workspace, _view(workspace))["edges"]
    }


class TestPayload:
    def test_orthogonal_reaches_the_styled_edge_only(self) -> None:
        edges = _edges('relationship "Internal" {\nrouting Orthogonal\n}')
        assert edges["Calls"]["styleRouting"] == "orthogonal"
        assert "styleRouting" not in edges["Uses"]
        # Never under the sidecar's key: that is the user's, not the model's.
        assert "routing" not in edges["Calls"]

    def test_the_base_relationship_style_covers_every_edge(self) -> None:
        edges = _edges('relationship "Relationship" {\nrouting orthogonal\n}')
        assert {e.get("styleRouting") for e in edges.values()} == {"orthogonal"}

    def test_a_later_rule_overrides_an_earlier_one(self) -> None:
        edges = _edges(
            'relationship "Relationship" {\nrouting Orthogonal\n}\n'
            'relationship "Internal" {\nrouting Direct\n}'
        )
        assert "styleRouting" not in edges["Calls"]
        assert edges["Uses"]["styleRouting"] == "orthogonal"

    @pytest.mark.parametrize("mode", ["Direct", "Curved"])
    def test_the_other_modes_leave_the_toolbar_in_charge(self, mode: str) -> None:
        edges = _edges(f'relationship "Relationship" {{\nrouting {mode}\n}}')
        assert all("styleRouting" not in e for e in edges.values())


def _node_available() -> bool:
    try:
        node_executable()
    except RenderError:
        return False
    return True


# Diagonal from one another, so an unrouted line between them is a slant.
POSITIONS = {
    "u": [0, 0],
    "s": [400, 300, 900, 800],
    "web": [500, 400],
    "api": [1000, 800],
}


def _edge_paths(svg: str) -> list[list[tuple[float, float]]]:
    paths = re.findall(r'<path d="([^"]+)"[^>]*marker-end=', svg)
    return [
        [(float(x), float(y)) for x, y in re.findall(r"([-\d.]+)[ ,]([-\d.]+)", d)]
        for d in paths
    ]


def _orthogonal(points: list[tuple[float, float]]) -> bool:
    return all(
        a[0] == b[0] or a[1] == b[1] for a, b in zip(points, points[1:], strict=False)
    )


@pytest.mark.skipif(not _node_available(), reason="no node")
@pytest.mark.parametrize(
    ("styles", "expected"),
    [
        # The control: without the style the same layout is a slant, so
        # the orthogonality check can fail.
        ("", False),
        ('relationship "Relationship" {\nrouting Orthogonal\n}', True),
    ],
)
def test_c4_render_draws_it(tmp_path: Path, styles: str, expected: bool) -> None:
    from c4studio.render import render_view

    source = tmp_path / "ws.dsl"
    source.write_text(_dsl(styles), encoding="utf-8")
    source.with_name("ws.layout.json").write_text(
        json.dumps({"version": 1, "views": {"cont": POSITIONS}}), encoding="utf-8"
    )
    workspace = parse_dsl(_dsl(styles))
    svg = render_view(workspace, _view(workspace), layout_source=source)
    paths = _edge_paths(svg)
    assert len(paths) == 2
    assert all(_orthogonal(p) for p in paths) is expected
