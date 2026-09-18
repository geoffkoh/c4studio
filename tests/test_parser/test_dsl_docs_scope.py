"""`!docs` and `!adrs` attach where they are written (PP-185).

They used to be stripped out of the source *before tokenising*, which is
why an element-scoped `!docs` silently landed on the workspace: by the
time anything knew about the directive, the context it was written in was
gone. The parser handles them now, so the context is still there.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from c4studio.models import Workspace
from c4studio.parser.dsl import ParseError, parse_dsl, parse_dsl_file


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "01-overview.md").write_text("# Overview\n", "utf-8")
    (tmp_path / "api-docs").mkdir()
    (tmp_path / "api-docs" / "01-api.md").write_text("# The API\n", "utf-8")
    (tmp_path / "adrs").mkdir()
    (tmp_path / "adrs" / "0001-use-c4.md").write_text(
        "# 1. Use C4\n\nDate: 2026-01-01\n\n## Status\n\nAccepted\n", "utf-8"
    )
    return tmp_path


def _parse(root: Path, body: str) -> Workspace:
    source = root / "ws.dsl"
    source.write_text(body, encoding="utf-8")
    return parse_dsl_file(source)


WORKSPACE_LEVEL = """
workspace "W" {
    !docs docs
    !adrs adrs
    model {
        s = softwareSystem "S"
    }
    views {
        systemLandscape "L" {
            include *
        }
    }
}
"""

ELEMENT_LEVEL = """
workspace "W" {
    model {
        s = softwareSystem "S" {
            !docs api-docs
        }
        other = softwareSystem "Other"
    }
    views {
        systemLandscape "L" {
            include *
        }
    }
}
"""


def test_workspace_level_still_attaches_to_the_workspace(root: Path) -> None:
    workspace = _parse(root, WORKSPACE_LEVEL)
    assert [s.title for s in workspace.documentation.sections] == ["Overview"]
    assert len(workspace.documentation.decisions) == 1


def test_an_element_keeps_its_own_documentation(root: Path) -> None:
    workspace = _parse(root, ELEMENT_LEVEL)
    system = next(s for s in workspace.software_systems if s.id == "s")
    assert [s.title for s in system.documentation.sections] == ["The API"]
    # The regression: these used to land here instead.
    assert workspace.documentation.sections == []


def test_another_element_is_not_given_them(root: Path) -> None:
    workspace = _parse(root, ELEMENT_LEVEL)
    other = next(s for s in workspace.software_systems if s.id == "other")
    assert other.documentation.sections == []


def test_both_scopes_at_once(root: Path) -> None:
    workspace = _parse(
        root,
        """
        workspace "W" {
            !docs docs
            model {
                s = softwareSystem "S" {
                    !docs api-docs
                }
            }
            views {
                systemLandscape "L" {
                    include *
                }
            }
        }
        """,
    )
    system = workspace.software_systems[0]
    assert [s.title for s in workspace.documentation.sections] == ["Overview"]
    assert [s.title for s in system.documentation.sections] == ["The API"]


def test_a_container_can_carry_its_own(root: Path) -> None:
    workspace = _parse(
        root,
        """
        workspace "W" {
            model {
                s = softwareSystem "S" {
                    c = container "C" {
                        !docs api-docs
                    }
                }
            }
            views {
                systemLandscape "L" {
                    include *
                }
            }
        }
        """,
    )
    container = workspace.software_systems[0].containers[0]
    assert [s.title for s in container.documentation.sections] == ["The API"]


def test_parsing_a_string_still_says_why_it_cannot(root: Path) -> None:
    """There is no directory to resolve against, and guessing would be worse."""
    with pytest.raises(ParseError, match="requires a file context"):
        parse_dsl(WORKSPACE_LEVEL)
