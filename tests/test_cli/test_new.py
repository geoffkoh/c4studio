"""``c4 new`` and the shipped starter templates (PP-137).

The test that earns its place is :func:`test_every_template_renders`. A
starter workspace that does not parse is worse than no starter workspace:
it is the first thing a new user sees, and it teaches them the tool is
broken rather than that their DSL is.

It is parametrised over whatever is *in the package*, not over a list
written here — so adding a template without checking it is not possible.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest
from click.testing import CliRunner

from c4studio import templates
from c4studio.cli.main import cli
from c4studio.parser.dsl import parse_dsl
from c4studio.webapp.graph import is_supported, react_flow_graph

ALL_TEMPLATES = [template.name for template in templates.list_templates()]


def test_the_expected_templates_ship() -> None:
    assert ALL_TEMPLATES == ["minimal", "system-context", "full-c4", "deployment"]


@pytest.mark.parametrize("name", ALL_TEMPLATES)
def test_every_template_renders(name: str, tmp_path: Path) -> None:
    """Parses clean, and every view it declares can actually be drawn."""
    source = tmp_path / f"{name}.dsl"
    source.write_text(templates.render(name), encoding="utf-8")

    with warnings.catch_warnings():
        warnings.simplefilter("error")  # a skipped construct must not pass
        workspace = parse_dsl(source.read_text(), base_dir=tmp_path, path=source)

    assert not workspace.diagnostics, [d.message for d in workspace.diagnostics]
    assert workspace.views, "a starter template with no views teaches nothing"
    for view in workspace.views:
        assert is_supported(view), f"{name}: {view.key} is not renderable"
        graph = react_flow_graph(workspace, view, None, None)
        assert graph["nodes"], f"{name}: {view.key} drew no nodes"


@pytest.mark.parametrize("name", ALL_TEMPLATES)
def test_every_template_carries_the_default_name(name: str) -> None:
    """What `--name` relies on: a literal to replace, present exactly once."""
    content = templates.get_template(name).content
    assert content.count(f'"{templates.DEFAULT_NAME}"') == 1


def test_render_replaces_the_name() -> None:
    content = templates.render("minimal", "Acme Platform")
    assert '"Acme Platform"' in content
    assert templates.DEFAULT_NAME not in content


def test_render_without_a_name_is_the_template_verbatim() -> None:
    assert templates.render("minimal") == templates.get_template("minimal").content


def test_unknown_template_lists_the_real_ones() -> None:
    with pytest.raises(templates.TemplateError) as excinfo:
        templates.get_template("nope")
    assert "minimal" in str(excinfo.value)


# --- the command ----------------------------------------------------------


def test_new_writes_the_default_template(tmp_path: Path) -> None:
    runner = CliRunner()
    target = tmp_path / "workspace.dsl"
    result = runner.invoke(cli, ["new", str(target)])
    assert result.exit_code == 0, result.output
    assert target.read_text() == templates.get_template("minimal").content


def test_new_creates_missing_parents(tmp_path: Path) -> None:
    target = tmp_path / "a" / "b" / "workspace.dsl"
    result = CliRunner().invoke(cli, ["new", str(target)])
    assert result.exit_code == 0, result.output
    assert target.is_file()


def test_new_refuses_to_clobber(tmp_path: Path) -> None:
    """Same rule the webapp's write path holds to: this is someone's work."""
    target = tmp_path / "workspace.dsl"
    target.write_text("// mine\n")
    result = CliRunner().invoke(cli, ["new", str(target)])
    assert result.exit_code != 0
    assert "already exists" in result.output
    assert target.read_text() == "// mine\n"


def test_new_force_overwrites(tmp_path: Path) -> None:
    target = tmp_path / "workspace.dsl"
    target.write_text("// mine\n")
    result = CliRunner().invoke(cli, ["new", str(target), "--force"])
    assert result.exit_code == 0, result.output
    assert "workspace" in target.read_text()


def test_new_applies_the_name(tmp_path: Path) -> None:
    target = tmp_path / "workspace.dsl"
    result = CliRunner().invoke(
        cli, ["new", str(target), "--template", "full-c4", "--name", "Acme"]
    )
    assert result.exit_code == 0, result.output
    assert '"Acme"' in target.read_text()


def test_new_rejects_an_unknown_template(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        cli, ["new", str(tmp_path / "w.dsl"), "--template", "nope"]
    )
    assert result.exit_code != 0
    assert "Unknown template" in result.output
    assert not (tmp_path / "w.dsl").exists()


def test_new_list_writes_nothing(tmp_path: Path) -> None:
    target = tmp_path / "workspace.dsl"
    result = CliRunner().invoke(cli, ["new", str(target), "--list"])
    assert result.exit_code == 0
    for name in ALL_TEMPLATES:
        assert name in result.output
    assert not target.exists()
