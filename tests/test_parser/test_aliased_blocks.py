"""Aliased block constructs must not consume their enclosing scope (PP-138).

Found while writing D1's deployment starter template, which produced zero
views: `prod = deploymentEnvironment "Production" { … }` was parsed as if
it were an element, so the parser read a name, met the `{` it did not
expect, dropped one token, and let the body be read as model statements —
with the closing brace ending `model` early.

The rule in CLAUDE.md is absolute and is what these tests pin: *a skipped
construct must never consume its enclosing scope*. The aliased form is
accepted where upstream accepts it, and skipped whole where it is not.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from c4studio.models import ViewType, Workspace
from c4studio.parser.dsl import parse_dsl

HERE = Path(__file__).parent


def _parse(body: str, views: str = "  views {\n  }\n") -> Workspace:
    source = f'workspace "T" {{\n  model {{\n{body}\n    sentinel = softwareSystem "Sentinel"\n  }}\n{views}}}\n'
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return parse_dsl(source, base_dir=HERE, path=HERE / "t.dsl")


ENVIRONMENT = """    s = softwareSystem "S" {
      c = container "C" "d" "t"
    }
    prod = deploymentEnvironment "Production" {
      deploymentNode "Region" "r" "AWS" {
        containerInstance c
      }
    }"""


def test_aliased_deployment_environment_parses() -> None:
    workspace = _parse(ENVIRONMENT)
    assert not workspace.diagnostics, [d.message for d in workspace.diagnostics]
    assert workspace.model.deployment_environments == ["Production"]


def test_aliased_deployment_environment_does_not_eat_the_model() -> None:
    """The defect itself: everything after the block used to vanish."""
    workspace = _parse(ENVIRONMENT)
    assert any(s.name == "Sentinel" for s in workspace.model.software_systems)


def test_a_view_can_name_the_environment_by_its_alias() -> None:
    """Upstream resolves an identifier in the environment slot to its name."""
    workspace = _parse(
        ENVIRONMENT,
        views='  views {\n    deployment s prod "ByAlias" { include * }\n  }\n',
    )
    view = next(v for v in workspace.views if v.key == "ByAlias")
    assert view.type is ViewType.DEPLOYMENT
    assert view.environment == "Production"


def test_the_plain_form_is_unaffected() -> None:
    workspace = _parse(
        ENVIRONMENT.replace("prod = deploymentEnvironment", "deploymentEnvironment")
    )
    assert not workspace.diagnostics
    assert workspace.model.deployment_environments == ["Production"]


@pytest.mark.parametrize(
    ("label", "body"),
    [
        ("group", '    g = group "Team" {\n      a = softwareSystem "A"\n    }'),
        (
            "enterprise",
            '    e = enterprise "Corp" {\n      a = softwareSystem "A"\n    }',
        ),
        ("unknown block", '    x = futureThing "Y" "Z" {\n      whatever\n    }'),
        ("unknown statement", '    x = futureThing "Y"'),
    ],
)
def test_other_aliased_constructs_are_skipped_whole(label: str, body: str) -> None:
    """Not every aliased block is valid, but none may swallow the scope.

    These are skipped and reported rather than parsed — lossy, sound, and
    visible, which is the fail-soft contract.
    """
    workspace = _parse(body)
    assert any(s.name == "Sentinel" for s in workspace.model.software_systems), (
        f"{label} consumed the enclosing model block"
    )
    assert [d.code for d in workspace.diagnostics] == ["unsupported-block"]


def test_the_skip_diagnostic_is_placeable() -> None:
    """It has to be a squiggle: the editor shows these (A3b)."""
    workspace = _parse('    g = group "Team" {\n      a = softwareSystem "A"\n    }')
    diagnostic = workspace.diagnostics[0]
    assert diagnostic.line == 3
    assert diagnostic.path is not None
    assert diagnostic.column is not None
