"""Unknown constructs must be skipped, never allowed to eat their scope."""

from __future__ import annotations

from c4studio.parser.dsl import parse_dsl


def test_model_level_properties_are_parsed() -> None:
    """``properties`` inside ``model`` populates the model's properties."""
    workspace = parse_dsl(
        """
        workspace "T" {
            model {
                properties {
                    "owner" "platform-team"
                    "tier" "1"
                }
                u = person "User"
            }
        }
        """
    )

    assert workspace.model.properties["owner"] == "platform-team"
    assert workspace.model.properties["tier"] == "1"
    # The rest of the model must survive the block.
    assert [p.name for p in workspace.people] == ["User"]


def test_unknown_block_in_model_does_not_swallow_the_rest() -> None:
    """An unrecognised block is skipped whole, with a warning, in place.

    Previously the fallback dropped one token at a time, so the unknown
    block's closing brace terminated the enclosing ``model`` block and every
    element after it was silently discarded.
    """
    workspace = parse_dsl(
        """
        workspace "T" {
            model {
                mysteryBlock {
                    "something" "unrecognised"
                }
                u = person "User"
                s = softwareSystem "System"
            }
        }
        """
    )

    assert [p.name for p in workspace.people] == ["User"]
    assert [s.name for s in workspace.software_systems] == ["System"]
    assert any("mysteryBlock" in w for w in workspace.parse_warnings)


def test_nested_unknown_block_is_skipped_whole() -> None:
    """Skipping is brace-balanced, so nesting does not confuse it."""
    workspace = parse_dsl(
        """
        workspace "T" {
            model {
                mystery {
                    inner {
                        "a" "b"
                    }
                }
                u = person "User"
            }
        }
        """
    )

    assert [p.name for p in workspace.people] == ["User"]


def test_unknown_bare_token_still_warns() -> None:
    """A stray token with no block is skipped and reported, not ignored."""
    workspace = parse_dsl(
        """
        workspace "T" {
            model {
                gibberish
                u = person "User"
            }
        }
        """
    )

    assert [p.name for p in workspace.people] == ["User"]
    assert any("gibberish" in w for w in workspace.parse_warnings)


def test_unknown_block_at_workspace_scope_does_not_swallow_the_model() -> None:
    workspace = parse_dsl(
        """
        workspace "T" {
            mystery {
                "a" "b"
            }
            model {
                u = person "User"
            }
        }
        """
    )

    assert [p.name for p in workspace.people] == ["User"]
    assert any("workspace" in w for w in workspace.parse_warnings)


def test_unknown_block_in_views_does_not_swallow_later_views() -> None:
    workspace = parse_dsl(
        """
        workspace "T" {
            model {
                u = person "User"
            }
            views {
                mystery {
                    "a" "b"
                }
                systemLandscape Landscape {
                    include *
                }
            }
        }
        """
    )

    assert [v.key for v in workspace.views] == ["Landscape"]
    assert any("views" in w for w in workspace.parse_warnings)


def test_unknown_block_in_an_element_body_does_not_swallow_children() -> None:
    workspace = parse_dsl(
        """
        workspace "T" {
            model {
                s = softwareSystem "System" {
                    mystery {
                        "a" "b"
                    }
                    c = container "Container"
                }
                u = person "User"
            }
        }
        """
    )

    system = workspace.software_systems[0]
    assert [c.name for c in system.containers] == ["Container"]
    assert [p.name for p in workspace.people] == ["User"]
    assert any("softwaresystem" in w for w in workspace.parse_warnings)
