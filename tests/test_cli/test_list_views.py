"""`list-views --json` is the view index the VS Code extension reads."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from c4studio.cli.main import cli

WITH_DEFAULT = """
workspace "W" {
    model {
        u = person "User"
        s = softwareSystem "S"
        u -> s "Uses"
    }
    views {
        systemLandscape Landscape "The landscape" {
            include *
        }
        systemContext s Context "The context" {
            include *
            default
        }
        image s Picture {
            url "https://example.com/a.png"
        }
    }
}
"""

#: `default` is a bare keyword *inside* a view block, not `default <key>`
#: at the views level — the first draft of these tests got that wrong and
#: the parser skipped the line with a warning rather than failing, so the
#: only symptom was an assertion about ordering.


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "workspace.dsl"
    path.write_text(text, encoding="utf-8")
    return path


def _views(tmp_path: Path, text: str = WITH_DEFAULT) -> list[dict[str, object]]:
    result = CliRunner().invoke(
        cli, ["list-views", str(_write(tmp_path, text)), "--json"]
    )
    assert result.exit_code == 0, result.output
    parsed: list[dict[str, object]] = json.loads(result.output)
    return parsed


def test_json_carries_what_a_view_picker_needs(tmp_path: Path) -> None:
    """Key to render by, title to show, and type — for every view."""
    views = _views(tmp_path)

    assert {v["key"] for v in views} == {"Landscape", "Context", "Picture"}
    context = next(v for v in views if v["key"] == "Context")
    assert context["type"] == "systemContext"
    assert context["title"] == "The context"
    assert context["element_id"] == "s"


def test_the_default_view_is_flagged_and_comes_first(tmp_path: Path) -> None:
    """So a picker can open the right one without a second decision.

    This is the half the frontend still does not read — nothing in
    `frontend/src` consumes `default`, which is why the VS Code preview
    lands on "Choose a renderable view from the sidebar" with the sidebar
    collapsed. The extension reads it from here instead.
    """
    views = _views(tmp_path)

    assert views[0]["key"] == "Context"
    assert views[0]["default"] is True
    assert [v["default"] for v in views[1:]] == [False, False]


def test_declaration_order_survives_when_no_default_is_declared(
    tmp_path: Path,
) -> None:
    """Sorting only applies when there is something to sort to the front."""
    views = _views(tmp_path, WITH_DEFAULT.replace("            default\n", ""))

    assert [v["key"] for v in views] == ["Landscape", "Context", "Picture"]
    assert not any(v["default"] for v in views)


def test_unrenderable_views_are_listed_but_marked(tmp_path: Path) -> None:
    """`image` parses and round-trips, and no renderer draws it.

    A picker that offered it would produce an empty panel, so the flag has
    to travel with the entry rather than the caller re-deriving which types
    are supported.
    """
    views = _views(tmp_path)

    by_key = {v["key"]: v["supported"] for v in views}
    assert by_key == {"Landscape": True, "Context": True, "Picture": False}


def test_the_table_output_is_unchanged(tmp_path: Path) -> None:
    """--json is additive; the human-readable default still prints."""
    result = CliRunner().invoke(
        cli, ["list-views", str(_write(tmp_path, WITH_DEFAULT))]
    )

    assert result.exit_code == 0
    assert "Key" in result.output and "Element ID" in result.output
    assert "Context" in result.output
    assert not result.output.lstrip().startswith("[")
