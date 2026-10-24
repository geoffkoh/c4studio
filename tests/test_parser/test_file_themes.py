"""``theme <file>``: a theme read from disk and inlined, as upstream (PP-199).

structurizr-java's ``ThemeParser`` accepts ``theme <name|url|file>``. A
non-URL is resolved against the DSL file, its styles are copied into the
workspace's own, and each relative icon becomes a ``data:`` URI
(``ThemeUtils.inlineAllStylesFromTheme``). So a file theme needs no
network and no file server, which is the point of it.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from c4studio.generators.json_export import workspace_to_json
from c4studio.graph.view_graph import build_view_graph
from c4studio.lint import lint
from c4studio.parser.dsl import parse_dsl, parse_dsl_file

# A 1x1 transparent PNG: the smallest real image, so the encoding is
# checked byte for byte rather than for "looks like base64".
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


def _theme(**overrides: object) -> str:
    theme: dict[str, object] = {
        "name": "Corporate",
        "elements": [
            {"tag": "Database", "background": "#aa0000", "icon": "icons/db.png"},
            {"tag": "Queue", "icon": "https://example.com/queue.png"},
        ],
        "relationships": [{"tag": "Async", "color": "#7b1fa2"}],
    }
    theme.update(overrides)
    return json.dumps(theme)


def _workspace(tmp_path: Path, views: str) -> Path:
    path = tmp_path / "workspace.dsl"
    path.write_text(
        'workspace "T" {\n'
        "    model {\n"
        '        s = softwareSystem "S" {\n'
        '            db = container "DB" "" "" "Database"\n'
        "        }\n"
        "    }\n"
        "    views {\n"
        "        container s Containers {\n"
        "            include *\n"
        "        }\n"
        f"{views}\n"
        "    }\n"
        "}\n",
        encoding="utf-8",
    )
    return path


@pytest.fixture
def theme_dir(tmp_path: Path) -> Path:
    """A theme in a subfolder, with its icon in a folder beside it."""
    folder = tmp_path / "themes"
    (folder / "icons").mkdir(parents=True)
    (folder / "corporate.json").write_text(_theme(), encoding="utf-8")
    (folder / "icons" / "db.png").write_bytes(PNG)
    return folder


def test_file_theme_styles_are_inlined_into_the_workspace(
    tmp_path: Path, theme_dir: Path
) -> None:
    workspace = parse_dsl_file(
        _workspace(tmp_path, '        theme "themes/corporate.json"')
    )

    configuration = workspace.views.configuration
    styles = configuration.theme_file_styles
    assert [s.tag for s in styles.element_styles] == ["Database", "Queue"]
    assert [s.tag for s in styles.relationship_styles] == ["Async"]
    assert styles.relationship_styles[0].color == "#7b1fa2"
    # Inlined, not referenced: nothing is left for anything to fetch...
    assert configuration.themes == []
    # ...and held apart from what the author wrote.
    assert configuration.styles.element_styles == []
    assert workspace.diagnostics == []


def test_relative_icons_become_data_uris_and_others_are_kept(
    tmp_path: Path, theme_dir: Path
) -> None:
    workspace = parse_dsl_file(
        _workspace(tmp_path, '        theme "themes/corporate.json"')
    )

    database, queue = workspace.views.configuration.theme_file_styles.element_styles
    expected = "data:image/png;base64," + base64.b64encode(PNG).decode("ascii")
    assert database.icon == expected
    # A URL icon is left as a URL, exactly as upstream leaves it.
    assert queue.icon == "https://example.com/queue.png"


def test_the_view_graph_carries_the_icon_with_no_network(
    tmp_path: Path, theme_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole point: a file theme renders offline."""

    def no_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("a file theme must not touch the network")

    monkeypatch.setattr("c4studio.themes.urlopen", no_network)
    monkeypatch.setattr("c4studio.icons.urlopen", no_network)
    workspace = parse_dsl_file(
        _workspace(tmp_path, '        theme "themes/corporate.json"')
    )
    view = next(v for v in workspace.views if v.key == "Containers")

    graph = build_view_graph(workspace, view)

    db = next(n for n in graph["nodes"] if n["id"] == "db")
    assert db["data"]["icon"].startswith("data:image/png;base64,")
    assert db["data"]["background"] == "#aa0000"


