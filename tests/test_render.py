"""Headless SVG rendering (PP-93).

Rendering is the one command that needs Node, so the tests split in two:
everything that can be checked without it (error paths, the bundled
renderer being present, the CLI's view selection) always runs, and the
end-to-end renders skip when no ``node`` is available.
"""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path

import pytest
from click.testing import CliRunner

from c4studio.cli.main import cli
from c4studio.models import View, Workspace
from c4studio.parser.dsl import parse_dsl_file
from c4studio.render import (
    LEGACY_NODE_ENV_VAR,
    NODE_ENV_VAR,
    RenderError,
    node_executable,
    render_view,
    renderer_script,
)

SAMPLES = Path(__file__).parent.parent / "samples"


def _node_available() -> bool:
    try:
        node_executable()
    except RenderError:
        return False
    return True


needs_node = pytest.mark.skipif(
    not _node_available(),
    reason=f"no node on PATH and {NODE_ENV_VAR} unset",
)


@pytest.fixture(scope="module")
def banking() -> Workspace:
    return parse_dsl_file(SAMPLES / "internet_banking.dsl")


def _height(svg: str) -> float:
    match = re.search(r'height="([\d.]+)"', svg)
    assert match is not None
    return float(match.group(1))


def _view(workspace: Workspace, key: str) -> View:
    return next(v for v in workspace.views if v.key == key)


