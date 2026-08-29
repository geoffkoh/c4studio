"""Tests for !const/!var substitution and !script stripping (Phase 6)."""

from pathlib import Path

import pytest

from c4studio.parser.dsl import (
    ParseError,
    UnsupportedFeatureWarning,
    parse_dsl,
    parse_dsl_file,
)


def test_const_substitution_in_strings() -> None:
    dsl = """
    !const SYSTEM_NAME "Payment System"
    workspace "W" {
        model {
            s = softwareSystem "${SYSTEM_NAME}" "Handles ${SYSTEM_NAME} payments"
        }
    }
    """
    ws = parse_dsl(dsl)
    system = ws.software_systems[0]
    assert system.name == "Payment System"
    assert system.description == "Handles Payment System payments"


def test_var_redefinition_last_wins() -> None:
    dsl = """
    !var ENV "dev"
    !var ENV "prod"
    workspace "W" {
        model {
            s = softwareSystem "S ${ENV}"
        }
    }
    """
    ws = parse_dsl(dsl)
    assert ws.software_systems[0].name == "S prod"


def test_const_redefinition_raises() -> None:
    dsl = """
    !const NAME "one"
    !const NAME "two"
    workspace "W" { model { } }
    """
    with pytest.raises(ParseError, match="NAME"):
        parse_dsl(dsl)


def test_var_cannot_override_const() -> None:
    dsl = """
    !const NAME "one"
    !var NAME "two"
    workspace "W" { model { } }
    """
    with pytest.raises(ParseError, match="NAME"):
        parse_dsl(dsl)


def test_unknown_placeholder_left_intact() -> None:
    dsl = """
    workspace "W" {
        model {
            s = softwareSystem "Uses ${UNDEFINED}"
        }
    }
    """
    ws = parse_dsl(dsl)
    assert ws.software_systems[0].name == "Uses ${UNDEFINED}"


def test_const_from_included_file(tmp_path: Path) -> None:
    (tmp_path / "constants.dsl").write_text('!const ORG "Acme"\n', encoding="utf-8")
    main = tmp_path / "workspace.dsl"
    main.write_text(
        """
        !include constants.dsl
        workspace "${ORG} Workspace" {
            model {
                s = softwareSystem "${ORG} System"
            }
        }
        """,
        encoding="utf-8",
    )
    ws = parse_dsl_file(main)
    assert ws.name == "Acme Workspace"
    assert ws.software_systems[0].name == "Acme System"


def test_script_block_stripped_with_warning() -> None:
    dsl = """
    workspace "W" {
        model {
            u = person "User"
            !script groovy {
                def label = "unbalanced { brace inside string"
                workspace.model.addPerson("Scripted")
            }
            s = softwareSystem "S"
            u -> s "Uses"
        }
    }
    """
    with pytest.warns(UnsupportedFeatureWarning, match="script"):
        ws = parse_dsl(dsl)
    # The script body must not leak tokens into the model.
    assert [p.name for p in ws.people] == ["User"]
    assert [s.name for s in ws.software_systems] == ["S"]
    assert len(ws.relationships) == 1
    assert any("!script" in w for w in ws.parse_warnings)


def test_script_with_nested_braces_stripped() -> None:
    dsl = """
    workspace "W" {
        model {
            !script kotlin {
                if (true) { println("nested { } braces") }
            }
            s = softwareSystem "S"
        }
    }
    """
    with pytest.warns(UnsupportedFeatureWarning):
        ws = parse_dsl(dsl)
    assert [s.name for s in ws.software_systems] == ["S"]


def test_constants_do_not_substitute_inside_scripts() -> None:
    dsl = """
    !const NAME "X"
    workspace "W" {
        model {
            !script groovy {
                def a = "${NAME}"
            }
            s = softwareSystem "${NAME}"
        }
    }
    """
    with pytest.warns(UnsupportedFeatureWarning):
        ws = parse_dsl(dsl)
    assert ws.software_systems[0].name == "X"
