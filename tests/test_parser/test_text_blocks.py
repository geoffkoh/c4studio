"""Multi-line strings: ``\"\"\"`` text blocks and ``\\`` line continuation (PP-202).

Both are read as structurizr-java's ``StructurizrDslParser.preProcessLines``
reads them. A text block opens with ``\"\"\"`` ending a line and closes at
the next line ending with ``\"\"\"``; its lines lose as much leading
whitespace as the first of them has. A backslash ending a line joins the
next one on, without that line's indentation.

Before this, a text block's content was silently lost — the value read as
``""`` and the content as stray tokens — so these pin the values exactly.
"""

import warnings

import pytest

from c4studio.models.workspace import Workspace
from c4studio.parser.dsl import UnsupportedFeatureWarning, parse_dsl


def _parse(model: str) -> Workspace:
    dsl = 'workspace "W" {\n    model {\n' + model + "\n    }\n}\n"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UnsupportedFeatureWarning)
        return parse_dsl(dsl)


def _properties(model: str) -> dict[str, str]:
    return _parse(model).software_systems[0].properties


class TestTextBlocks:
    def test_a_property_value_keeps_its_lines_without_the_indent(self) -> None:
        props = _properties('''
        s = softwareSystem "S" {
            properties {
                "owner" "team-a"
                "runbook" """
                    ## Restart

                    1. Drain traffic
                       - wait for zero
                    """
                "after" "still read"
            }
        }''')
        assert props == {
            "owner": "team-a",
            "runbook": "## Restart\n\n1. Drain traffic\n   - wait for zero",
            "after": "still read",
        }

    def test_its_content_is_text_not_dsl(self) -> None:
        """Quotes, braces, comment markers and `#` are all just characters."""
        system = _parse('''
        s = softwareSystem "S" {
            description """
                Says "hi" { and } // not a comment
                # nor this
                /* nor this */
                """
        }''').software_systems[0]
        assert system.description == (
            'Says "hi" { and } // not a comment\n# nor this\n/* nor this */'
        )

    def test_text_before_the_closing_quotes_is_dropped_as_upstream_does(
        self,
    ) -> None:
        props = _properties('''
        s = softwareSystem "S" {
            properties {
                "k" """
                    kept
                    dropped"""
            }
        }''')
        assert props == {"k": "kept"}

    def test_as_a_positional_argument(self) -> None:
        system = _parse('''
        s = softwareSystem "S" """
            Line one
            Line two
            """''').software_systems[0]
        assert system.description == "Line one\nLine two"

    def test_a_constant_can_hold_one(self) -> None:
        dsl = '''
        !const NOTES """
            Shared **notes**
            """
        workspace "W" {
            model {
                s = softwareSystem "S" "${NOTES}"
            }
        }
        '''
        assert parse_dsl(dsl).software_systems[0].description == "Shared **notes**"


class TestContinuation:
    def test_a_statement_split_across_lines_is_one_statement(self) -> None:
        """A property's key and value pair by line, so this needs the join.

        Without it the two lines read as two properties, each empty.
        """
        props = _properties("""
        s = softwareSystem "S" {
            properties {
                "key" \\
                    "value"
            }
        }""")
        assert props == {"key": "value"}

    def test_inside_a_string_it_joins_without_the_indent(self) -> None:
        props = _properties("""
        s = softwareSystem "S" {
            properties {
                "notes" "First part, \\
                         second part"
            }
        }""")
        assert props == {"notes": "First part, second part"}

    def test_a_backslash_elsewhere_in_a_string_is_kept(self) -> None:
        props = _properties(r"""
        s = softwareSystem "S" {
            properties {
                "path" "C:\temp"
            }
        }""")
        assert props == {"path": r"C:\temp"}


class TestDiagnosticLines:
    """Joined lines must not shift what a diagnostic points at."""

    @pytest.mark.parametrize(
        "joined",
        [
            'a = softwareSystem "A" """\n    one\n    two\n    """',
            'a = softwareSystem "A" \\\n    "Desc" \\\n    "Tag"',
            'a = softwareSystem "A" "First \\\n    second"',
        ],
        ids=["text block", "continuation", "continuation in a string"],
    )
    def test_a_problem_below_is_reported_on_its_own_line(self, joined: str) -> None:
        workspace = _parse(joined + "\n        oops")
        # Line 1 `workspace`, line 2 `model`, then the joined statement.
        expected = 3 + joined.count("\n") + 1
        assert [d.line for d in workspace.diagnostics] == [expected]

    def test_after_a_constant_holding_a_text_block(self) -> None:
        dsl = '!const N """\n    a\n    b\n    """\nworkspace "W" {\n    model {\n        oops\n    }\n}\n'
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UnsupportedFeatureWarning)
            workspace = parse_dsl(dsl)
        assert [d.line for d in workspace.diagnostics] == [7]
