"""In-memory source overlay for ``!include`` (PP-121).

The seam an editor needs. A fragment is not a valid workspace on its own,
so checking an unsaved buffer means parsing its *root* with the buffer
substituted for the file the root includes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from c4studio.parser.dsl import ParseError, parse_dsl, parse_dsl_file

ROOT = """workspace "Overlay" {
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

FRAGMENT = 'u = person "User" "From disk"\n'


@pytest.fixture()
def workspace_root(tmp_path: Path) -> Path:
    (tmp_path / "workspace.dsl").write_text(ROOT, encoding="utf-8")
    (tmp_path / "model").mkdir()
    (tmp_path / "model" / "people.dsl").write_text(FRAGMENT, encoding="utf-8")
    return tmp_path / "workspace.dsl"


def test_without_an_overlay_nothing_changes(workspace_root: Path) -> None:
    workspace = parse_dsl_file(workspace_root)
    assert [p.description for p in workspace.people] == ["From disk"]


def test_overlay_replaces_an_include_target(workspace_root: Path) -> None:
    """The unsaved buffer wins over what is on disk."""
    fragment = workspace_root.parent / "model" / "people.dsl"
    workspace = parse_dsl(
        workspace_root.read_text(encoding="utf-8"),
        base_dir=workspace_root.parent,
        path=workspace_root,
        overlay={fragment.resolve(): 'u = person "User" "Unsaved edit"\n'},
    )
    assert [p.description for p in workspace.people] == ["Unsaved edit"]
    # Disk is untouched — the overlay is a read-time substitution only.
    assert fragment.read_text(encoding="utf-8") == FRAGMENT


def test_overlay_resolves_a_target_that_does_not_exist_yet(
    workspace_root: Path,
) -> None:
    """Declare the include, then type the fragment — before saving either."""
    root_text = ROOT.replace(
        "!include model/people.dsl",
        "!include model/people.dsl\n        !include model/new.dsl",
    )
    new_fragment = (workspace_root.parent / "model" / "new.dsl").resolve()
    assert not new_fragment.exists()

    workspace = parse_dsl(
        root_text,
        base_dir=workspace_root.parent,
        path=workspace_root,
        overlay={new_fragment: 's = softwareSystem "Typed but unsaved"\n'},
    )
    assert [s.name for s in workspace.software_systems] == ["Typed but unsaved"]


def test_a_missing_target_without_an_overlay_still_raises(
    workspace_root: Path,
) -> None:
    root_text = ROOT.replace("!include model/people.dsl", "!include model/absent.dsl")
    with pytest.raises(ParseError, match="!include target not found"):
        parse_dsl(root_text, base_dir=workspace_root.parent, path=workspace_root)


def test_an_error_in_the_overlaid_text_is_reported(workspace_root: Path) -> None:
    """A buffer that does not parse reports, rather than silently passing.

    Note what is *not* asserted: which file the diagnostic names. Errors
    raised with an explicit path skip ``SourceMap`` resolution, so one
    from inside a fragment is currently attributed to the root at the
    flattened line — pre-existing and identical for an include read from
    disk, so not this change's to fix. It is a prerequisite for the
    editor's inline squiggles and has its own ticket; see
    ``docs/studio-editor-plan.md``.
    """
    fragment = (workspace_root.parent / "model" / "people.dsl").resolve()
    with pytest.raises(ParseError) as caught:
        parse_dsl(
            workspace_root.read_text(encoding="utf-8"),
            base_dir=workspace_root.parent,
            path=workspace_root,
            overlay={fragment: 'u = person "User"\nu -> \n'},
        )
    assert caught.value.diagnostics, "the overlaid text was not actually parsed"


def test_the_root_itself_can_be_overlaid(workspace_root: Path) -> None:
    """An unsaved root buffer needs no special case — it is just the text."""
    workspace = parse_dsl(
        ROOT.replace("Overlay", "Renamed"),
        base_dir=workspace_root.parent,
        path=workspace_root,
    )
    assert workspace.name == "Renamed"
