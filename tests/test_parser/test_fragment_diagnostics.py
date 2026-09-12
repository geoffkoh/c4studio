"""Diagnostics name the file they came from (PP-123).

``!include`` is flattened before tokenising, so every position the parser
sees is a line of one big synthetic source. ``SourceMap`` maps those back,
and ``_warn``/``_record_error`` both run positions through it — so a
problem inside a fragment names the fragment.

That only works when the position travels as a *field*. One call site
formatted the line into the message instead, which left the diagnostic
with no path and no line: a flattened line number, attached to nothing,
that no editor could place.
"""

from __future__ import annotations

import warnings
from collections.abc import Callable
from pathlib import Path

import pytest

from c4studio.diagnostics import Severity
from c4studio.models import Workspace
from c4studio.parser.dsl import ParseError, parse_dsl_file

ROOT = """workspace "Attribution" {
    model {
        !include model/people.dsl
    }
    views {
        systemLandscape Landscape {
            include *
        }
    }
}
"""


@pytest.fixture()
def build(tmp_path: Path) -> Callable[[str], Path]:
    """Return a helper that writes a root plus a fragment and returns the root."""

    def _build(fragment: str) -> Path:
        (tmp_path / "workspace.dsl").write_text(ROOT, encoding="utf-8")
        (tmp_path / "model").mkdir(exist_ok=True)
        (tmp_path / "model" / "people.dsl").write_text(fragment, encoding="utf-8")
        return tmp_path / "workspace.dsl"

    return _build


def _parse(root: Path) -> Workspace:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return parse_dsl_file(root)


def test_an_unsupported_directive_names_the_fragment(
    build: Callable[[str], Path],
) -> None:
    """The regression: this used to be path=None, line=None."""
    root = build('u = person "User"\n!bogus thing\np = person "Other"\n')
    diagnostics = _parse(root).diagnostics

    directive = next(d for d in diagnostics if "unsupported directive" in d.message)
    assert directive.path == root.parent / "model" / "people.dsl"
    assert directive.line == 2
    assert directive.severity is Severity.WARNING
    assert directive.code == "unsupported-directive"


def test_the_line_number_is_not_baked_into_the_message(
    build: Callable[[str], Path],
) -> None:
    """A line in the prose is unplaceable, and was the flattened one."""
    root = build('u = person "User"\n!bogus thing\n')
    directive = next(
        d for d in _parse(root).diagnostics if "unsupported directive" in d.message
    )
    assert not directive.message.startswith("Line ")


def test_the_directive_carries_a_column_range(
    build: Callable[[str], Path],
) -> None:
    """An editor underlines a span, not a whole line."""
    root = build('u = person "User"\n  !bogus thing\n')
    directive = next(
        d for d in _parse(root).diagnostics if "unsupported directive" in d.message
    )
    assert directive.column == 3
    assert directive.end_column is not None
    assert directive.end_column > directive.column


def test_an_error_inside_a_fragment_names_the_fragment(
    build: Callable[[str], Path],
) -> None:
    """Errors already resolved correctly; pinned so they keep doing so."""
    root = build('u = person "User"\nsoftwareSystem\np = person "Other"\n')
    with pytest.raises(ParseError) as caught:
        parse_dsl_file(root)

    fragment = root.parent / "model" / "people.dsl"
    assert any(d.path == fragment and d.line == 2 for d in caught.value.diagnostics), [
        (str(d.path), d.line) for d in caught.value.diagnostics
    ]


def test_a_diagnostic_in_the_root_still_names_the_root(
    build: Callable[[str], Path],
) -> None:
    """Resolution must not push everything into the fragment."""
    root = build('u = person "User"\n')
    root.write_text(
        ROOT.replace("    views {", "    !alsobogus here\n    views {"),
        encoding="utf-8",
    )
    directive = next(
        d for d in _parse(root).diagnostics if "unsupported directive" in d.message
    )
    assert directive.path == root