class TestWithoutNode:
    def test_the_bundled_renderer_ships_with_the_package(self) -> None:
        """The wheel must carry it; a stale checkout is the usual cause."""
        script = renderer_script()
        assert script.exists(), f"{script} missing — run npm run build"
        assert script.read_text(encoding="utf-8").lstrip().startswith("//")

    def test_missing_node_is_an_actionable_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv(NODE_ENV_VAR, raising=False)
        monkeypatch.delenv(LEGACY_NODE_ENV_VAR, raising=False)
        monkeypatch.setattr("c4studio.render.shutil.which", lambda _: None)
        with pytest.raises(RenderError) as excinfo:
            node_executable()
        message = str(excinfo.value)
        assert "Node.js" in message
        assert NODE_ENV_VAR in message
        # It must also say what still works, so nobody thinks the tool broke.
        assert "generate" in message

    def test_configured_node_must_exist(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv(NODE_ENV_VAR, str(tmp_path / "nope"))
        with pytest.raises(RenderError, match="does not exist"):
            node_executable()

    def test_the_pre_rename_variable_still_works(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """PYSTRUCTURIZR_NODE usually lives in CI config (PP-106)."""
        monkeypatch.delenv(NODE_ENV_VAR, raising=False)
        monkeypatch.setenv(LEGACY_NODE_ENV_VAR, str(tmp_path / "nope"))
        with pytest.raises(RenderError, match="does not exist"):
            node_executable()

    def test_the_current_variable_wins_over_the_legacy_one(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        node = tmp_path / "node"
        node.write_text("")
        monkeypatch.setenv(NODE_ENV_VAR, str(node))
        monkeypatch.setenv(LEGACY_NODE_ENV_VAR, str(tmp_path / "nope"))
        assert node_executable() == str(node)

    def test_unknown_view_is_rejected_before_node_is_needed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv(NODE_ENV_VAR, raising=False)
        monkeypatch.delenv(LEGACY_NODE_ENV_VAR, raising=False)
        monkeypatch.setattr("c4studio.render.shutil.which", lambda _: None)
        result = CliRunner().invoke(
            cli, ["render", str(SAMPLES / "internet_banking.dsl"), "-v", "Nope"]
        )
        assert result.exit_code != 0
        assert "not found or not renderable" in result.output
        assert "SystemContext" in result.output


@needs_node
class TestRendering:
    def test_renders_a_standalone_svg(self, banking: Workspace) -> None:
        svg = render_view(banking, _view(banking, "Containers"))
        assert svg.startswith("<svg xmlns=")
        assert svg.rstrip().endswith("</svg>")
        assert "<title>" in svg

    def test_no_external_references(self, banking: Workspace) -> None:
        """A file that phones home renders differently offline."""
        svg = render_view(banking, _view(banking, "Containers"))
        # Images are allowed, but only as embedded data: URIs (PP-94).
        assert 'href="http' not in svg
        assert "@import" not in svg
        assert "<link" not in svg
        # The only URL allowed is the SVG namespace itself.
        urls = re.findall(r"https?://[^\s\"']+", svg)
        assert urls == ["http://www.w3.org/2000/svg"]

    def test_deterministic(self, banking: Workspace) -> None:
        """Committed diagrams must not churn between runs."""
        view = _view(banking, "Containers")
        assert render_view(banking, view) == render_view(banking, view)

    def test_every_element_reaches_the_output(self, banking: Workspace) -> None:
        view = _view(banking, "Containers")
        svg = render_view(banking, view)
        for name in (
            "Web Application",
            "API Gateway",
            "Accounts Database",
            "Personal Banking Customer",
        ):
            assert name.split()[0] in svg, name

    def test_boundary_and_metadata_are_drawn(self, banking: Workspace) -> None:
        svg = render_view(banking, _view(banking, "Containers"))
        assert "stroke-dasharray" in svg  # the boundary
        assert "[Software System]" in svg  # its type caption
        assert "[Container: Kong]" in svg  # an element's metadata line

    def test_suppressed_metadata_is_not_drawn(self, tmp_path: Path) -> None:
        source = tmp_path / "ws.dsl"
        source.write_text(
            """
            workspace "W" {
                model {
                    u = person "User"
                    s = softwareSystem "S" {
                        db = container "DB" "Storage" "PostgreSQL" {
                            tags "Datastore"
                        }
                    }
                    u -> db "Uses"
                }
                views {
                    container s "cont" { include * }
                    styles {
                        element "Datastore" { metadata false }
                    }
                }
            }
            """,
            encoding="utf-8",
        )
        workspace = parse_dsl_file(source)
        svg = render_view(workspace, _view(workspace, "cont"))
        assert "[Container: PostgreSQL]" not in svg
        assert "DB" in svg

    def test_theme_icons_are_embedded(self, tmp_path: Path) -> None:
        """A themed element's logo travels inside the file (PP-94)."""
        icon = tmp_path / "lambda.png"
        icon.write_bytes(
            base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8"
                "BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
            )
        )
        theme = tmp_path / "theme.json"
        theme.write_text(
            json.dumps(
                {
                    "name": "Test",
                    "elements": [{"tag": "Serverless", "icon": "lambda.png"}],
                }
            ),
            encoding="utf-8",
        )
        source = tmp_path / "ws.dsl"
        source.write_text(
            f"""
            workspace "W" {{
                model {{
                    u = person "User"
                    s = softwareSystem "S" {{
                        fn = container "Function" {{
                            tags "Serverless"
                        }}
                    }}
                    u -> fn "Calls"
                }}
                views {{
                    container s "cont" {{ include * }}
                    theme "{theme.as_uri()}"
                }}
            }}
            """,
            encoding="utf-8",
        )
        workspace = parse_dsl_file(source)
        svg = render_view(workspace, _view(workspace, "cont"))
        assert "<image" in svg
        assert 'href="data:image/png;base64,' in svg
        # Still nothing to fetch at view time.
        assert 'href="file:' not in svg and 'href="http' not in svg

    def test_title_and_legend_can_be_switched_off(self, banking: Workspace) -> None:
        """The switches existed in the TS options but nothing reached them."""
        view = _view(banking, "Containers")
        full = render_view(banking, view)
        bare = render_view(banking, view, show_title=False, show_legend=False)
        assert "Internet Banking – Containers</text>" in full
        assert "Internet Banking – Containers</text>" not in bare
        # The document <title> is metadata, not ink: it stays either way.
        assert "<title>" in bare
        # Dropping both shrinks the canvas, since they extend it.
        assert _height(bare) < _height(full)

    def test_each_switch_acts_alone(self, banking: Workspace) -> None:
        view = _view(banking, "Containers")
        full = _height(render_view(banking, view))
        no_title = _height(render_view(banking, view, show_title=False))
        no_legend = _height(render_view(banking, view, show_legend=False))
        assert no_title < full
        assert no_legend < full
        assert no_legend < no_title  # the legend is the taller block

    @pytest.mark.parametrize(
        "key",
        ["Landscape", "OmsContext", "OmsContainers", "PlaceOrder", "OmsProduction"],
    )
    def test_every_view_type_renders(self, key: str) -> None:
        """Landscape, context, container, dynamic and deployment views."""
        workspace = parse_dsl_file(SAMPLES / "hedge_fund" / "workspace.dsl")
        svg = render_view(workspace, _view(workspace, key))
        assert svg.startswith("<svg xmlns=")
        assert svg.count("<text") > 1

    def test_cli_writes_one_file_per_view(self, tmp_path: Path) -> None:
        result = CliRunner().invoke(
            cli,
            [
                "render",
                str(SAMPLES / "internet_banking.dsl"),
                "--output",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0, result.output
        written = sorted(p.name for p in tmp_path.glob("*.svg"))
        assert written == ["Containers.svg", "SystemContext.svg"]
        assert (tmp_path / "Containers.svg").read_text().startswith("<svg")

    def test_cli_flags_reach_the_renderer(self) -> None:
        runner = CliRunner()
        base = ["render", str(SAMPLES / "internet_banking.dsl"), "-v", "Containers"]
        full = runner.invoke(cli, base)
        bare = runner.invoke(cli, [*base, "--no-title", "--no-legend"])
        assert full.exit_code == 0 and bare.exit_code == 0, bare.output
        assert _height(bare.output) < _height(full.output)

    def test_cli_prints_a_single_view_to_stdout(self) -> None:
        result = CliRunner().invoke(
            cli,
            ["render", str(SAMPLES / "internet_banking.dsl"), "-v", "SystemContext"],
        )
        assert result.exit_code == 0, result.output
        assert result.output.startswith("<svg xmlns=")
