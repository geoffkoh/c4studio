"""Dynamic-view step ids, and the layout keyed by them (PP-198).

A step's edge id used to embed its step number (``step-<order>-<src>__<dst>``),
and waypoints, routes, pinned sides and label offsets are saved by edge id.
Inserting one step at the top of a view renumbered every step after it and
quietly dropped their saved layout; two steps of one ``parallel`` block
between the same elements shared a number and so collided on one id.

Ids are now keyed by endpoints and occurrence, as static views' unaliased
edges are, and a sidecar written under the old ids still applies.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from c4studio.graph.view_graph import build_view_graph
from c4studio.layout_sidecar import attach_labels, attach_waypoints, saved_for
from c4studio.parser.dsl import parse_dsl_file
from c4studio.webapp.server import create_app


def _workspace(steps: str) -> str:
    return f"""
    workspace "Dyn" {{
        model {{
            a = person "A"
            s = softwareSystem "S" {{
                b = container "B"
                c = container "C"
            }}
            a -> b "Uses"
            b -> c "Calls"
            c -> a "Notifies"
        }}
        views {{
            dynamic s Flow "Flow" {{
                {steps}
            }}
        }}
    }}
    """


def _ids(tmp_path: Path, steps: str) -> list[str]:
    path = tmp_path / "w.dsl"
    path.write_text(_workspace(steps), encoding="utf-8")
    workspace = parse_dsl_file(path)
    return [e["id"] for e in build_view_graph(workspace, workspace.views[0])["edges"]]


class TestIds:
    def test_inserting_a_step_keeps_the_others_ids(self, tmp_path: Path) -> None:
        before = _ids(tmp_path, 'a -> b "one"\nb -> c "two"')
        after = _ids(tmp_path, 'c -> a "new first"\na -> b "one"\nb -> c "two"')
        assert after[1:] == before

    def test_parallel_steps_between_one_pair_are_told_apart(
        self, tmp_path: Path
    ) -> None:
        ids = _ids(tmp_path, 'parallel {\na -> b "x"\na -> b "y"\n}')
        assert len(ids) == 2
        assert len(set(ids)) == 2

    def test_the_old_id_is_listed_for_migration(self, tmp_path: Path) -> None:
        path = tmp_path / "w.dsl"
        path.write_text(_workspace('a -> b "one"\nb -> c "two"'), encoding="utf-8")
        workspace = parse_dsl_file(path)
        edges = build_view_graph(workspace, workspace.views[0])["edges"]
        assert [e["previousIds"] for e in edges] == [["step-1-a__b"], ["step-2-b__c"]]


class TestSavedFor:
    def test_the_current_id_wins_over_an_old_one(self) -> None:
        edge = {"id": "new", "previousIds": ["old"]}
        assert saved_for({"new": 1, "old": 2}, edge) == 1

    def test_an_old_id_is_used_when_the_current_one_is_absent(self) -> None:
        edge = {"id": "new", "previousIds": ["old"]}
        assert saved_for({"old": 2}, edge) == 2

    def test_an_edge_without_old_ids_is_unaffected(self) -> None:
        assert saved_for({"x": 1}, {"id": "y"}) is None

    def test_attach_reads_old_ids(self) -> None:
        data: dict[str, Any] = {"edges": [{"id": "new", "previousIds": ["old"]}]}
        attach_waypoints(data, {"old": [[1, 2]]})
        attach_labels(data, {"old": [3, 4]})
        assert data["edges"][0]["waypoints"] == [[1, 2]]
        assert data["edges"][0]["labelOffset"] == [3, 4]


def test_a_sidecar_saved_under_old_ids_still_applies(tmp_path: Path) -> None:
    """The real migration path: an existing sidecar, a fresh server."""
    (tmp_path / "w.dsl").write_text(
        _workspace('a -> b "one"\nb -> c "two"'), encoding="utf-8"
    )
    (tmp_path / "w.layout.json").write_text(
        json.dumps(
            {
                "edges": {"Flow": {"step-2-b__c": [[100, 200]]}},
                "labels": {"Flow": {"step-2-b__c": [5, 6]}},
            }
        ),
        encoding="utf-8",
    )
    client = TestClient(create_app(root=tmp_path))
    client.post("/api/load", json={"path": "w.dsl"})
    edges = client.get("/api/views/Flow/graph").json()["edges"]
    step = next(e for e in edges if e["source"] == "b")
    assert step["id"] != "step-2-b__c"
    assert step["waypoints"] == [[100, 200]]
    assert step["labelOffset"] == [5, 6]
