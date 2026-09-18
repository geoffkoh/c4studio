"""`list-perspectives` feeds the VS Code preview's picker (PP-183).

Its own command rather than a field on `list-views --json`: perspectives
belong to the model, not to a view, and that JSON is an array whose shape
other tools already read.
"""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from c4studio.cli.main import cli

WITH_PERSPECTIVES = """
workspace "W" {
    model {
        a = softwareSystem "A" {
            perspectives {
                "Security" "TLS everywhere" "High"
                "Ownership" "Team A" "team-a"
            }
        }
        b = softwareSystem "B"
        a -> b "Calls" {
            perspectives {
                "Reliability" "Retried" "Medium"
            }
        }
    }
    views {
        systemLandscape "L" {
            include *
        }
    }
}
"""

WITHOUT = """
workspace "W" {
    model {
        a = softwareSystem "A"
    }
    views {
        systemLandscape "L" {
            include *
        }
    }
}
"""


def _write(tmp_path: Path, text: str) -> Path:
    source = tmp_path / "ws.dsl"
    source.write_text(text, encoding="utf-8")
    return source


def test_json_lists_every_name_sorted(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        cli, ["list-perspectives", str(_write(tmp_path, WITH_PERSPECTIVES)), "--json"]
    )
    assert result.exit_code == 0
    # Relationships contribute too, which is why the picker cannot be
    # built from elements alone.
    assert json.loads(result.output) == ["Ownership", "Reliability", "Security"]


def test_the_plain_output_is_one_name_per_line(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        cli, ["list-perspectives", str(_write(tmp_path, WITH_PERSPECTIVES))]
    )
    assert result.output.split() == ["Ownership", "Reliability", "Security"]


def test_a_model_with_none_says_so(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        cli, ["list-perspectives", str(_write(tmp_path, WITHOUT))]
    )
    assert result.exit_code == 0
    assert "No perspectives found" in result.output


def test_json_with_none_is_an_empty_array(tmp_path: Path) -> None:
    """The picker reads this: an empty list means nothing to offer."""
    result = CliRunner().invoke(
        cli, ["list-perspectives", str(_write(tmp_path, WITHOUT)), "--json"]
    )
    assert json.loads(result.output) == []


def test_every_name_is_one_render_would_accept(tmp_path: Path) -> None:
    """The picker must not offer a name `--perspective` refuses."""
    source = _write(tmp_path, WITH_PERSPECTIVES)
    names = json.loads(
        CliRunner().invoke(cli, ["list-perspectives", str(source), "--json"]).output
    )
    for name in names:
        result = CliRunner().invoke(
            cli, ["render", str(source), "--perspective", name, "--view", "nope"]
        )
        # The view is what fails here, never the perspective.
        assert "No perspective named" not in result.output
