"""``icon <file>`` in the workspace's own styles (PP-232).

Upstream's ``ElementStyleParser.parseIcon`` resolves a path that is not a
URL against the file the style is written in, and embeds the image as a
``data:`` URI. So does this parser: an icon downloaded into the repo then
draws on every surface with no file server and no network, and the path
as written is kept for the details card to show.
"""

from __future__ import annotations

import base64
from pathlib import Path

import pytest

from c4studio.generators.json_export import workspace_to_json
from c4studio.graph.view_graph import build_view_graph
from c4studio.models.workspace import Workspace
from c4studio.parser.dsl import parse_dsl, parse_dsl_file

# A 1x1 transparent PNG, so the encoding is checked byte for byte.
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)
PNG_URI = "data:image/png;base64," + base64.b64encode(PNG).decode("ascii")


def _workspace(styles: str) -> str:
    return (
        'workspace "T" {\n'
        "    model {\n"
        '        s = softwareSystem "S" {\n'
        '            fn = container "Fn" "" "" "Serverless"\n'
        "        }\n"
        "    }\n"
        "    views {\n"
        "        container s Containers {\n"
        "            include *\n"
        "        }\n"
        f"{styles}\n"
        "    }\n"
        "}\n"
    )


def _styles(icon: str) -> str:
    return (
        "        styles {\n"
        '            element "Serverless" {\n'
        f"                icon {icon}\n"
        "            }\n"
        "        }"
    )


def _icon_style(workspace: Workspace) -> tuple[str, str]:
    style = next(
        s
        for s in workspace.views.configuration.styles.element_styles
        if s.tag == "Serverless"
    )
    return style.icon, style.icon_source


def _node(workspace: Workspace) -> dict[str, object]:
    view = next(v for v in workspace.views if v.key == "Containers")
    graph = build_view_graph(workspace, view)
    data: dict[str, object] = next(n["data"] for n in graph["nodes"] if n["id"] == "fn")
    return data


@pytest.fixture
def icons(tmp_path: Path) -> Path:
    folder = tmp_path / "icons" / "aws"
    folder.mkdir(parents=True)
    (folder / "lambda.png").write_bytes(PNG)
    return tmp_path


def test_a_relative_icon_is_embedded_and_its_path_kept(icons: Path) -> None:
    path = icons / "workspace.dsl"
    path.write_text(_workspace(_styles('"icons/aws/lambda.png"')), encoding="utf-8")
    workspace = parse_dsl_file(path)
    assert _icon_style(workspace) == (PNG_URI, "icons/aws/lambda.png")
    assert not workspace.diagnostics

    data = _node(workspace)
    assert data["icon"] == PNG_URI
    assert data["iconSource"] == "icons/aws/lambda.png"
    assert data["styleOrigins"] == {"icon": {"tag": "Serverless", "theme": False}}


def test_the_path_is_relative_to_the_file_the_style_is_in(icons: Path) -> None:
    # A fragment in a subfolder resolves against itself, as upstream does
    # with `context.getFile().getParent()`.
    (icons / "styles").mkdir()
    (icons / "styles" / "icons.dsl").write_text(
        'element "Serverless" {\n    icon "../icons/aws/lambda.png"\n}\n',
        encoding="utf-8",
    )
    path = icons / "workspace.dsl"
    path.write_text(
        _workspace(
            '        styles {\n            !include "styles/icons.dsl"\n        }'
        ),
        encoding="utf-8",
    )
    workspace = parse_dsl_file(path)
    assert not workspace.diagnostics
    assert _icon_style(workspace) == (PNG_URI, "../icons/aws/lambda.png")


def test_a_missing_file_warns_and_the_box_draws_without_it(tmp_path: Path) -> None:
    path = tmp_path / "workspace.dsl"
    path.write_text(_workspace(_styles('"icons/nope.png"')), encoding="utf-8")
    workspace = parse_dsl_file(path)
    assert _icon_style(workspace) == ("", "icons/nope.png")
    [diagnostic] = workspace.diagnostics
    assert diagnostic.code == "icon-not-found"
    assert diagnostic.line == 13
    assert "icons/nope.png" in diagnostic.message
    assert "icon" not in _node(workspace)


def test_a_file_that_is_not_an_image_warns(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("hello", encoding="utf-8")
    path = tmp_path / "workspace.dsl"
    path.write_text(_workspace(_styles('"notes.txt"')), encoding="utf-8")
    workspace = parse_dsl_file(path)
    assert _icon_style(workspace)[0] == ""
    [diagnostic] = workspace.diagnostics
    assert diagnostic.code == "icon-not-found"
    assert "not a supported image" in diagnostic.message


@pytest.mark.parametrize(
    "icon", ["https://example.com/lambda.png", PNG_URI], ids=["url", "data"]
)
def test_urls_and_data_uris_are_left_as_written(tmp_path: Path, icon: str) -> None:
    path = tmp_path / "workspace.dsl"
    path.write_text(_workspace(_styles(f'"{icon}"')), encoding="utf-8")
    workspace = parse_dsl_file(path)
    assert _icon_style(workspace) == (icon, icon)
    assert not workspace.diagnostics


def test_an_unquoted_url_says_to_quote_it(tmp_path: Path) -> None:
    # The tokeniser reads `//` as a comment anywhere on a line, so only the
    # scheme survives; it is not a file to look for.
    path = tmp_path / "workspace.dsl"
    path.write_text(_workspace(_styles("https://example.com/a.png")), encoding="utf-8")
    workspace = parse_dsl_file(path)
    assert _icon_style(workspace)[0] == ""
    [diagnostic] = workspace.diagnostics
    assert diagnostic.code == "icon-not-found"
    assert "needs quotes" in diagnostic.message


def test_a_file_needs_a_file_to_be_relative_to() -> None:
    workspace = parse_dsl(_workspace(_styles('"icons/aws/lambda.png"')))
    assert _icon_style(workspace)[0] == ""
    [diagnostic] = workspace.diagnostics
    assert diagnostic.code == "icon-not-found"


def test_the_json_export_carries_the_image_not_the_path(icons: Path) -> None:
    # What upstream's export holds too: the path means nothing elsewhere.
    path = icons / "workspace.dsl"
    path.write_text(_workspace(_styles('"icons/aws/lambda.png"')), encoding="utf-8")
    exported = workspace_to_json(parse_dsl_file(path))
    [style] = exported["workspace"]["views"]["configuration"]["styles"]["elements"]
    assert style["icon"] == PNG_URI
