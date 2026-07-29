"""Malformed DSL must be reported, not silently absorbed.

The failure these guard against is quiet: the file "parses", and the model
simply comes out missing the elements the author thought they wrote.
"""

from __future__ import annotations

import pytest

from pystructurizr.parser.dsl import ParseError, parse_dsl


def _errors(source: str) -> list[str]:
    """Parse and return the messages of every error raised."""
    with pytest.raises(ParseError) as excinfo:
        parse_dsl(source)
    return [d.message for d in excinfo.value.diagnostics]


@pytest.mark.parametrize("keyword", ["person", "softwareSystem"])
def test_model_element_without_a_name_is_an_error(keyword: str) -> None:
    """``<keyword> <name>`` — the name is required, not optional."""
    messages = _errors(
        'workspace "T" {\n    model {\n' f"        x = {keyword}\n" "    }\n}\n"
    )

    assert any("name" in m for m in messages)


def test_container_without_a_name_is_an_error() -> None:
    messages = _errors(
        'workspace "T" {\n'
        "    model {\n"
        '        s = softwareSystem "S" {\n'
        "            c = container\n"
        "        }\n"
        "    }\n"
        "}\n"
    )

    assert any("name" in m for m in messages)


def test_component_without_a_name_is_an_error() -> None:
    messages = _errors(
        'workspace "T" {\n'
        "    model {\n"
        '        s = softwareSystem "S" {\n'
        '            c = container "C" {\n'
        "                x = component\n"
        "            }\n"
        "        }\n"
        "    }\n"
        "}\n"
    )

    assert any("name" in m for m in messages)


def test_child_keyword_in_the_wrong_parent_is_reported() -> None:
    """``x = softwareSystem`` inside a system was consumed without a word."""
    workspace = parse_dsl(
        'workspace "T" {\n'
        "    model {\n"
        '        s = softwareSystem "S" {\n'
        '            x = softwareSystem "Nested"\n'
        "        }\n"
        "    }\n"
        "}\n"
    )

    assert any(d.code == "unexpected-element" for d in workspace.diagnostics)


def test_deployment_environment_without_a_name_is_an_error() -> None:
    messages = _errors(
        'workspace "T" {\n    model {\n        deploymentEnvironment {\n        }\n    }\n}\n'
    )

    assert any("name" in m for m in messages)


def test_relationship_without_a_destination_is_an_error() -> None:
    messages = _errors(
        'workspace "T" {\n'
        "    model {\n"
        '        a = person "A"\n'
        "        a ->\n"
        "    }\n"
        "}\n"
    )

    assert any("destination" in m for m in messages)


def test_unterminated_workspace_is_an_error() -> None:
    """A missing closing brace changes what the file means; say so."""
    messages = _errors(
        'workspace "T" {\n    model {\n        a = person "A"\n    }\n'
    )

    assert any("workspace" in m.lower() for m in messages)


def test_a_valid_workspace_still_reports_nothing() -> None:
    workspace = parse_dsl(
        'workspace "T" {\n'
        "    model {\n"
        '        a = person "A"\n'
        '        s = softwareSystem "S" {\n'
        '            c = container "C" "Does things" "Python"\n'
        "        }\n"
        '        a -> s "Uses"\n'
        '        deploymentEnvironment "Production" {\n'
        '            n = deploymentNode "Node"\n'
        "        }\n"
        "    }\n"
        "}\n"
    )

    assert workspace.diagnostics == []
    assert [p.name for p in workspace.people] == ["A"]
