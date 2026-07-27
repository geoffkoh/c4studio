"""The check command is the machine-readable face of the parser."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from pystructurizr.cli.main import cli

WARNING_DSL = (
    'workspace "T" {\n'
    "    model {\n"
    "        mystery {\n"
    '            "a" "b"\n'
    "        }\n"
    '        u = person "User"\n'
    "    }\n"
    "}\n"
)

BROKEN_DSL = 'workspace "T" {\n    model {\n        u = person\n'

CLEAN_DSL = 'workspace "T" {\n    model {\n        u = person "User"\n    }\n}\n'


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_clean_file_reports_nothing_and_exits_zero(tmp_path: Path) -> None:
    source = _write(tmp_path, "clean.dsl", CLEAN_DSL)
    result = CliRunner().invoke(cli, ["check", str(source)])

    assert result.exit_code == 0
    assert "no problems found" in result.output


def test_warnings_do_not_fail_the_command(tmp_path: Path) -> None:
    source = _write(tmp_path, "warn.dsl", WARNING_DSL)
    result = CliRunner().invoke(cli, ["check", str(source)])

    assert result.exit_code == 0


def test_strict_fails_on_warnings(tmp_path: Path) -> None:
    source = _write(tmp_path, "warn.dsl", WARNING_DSL)
    result = CliRunner().invoke(cli, ["check", "--strict", str(source)])

    assert result.exit_code == 1


def test_errors_fail_the_command(tmp_path: Path) -> None:
    source = _write(tmp_path, "broken.dsl", BROKEN_DSL)
    result = CliRunner().invoke(cli, ["check", str(source)])

    assert result.exit_code == 1


def test_json_output_is_machine_readable(tmp_path: Path) -> None:
    source = _write(tmp_path, "warn.dsl", WARNING_DSL)
    result = CliRunner().invoke(cli, ["check", "--json", str(source)])

    assert result.exit_code == 0
    [record] = json.loads(result.output)
    assert record["severity"] == "warning"
    assert record["code"] == "unsupported-block"
    assert record["line"] == 3
    # "mystery" starts at column 9; the span underlines the word itself.
    assert record["column"] == 9
    assert record["endColumn"] == 16
    assert Path(record["path"]).name == "warn.dsl"
    assert "Line 3" not in record["message"]


def test_json_output_for_a_hard_error(tmp_path: Path) -> None:
    source = _write(tmp_path, "broken.dsl", BROKEN_DSL)
    result = CliRunner().invoke(cli, ["check", "--json", str(source)])

    assert result.exit_code == 1
    [record] = json.loads(result.output)
    assert record["severity"] == "error"
    assert record["line"] == 4
    assert Path(record["path"]).name == "broken.dsl"
