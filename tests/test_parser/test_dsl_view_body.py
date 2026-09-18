"""View bodies: `parallel`, `paperSize`, and the fallback (PP-186).

`parallel { … }` used to break the parser's own contract — *a skipped
construct must never consume its enclosing scope*. The keyword and its
brace were dropped token by token, and the block's closing brace was then
read as the end of the view, so every step written after it vanished from
the diagram with only two `unexpected-token` diagnostics to show for it.
"""

from __future__ import annotations

import warnings

import pytest

from c4studio.models import PaperSize, ViewType
from c4studio.parser.dsl import UnsupportedFeatureWarning, parse_dsl

DYNAMIC = """
workspace "W" {{
    model {{
        a = softwareSystem "A"
        b = softwareSystem "B"
        c = softwareSystem "C"
        a -> b "x"
        a -> c "y"
    }}
    views {{
        dynamic * "dyn" {{
{body}
        }}
    }}
}}
"""


def _steps(body: str) -> list[tuple[str, str]]:
    workspace = parse_dsl(DYNAMIC.format(body=body))
    view = next(v for v in workspace.views if v.key == "dyn")
    return [(rv.order, rv.description) for rv in view.relationship_views]


class TestParallel:
    def test_steps_after_a_parallel_block_survive(self) -> None:
        """The regression: they used to be dropped from the view."""
        assert _steps(
            """parallel {
                a -> b "one"
                a -> c "two"
            }
            a -> b "after\""""
        ) == [("1", "one"), ("1", "two"), ("2", "after")]

    def test_a_block_shares_one_step_number(self) -> None:
        """Upstream numbers them alike: one moment in the sequence."""
        assert _steps(
            """a -> b "first"
            parallel {
                a -> b "same"
                a -> c "time"
            }"""
        ) == [("1", "first"), ("2", "same"), ("2", "time")]

    def test_sequential_steps_are_unaffected(self) -> None:
        assert _steps(
            """a -> b "one"
            a -> c "two"
            a -> b "three\""""
        ) == [("1", "one"), ("2", "two"), ("3", "three")]

    def test_an_empty_block_costs_a_number_and_nothing_else(self) -> None:
        assert _steps(
            """parallel {
            }
            a -> b "after\""""
        ) == [("2", "after")]


class TestPaperSize:
    def test_it_is_stored(self) -> None:
        workspace = parse_dsl(
            """
            workspace "W" {
                model {
                    a = softwareSystem "A"
                }
                views {
                    systemLandscape "L" {
                        include *
                        paperSize A4_Landscape
                    }
                }
            }
            """
        )
        view = next(iter(workspace.views))
        assert view.paper_size is PaperSize.A4_LANDSCAPE

    def test_an_unknown_size_is_reported_rather_than_dropped(self) -> None:
        with pytest.warns(UnsupportedFeatureWarning):
            workspace = parse_dsl(
                """
                workspace "W" {
                    model {
                        a = softwareSystem "A"
                    }
                    views {
                        systemLandscape "L" {
                            include *
                            paperSize A9_Origami
                        }
                    }
                }
                """
            )
        [diagnostic] = workspace.diagnostics
        assert diagnostic.code == "unknown-paper-size"
        assert next(iter(workspace.views)).paper_size is None


class TestUnknownConstructs:
    def test_an_unknown_block_does_not_eat_the_view(self) -> None:
        """The contract, now held by the view body as well."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            workspace = parse_dsl(
                """
                workspace "W" {
                    model {
                        a = softwareSystem "A"
                        b = softwareSystem "B"
                        a -> b "x"
                    }
                    views {
                        systemLandscape "L" {
                            bogusBlock {
                                whatever
                            }
                            include *
                            title "Still here"
                        }
                    }
                }
                """
            )
        view = next(iter(workspace.views))
        # Everything after the unknown block still belongs to the view.
        assert view.include_all is True
        assert view.title == "Still here"
        assert {d.code for d in workspace.diagnostics} == {"unsupported-block"}

    def test_parallel_outside_a_dynamic_view_is_skipped_whole(self) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            workspace = parse_dsl(
                """
                workspace "W" {
                    model {
                        a = softwareSystem "A"
                    }
                    views {
                        systemLandscape "L" {
                            parallel {
                                a
                            }
                            include *
                        }
                    }
                }
                """
            )
        view = next(iter(workspace.views))
        assert view.type is ViewType.SYSTEM_LANDSCAPE
        assert view.include_all is True
        assert {d.code for d in workspace.diagnostics} == {"unsupported-block"}