def test_a_workspace_style_declared_after_the_theme_wins(
    tmp_path: Path, theme_dir: Path
) -> None:
    workspace = parse_dsl_file(
        _workspace(
            tmp_path,
            '        theme "themes/corporate.json"\n'
            "        styles {\n"
            '            element "Database" {\n'
            "                background #0000aa\n"
            "            }\n"
            "        }",
        )
    )
    view = next(v for v in workspace.views if v.key == "Containers")

    db = next(n for n in build_view_graph(workspace, view)["nodes"] if n["id"] == "db")

    assert db["data"]["background"] == "#0000aa"
    # ...and the theme still supplies what the workspace did not override.
    assert db["data"]["icon"].startswith("data:image/png")


def test_a_workspace_style_declared_before_the_theme_also_wins(
    tmp_path: Path, theme_dir: Path
) -> None:
    """Unlike upstream, order does not decide: the workspace always wins,
    the same rule a fetched (URL) theme follows."""
    workspace = parse_dsl_file(
        _workspace(
            tmp_path,
            "        styles {\n"
            '            element "Database" {\n'
            "                background #0000aa\n"
            "            }\n"
            "        }\n"
            '        theme "themes/corporate.json"',
        )
    )
    view = next(v for v in workspace.views if v.key == "Containers")

    db = next(n for n in build_view_graph(workspace, view)["nodes"] if n["id"] == "db")

    assert db["data"]["background"] == "#0000aa"


def test_lint_does_not_report_a_themes_unused_tags(
    tmp_path: Path, theme_dir: Path
) -> None:
    """`Queue` matches nothing in this model; that is the theme's business."""
    workspace = parse_dsl_file(
        _workspace(tmp_path, '        theme "themes/corporate.json"')
    )

    findings = lint(workspace)

    assert not [f for f in findings if f.code == "unused-style"]


def test_json_export_carries_the_inlined_styles_first(
    tmp_path: Path, theme_dir: Path
) -> None:
    workspace = parse_dsl_file(
        _workspace(
            tmp_path,
            '        theme "themes/corporate.json"\n'
            "        styles {\n"
            '            element "Database" {\n'
            "                background #0000aa\n"
            "            }\n"
            "        }",
        )
    )

    exported = workspace_to_json(workspace)["workspace"]["views"]["configuration"]

    assert [s["tag"] for s in exported["styles"]["elements"]] == [
        "Database",
        "Queue",
        "Database",
    ]
    assert exported["styles"]["elements"][0]["icon"].startswith("data:image/png")
    assert "themes" not in exported or exported["themes"] == []


def test_urls_and_files_mix_in_one_themes_statement(
    tmp_path: Path, theme_dir: Path
) -> None:
    workspace = parse_dsl_file(
        _workspace(
            tmp_path,
            '        themes "https://example.com/t.json" "themes/corporate.json"',
        )
    )

    assert workspace.views.configuration.themes == ["https://example.com/t.json"]
    assert len(workspace.views.configuration.theme_file_styles.element_styles) == 2


def test_a_missing_theme_file_is_a_diagnostic_not_a_crash(tmp_path: Path) -> None:
    """Upstream throws; here a skipped construct fails soft, as every other does."""
    workspace = parse_dsl_file(_workspace(tmp_path, '        theme "nope.json"'))

    assert workspace.views.configuration.theme_file_styles.element_styles == []
    [diagnostic] = workspace.diagnostics
    assert diagnostic.code == "theme-not-found"
    assert "nope.json" in diagnostic.message


def test_an_invalid_theme_file_is_a_diagnostic(tmp_path: Path) -> None:
    (tmp_path / "broken.json").write_text("{ not json", encoding="utf-8")

    workspace = parse_dsl_file(_workspace(tmp_path, '        theme "broken.json"'))

    [diagnostic] = workspace.diagnostics
    assert diagnostic.code == "invalid-theme"


def test_a_missing_icon_drops_the_icon_and_keeps_the_style(
    tmp_path: Path, theme_dir: Path
) -> None:
    (theme_dir / "icons" / "db.png").unlink()

    workspace = parse_dsl_file(
        _workspace(tmp_path, '        theme "themes/corporate.json"')
    )

    database = workspace.views.configuration.theme_file_styles.element_styles[0]
    assert database.icon == ""
    assert database.background == "#aa0000"


def test_a_file_theme_without_a_file_context_is_reported() -> None:
    """Parsing a string has no directory to resolve the theme against."""
    workspace = parse_dsl(
        'workspace "T" {\n    model {\n    }\n    views {\n'
        '        theme "corporate.json"\n'
        "    }\n}\n"
    )

    [diagnostic] = workspace.diagnostics
    assert diagnostic.code == "theme-not-found"
