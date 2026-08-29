"""The VS Code grammar fixture must stay valid DSL."""

from __future__ import annotations

from pathlib import Path

from c4studio.parser.dsl import parse_dsl_file

FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "editors"
    / "vscode"
    / "fixtures"
    / "highlighting.dsl"
)


def test_highlighting_fixture_parses() -> None:
    """The grammar fixture is real DSL, not a bag of keywords.

    It exists so the syntax highlighter can be checked by eye, which is only
    meaningful if the language actually accepts it — otherwise the fixture
    drifts into terms the parser never sees.
    """
    workspace = parse_dsl_file(FIXTURE)

    assert workspace.name == "Highlighting"
    assert len(workspace.people) == 1
    assert len(workspace.software_systems) == 2
    assert len(list(workspace.views)) == 9
    # A silently emptied model still "parses", so assert we got the depth.
    shop = next(s for s in workspace.software_systems if s.name == "Shop")
    assert len(shop.containers) == 2
    assert shop.properties == {"owner": "platform-team"}
    assert workspace.parse_warnings == []
