"""Parse problems must be structured, positioned, and attributed."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from pystructurizr.diagnostics import Diagnostic, Severity
from pystructurizr.parser.dsl import ParseError, parse_dsl, parse_dsl_file

SPLIT = Path(__file__).parent.parent / "fixtures" / "split_workspace"


def test_diagnostic_renders_and_serialises() -> None:
    diagnostic = Diagnostic(
        message="something went wrong",
        severity=Severity.WARNING,
        path=Path("/tmp/a.dsl"),
        line=7,
        code="unsupported-block",
    )

    assert str(diagnostic) == "/tmp/a.dsl:7: something went wrong"
    assert diagnostic.to_dict() == {
        "path": "/tmp/a.dsl",
        "line": 7,
        "column": None,
        "endColumn": None,
        "severity": "warning",
        "code": "unsupported-block",
        "message": "something went wrong",
    }


def test_parse_error_carries_position_as_data() -> None:
    """The line is a field, not something to scrape out of the message."""
    with pytest.raises(ParseError) as excinfo:
        parse_dsl('workspace "T" {\n    model {\n        u = person\n')

    error = excinfo.value
    assert error.line == 4
    assert "Line 4" not in error.message
    assert error.as_diagnostic().severity is Severity.ERROR


def test_parse_error_from_a_file_names_the_file(tmp_path: Path) -> None:
    source = tmp_path / "broken.dsl"
    source.write_text('workspace "T" {\n    model {\n        u = person\n')

    with pytest.raises(ParseError) as excinfo:
        parse_dsl_file(source)

    assert excinfo.value.path == source.resolve()


def test_warnings_are_diagnostics_with_a_code_and_line() -> None:
    workspace = parse_dsl(
        'workspace "T" {\n'
        "    model {\n"
        "        mystery {\n"
        '            "a" "b"\n'
        "        }\n"
        '        u = person "User"\n'
        "    }\n"
        "}\n"
    )

    [diagnostic] = workspace.diagnostics
    assert diagnostic.severity is Severity.WARNING
    assert diagnostic.code == "unsupported-block"
    assert diagnostic.line == 3
    # The legacy string list is still populated for existing callers.
    assert workspace.parse_warnings


def test_script_directive_keeps_later_line_numbers_intact() -> None:
    """Stripping ``!script`` must not shift the lines that follow it.

    The block is replaced by blank lines rather than removed, so a problem
    after it is still reported where the user can see it.
    """
    workspace = parse_dsl(
        'workspace "T" {\n'
        "    model {\n"
        "        !script groovy {\n"
        "            noop()\n"
        "        }\n"
        "        mystery {\n"
        '            "a" "b"\n'
        "        }\n"
        '        u = person "User"\n'
        "    }\n"
        "}\n"
    )

    by_code = {d.code: d for d in workspace.diagnostics}
    assert by_code["unsupported-directive"].line == 3
    # Line 6 in the original source, which only holds if stripping the
    # script block preserved the line count.
    assert by_code["unsupported-block"].line == 6


def test_problem_inside_an_include_names_the_fragment(tmp_path: Path) -> None:
    """``!include`` is flattened before tokenising; the map undoes that.

    Without it the problem is reported against a line of the root file that
    does not contain it — and often a line the root file does not have.
    """
    workspace_dir = tmp_path / "ws"
    shutil.copytree(SPLIT, workspace_dir)
    fragment = workspace_dir / "model" / "people.dsl"
    lines = fragment.read_text().splitlines()
    lines.insert(1, '    mystery {\n        "a" "b"\n    }')
    fragment.write_text("\n".join(lines) + "\n")

    workspace = parse_dsl_file(workspace_dir / "workspace.dsl")

    [diagnostic] = workspace.diagnostics
    assert diagnostic.path is not None
    assert Path(diagnostic.path).resolve() == fragment.resolve()
    assert diagnostic.line == 2
    # The model still parses around the unknown block.
    assert [p.name for p in workspace.people] == ["User"]


def test_tokeniser_records_columns() -> None:
    from pystructurizr.parser.dsl import _tokenize

    tokens = _tokenize('workspace "T" {\n    model {\n')
    by_value = {t.value: t for t in tokens}

    assert (by_value["workspace"].line, by_value["workspace"].column) == (1, 1)
    assert by_value["workspace"].end_column == 10
    assert (by_value["model"].line, by_value["model"].column) == (2, 5)
    assert by_value["model"].end_column == 10


def test_columns_survive_multi_line_tokens() -> None:
    """A token spanning lines must reset the column origin, not just the line.

    Block comments are the common case; without advancing the line origin
    for every token, everything after one is reported at a column offset by
    the comment's length.
    """
    from pystructurizr.parser.dsl import _tokenize

    tokens = _tokenize("a\n/* spanning\n   comment */ b\nc")
    by_value = {t.value: t for t in tokens}

    assert (by_value["b"].line, by_value["b"].column) == (3, 15)
    assert (by_value["c"].line, by_value["c"].column) == (4, 1)


def test_error_underlines_the_offending_token() -> None:
    with pytest.raises(ParseError) as excinfo:
        parse_dsl('workspace "T" {\n    model {\n        u = person "U"\n')

    error = excinfo.value
    assert error.column is not None
    assert error.end_column is not None
    assert error.end_column >= error.column


def test_warning_underlines_the_skipped_construct() -> None:
    workspace = parse_dsl(
        'workspace "T" {\n'
        "    model {\n"
        "        mystery {\n"
        '            "a" "b"\n'
        "        }\n"
        "    }\n"
        "}\n"
    )

    [diagnostic] = workspace.diagnostics
    # "mystery" starts at column 9 and is seven characters long.
    assert (diagnostic.line, diagnostic.column, diagnostic.end_column) == (3, 9, 16)
