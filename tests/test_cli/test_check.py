"""The check command is the machine-readable face of the parser."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from c4studio.cli.main import _read_stdin_text, cli
from c4studio.parser.dsl import parse_dsl

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

BROKEN_DSL = 'workspace "T"\n    model {\n    }\n'

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
    assert record["line"] == 2
    assert Path(record["path"]).name == "broken.dsl"


def test_json_reports_every_error(tmp_path: Path) -> None:
    source = _write(
        tmp_path,
        "two.dsl",
        'workspace "T" {\n    views systemContext\n    views component\n}\n',
    )
    result = CliRunner().invoke(cli, ["check", "--json", str(source)])

    assert result.exit_code == 1
    records = json.loads(result.output)
    assert [r["line"] for r in records] == [2, 3]
    assert {r["severity"] for r in records} == {"error"}


def test_check_reads_dsl_from_stdin(tmp_path: Path) -> None:
    """`check -` lets an editor check an unsaved buffer."""
    result = CliRunner().invoke(cli, ["check", "-", "--json"], input=WARNING_DSL)

    assert result.exit_code == 0
    [record] = json.loads(result.output)
    assert record["code"] == "unsupported-block"
    assert record["line"] == 3


def test_stdin_is_decoded_as_utf8_whatever_the_locale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A piped buffer decodes like a file on disk, not like the locale.

    Every DSL read from disk is decoded UTF-8 explicitly, so stdin has to
    match or the same workspace parses two ways depending on where it came
    from. `sys.stdin.read()` would not: its encoding follows the locale.

    The stdin built here is what a latin-1 locale hands a process — correct
    UTF-8 bytes wrapped in a stream that will mis-decode them. Read through
    the text layer, "Ünïcodé" arrives as "ÃœnÃ¯codÃ©".
    """
    dsl = 'workspace "T" {\n    model {\n        u = person "Ünïcodé"\n    }\n}\n'
    mis_decoding = io.TextIOWrapper(io.BytesIO(dsl.encode("utf-8")), encoding="latin-1")
    monkeypatch.setattr(sys, "stdin", mis_decoding)

    workspace = parse_dsl(_read_stdin_text())

    assert [p.name for p in workspace.people] == ["Ünïcodé"]


def test_stdin_diagnostics_are_attributed_to_the_real_path(tmp_path: Path) -> None:
    """--path names the file being edited, not the pipe.

    Without it an editor cannot place the marker: the diagnostic would have
    no path at all.
    """
    source = tmp_path / "buffer.dsl"
    source.write_text(CLEAN_DSL, encoding="utf-8")  # stale on purpose

    result = CliRunner().invoke(
        cli, ["check", "-", "--path", str(source), "--json"], input=WARNING_DSL
    )

    [record] = json.loads(result.output)
    assert Path(record["path"]) == source
    assert record["code"] == "unsupported-block"


def test_stdin_resolves_includes_against_the_given_path(tmp_path: Path) -> None:
    """Relative !include targets resolve next to --path, not the cwd."""
    (tmp_path / "fragment.dsl").write_text(
        '        u = person "User"\n', encoding="utf-8"
    )
    buffer_source = (
        'workspace "T" {\n    model {\n        !include fragment.dsl\n    }\n}\n'
    )

    result = CliRunner().invoke(
        cli,
        ["check", "-", "--path", str(tmp_path / "workspace.dsl"), "--json"],
        input=buffer_source,
    )

    assert result.exit_code == 0
    assert json.loads(result.output) == []


def test_stdin_errors_still_fail_the_command() -> None:
    result = CliRunner().invoke(cli, ["check", "-", "--json"], input=BROKEN_DSL)

    assert result.exit_code == 1
    assert json.loads(result.output)[0]["severity"] == "error"
