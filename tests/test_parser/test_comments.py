"""Comment handling: ``//``, ``/* */`` and full-line ``#`` (PP-112).

structurizr-java's comment pattern is ``^\\s*?(//|#).*$`` — a ``#`` only
starts a comment when nothing but whitespace precedes it on the line,
because hex colours (``background #1a2b3c``) put ``#`` mid-line. These
tests pin both halves of that contract.
"""

from __future__ import annotations

from c4studio.parser.dsl import parse_dsl


def test_full_line_hash_comment_is_ignored() -> None:
    ws = parse_dsl(
        """
        # a comment before the workspace
        workspace "W" {
            # indented comment
            model {
# flush-left comment
                a = person "A"
            }
        }
        """
    )
    assert ws.diagnostics == []
    assert [p.name for p in ws.model.people] == ["A"]


def test_hash_comment_on_the_first_line_of_the_file() -> None:
    ws = parse_dsl('# leading comment\nworkspace "W" {\n    model { }\n}\n')
    assert ws.diagnostics == []
    assert ws.name == "W"


def test_hash_comment_with_braces_does_not_disturb_scope() -> None:
    """An unbalanced brace inside a comment must not open or close blocks."""
    ws = parse_dsl(
        """
        workspace "W" {
            model {
                # { this brace is commentary, not scope
                a = person "A"
                # } and so is this one
                b = softwareSystem "B"
            }
        }
        """
    )
    assert ws.diagnostics == []
    assert [p.name for p in ws.model.people] == ["A"]
    assert [s.name for s in ws.model.software_systems] == ["B"]


def test_mid_line_hash_is_still_a_colour() -> None:
    """The comment rule is full-line only: hex colours keep working."""
    ws = parse_dsl(
        """
        workspace "W" {
            model {
                a = person "A"
            }
            views {
                styles {
                    element "Person" {
                        background #1a2b3c
                        color #fff
                    }
                }
            }
        }
        """
    )
    assert ws.diagnostics == []
    style = ws.views.configuration.styles.element_styles[0]
    assert style.background == "#1a2b3c"
    assert style.color == "#fff"


def test_double_slash_and_block_comments_still_work() -> None:
    ws = parse_dsl(
        """
        workspace "W" {
            // line comment
            model {
                /* block
                   comment */
                a = person "A" // trailing comment
            }
        }
        """
    )
    assert ws.diagnostics == []
    assert [p.name for p in ws.model.people] == ["A"]
