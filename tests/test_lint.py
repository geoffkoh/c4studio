"""Model standards (PP-187).

The rules are only worth having if they are quiet on a good model and
specific on a bad one, so the suite works both ways: each rule gets a
workspace that breaks it and one that does not, and the samples are
checked as a whole to keep the signal-to-noise honest.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from c4studio.cli.main import cli
from c4studio.lint import LintConfig, lint, load_config
from c4studio.models import Workspace
from c4studio.parser.dsl import parse_dsl

SAMPLES = Path(__file__).parent.parent / "samples"

GOOD = """
workspace "W" {
    model {
        u = person "User" "Someone with an account"
        s = softwareSystem "Platform" "Does the work" {
            web = container "Web" "The UI" "React"
            api = container "API" "The surface" "Python"
            web -> api "Calls" "JSON/HTTPS"
        }
        u -> web "Uses"
    }
    views {
        systemLandscape "L" {
            include *
        }
    }
}
"""


def _codes(workspace: Workspace, config: LintConfig | None = None) -> list[str]:
    return [finding.code for finding in lint(workspace, config)]


def _messages(workspace: Workspace) -> list[str]:
    return [finding.message for finding in lint(workspace)]


def test_a_good_model_is_silent() -> None:
    assert lint(parse_dsl(GOOD)) == []


class TestRules:
    def test_missing_description(self) -> None:
        workspace = parse_dsl(GOOD.replace('"Platform" "Does the work"', '"Platform"'))
        assert "missing-description" in _codes(workspace)
        assert "softwareSystem 'Platform' has no description" in _messages(workspace)

    def test_missing_technology_only_applies_below_the_system(self) -> None:
        """People and systems have none by design."""
        workspace = parse_dsl(GOOD.replace('"The UI" "React"', '"The UI"'))
        messages = [m for m in _messages(workspace) if "technology" in m]
        assert messages == ["container 'Web' has no technology"]

    def test_orphan_element(self) -> None:
        workspace = parse_dsl(
            GOOD.replace(
                '            web -> api "Calls" "JSON/HTTPS"\n',
                '            spare = container "Spare" "Unused" "Python"\n',
            )
        )
        assert "container 'Spare' has no relationships" in _messages(workspace)

    def test_a_parent_is_not_an_orphan_when_a_child_is_connected(self) -> None:
        """The false positive that would flag every well-modelled system.

        Relationships are routinely declared at container level while the
        diagram people look at is the context view, which lifts them.
        """
        workspace = parse_dsl(GOOD)
        assert [m for m in _messages(workspace) if "Platform" in m] == []

    def test_a_system_with_nothing_connected_anywhere_is_reported(self) -> None:
        workspace = parse_dsl(
            """
            workspace "W" {
                model {
                    a = softwareSystem "A" "Alone" {
                        c = container "C" "Also alone" "Python"
                    }
                    b = softwareSystem "B" "Connected"
                    d = softwareSystem "D" "Connected"
                    b -> d "Uses"
                }
                views {
                    systemLandscape "L" {
                        include *
                    }
                }
            }
            """
        )
        messages = [m for m in _messages(workspace) if "no relationships" in m]
        # The system is reported; its container is not reported separately,
        # which would be the same problem said twice.
        assert messages == ["softwareSystem 'A' has no relationships"]

    def test_duplicate_relationship(self) -> None:
        workspace = parse_dsl(
            GOOD.replace(
                '        u -> web "Uses"\n',
                '        u -> web "Uses"\n        u -> web "Uses"\n',
            )
        )
        assert "duplicate-relationship" in _codes(workspace)

    def test_two_relationships_with_different_descriptions_are_fine(self) -> None:
        workspace = parse_dsl(
            GOOD.replace(
                '        u -> web "Uses"\n',
                '        u -> web "Uses"\n        u -> web "Signs out of"\n',
            )
        )
        assert "duplicate-relationship" not in _codes(workspace)

    def test_unused_style(self) -> None:
        workspace = parse_dsl(
            GOOD.replace(
                "        systemLandscape",
                """        styles {
            element "Datastore" {
                shape Cylinder
            }
        }
        systemLandscape""",
            )
        )
        assert "element style 'Datastore' matches no element" in _messages(workspace)

    def test_a_style_on_an_implicit_tag_is_used(self) -> None:
        """`Person`, `Container` and friends are carried without being written."""
        workspace = parse_dsl(
            GOOD.replace(
                "        systemLandscape",
                """        styles {
            element "Person" {
                shape Person
            }
            relationship "Relationship" {
                thickness 2
            }
        }
        systemLandscape""",
            )
        )
        assert "unused-style" not in _codes(workspace)

    def test_a_perspective_style_is_never_unused(self) -> None:
        """It matches by perspective name, not by any tag an element has."""
        workspace = parse_dsl(
            GOOD.replace(
                "        systemLandscape",
                """        styles {
            element "Perspective:Security[value==High]" {
                background #d32f2f
            }
        }
        systemLandscape""",
            )
        )
        assert "unused-style" not in _codes(workspace)

    def test_naming_convention_does_nothing_until_configured(self) -> None:
        workspace = parse_dsl(GOOD.replace('"Platform"', '"platform"'))
        assert "naming-convention" not in _codes(workspace)
        config = LintConfig(naming={"softwareSystem": "^[A-Z]"})
        assert "naming-convention" in _codes(workspace, config)


class TestConfiguration:
    def test_ignore_switches_a_rule_off(self) -> None:
        workspace = parse_dsl(GOOD.replace('"Platform" "Does the work"', '"Platform"'))
        assert _codes(workspace, LintConfig(ignore={"missing-description"})) == []

    def test_select_runs_only_what_is_named(self) -> None:
        workspace = parse_dsl(
            GOOD.replace('"Platform" "Does the work"', '"Platform"').replace(
                '"The UI" "React"', '"The UI"'
            )
        )
        codes = set(_codes(workspace, LintConfig(select={"missing-technology"})))
        assert codes == {"missing-technology"}

    def test_config_is_read_from_json(self, tmp_path: Path) -> None:
        path = tmp_path / "c4studio.lint.json"
        path.write_text(
            json.dumps(
                {"ignore": ["orphan-element"], "naming": {"container": "^[A-Z]"}}
            ),
            encoding="utf-8",
        )
        config = load_config(path)
        assert config.ignore == {"orphan-element"}
        assert config.naming == {"container": "^[A-Z]"}

    def test_a_file_that_is_not_an_object_is_empty_config(self, tmp_path: Path) -> None:
        path = tmp_path / "c4studio.lint.json"
        path.write_text("[]", encoding="utf-8")
        assert load_config(path) == LintConfig()

    def test_invalid_json_is_an_error_the_caller_can_explain(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "c4studio.lint.json"
        path.write_text("{not json", encoding="utf-8")
        with pytest.raises(ValueError):
            load_config(path)


class TestCli:
    def _write(self, tmp_path: Path, text: str) -> Path:
        source = tmp_path / "ws.dsl"
        source.write_text(text, encoding="utf-8")
        return source

    def test_a_clean_model_exits_zero(self, tmp_path: Path) -> None:
        result = CliRunner().invoke(cli, ["lint", str(self._write(tmp_path, GOOD))])
        assert result.exit_code == 0
        assert "no findings" in result.output

    def test_findings_exit_one_so_ci_fails(self, tmp_path: Path) -> None:
        source = self._write(tmp_path, GOOD.replace('"Does the work"', '""'))
        result = CliRunner().invoke(cli, ["lint", str(source)])
        assert result.exit_code == 1
        assert "has no description" in result.output

    def test_exit_zero_reports_without_failing(self, tmp_path: Path) -> None:
        """For a first run on a model nobody has linted before."""
        source = self._write(tmp_path, GOOD.replace('"Does the work"', '""'))
        result = CliRunner().invoke(cli, ["lint", str(source), "--exit-zero"])
        assert result.exit_code == 0
        assert "has no description" in result.output

    def test_ignore_on_the_command_line(self, tmp_path: Path) -> None:
        source = self._write(tmp_path, GOOD.replace('"Does the work"', '""'))
        result = CliRunner().invoke(
            cli, ["lint", str(source), "--ignore", "missing-description"]
        )
        assert result.exit_code == 0

    def test_json_output_carries_the_code_and_the_place(self, tmp_path: Path) -> None:
        source = self._write(tmp_path, GOOD.replace('"Does the work"', '""'))
        result = CliRunner().invoke(cli, ["lint", str(source), "--json"])
        [finding] = json.loads(result.output)
        assert finding["code"] == "missing-description"
        # The definition site, so an editor can place a marker.
        assert finding["line"] == 5
        assert finding["path"].endswith("ws.dsl")

    def test_a_config_beside_the_file_is_found(self, tmp_path: Path) -> None:
        source = self._write(tmp_path, GOOD.replace('"Does the work"', '""'))
        (tmp_path / "c4studio.lint.json").write_text(
            json.dumps({"ignore": ["missing-description"]}), encoding="utf-8"
        )
        assert CliRunner().invoke(cli, ["lint", str(source)]).exit_code == 0


class TestSamples:
    """The rules have to be quiet on models that are actually good."""

    @pytest.mark.parametrize(
        "name",
        [
            "hedge_fund/workspace.dsl",
            "internet_banking.dsl",
            "ecommerce_platform.dsl",
            "saas_monitoring.dsl",
            "logistics_network.dsl",
        ],
    )
    def test_the_well_formed_samples_are_clean(self, name: str) -> None:
        result = CliRunner().invoke(cli, ["lint", str(SAMPLES / name)])
        assert result.exit_code == 0, result.output
