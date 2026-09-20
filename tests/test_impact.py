"""Impact analysis (PP-189).

The walk is easy; the semantics are the part worth pinning. Containment
counts as involvement, because a relationship declared against a
container is one its system takes part in — the same rule the views apply
when they lift an edge to the nearest visible ancestor. An answer that
ignored the hierarchy would disagree with the diagrams it is about.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from c4studio.cli.main import cli
from c4studio.impact import Hop, analyse, views_containing
from c4studio.parser.dsl import parse_dsl, parse_dsl_file

SAMPLES = Path(__file__).parent.parent / "samples"

CHAIN = """
workspace "W" {
    model {
        u = person "User" "Buys"
        shop = softwareSystem "Shop" "Sells" {
            web = container "Web" "UI" "React"
            api = container "API" "Logic" "Python"
            db = container "DB" "Store" "PostgreSQL"
            web -> api "Calls"
            api -> db "Reads"
        }
        partner = softwareSystem "Partner" "Third party"
        u -> web "Uses"
        api -> partner "Calls"
    }
    views {
        systemLandscape "Landscape" {
            include *
        }
        container shop "Containers" {
            include *
        }
    }
}
"""


def _ids(hops: list[Hop]) -> list[str]:
    return [hop.id for hop in hops]


class TestDirections:
    def test_dependents_are_what_reach_it(self) -> None:
        result = analyse(parse_dsl(CHAIN), "db")
        # web -> api -> db, and the user through the web.
        assert _ids(result.dependents) == ["api", "web", "u"]

    def test_dependencies_are_what_it_reaches(self) -> None:
        result = analyse(parse_dsl(CHAIN), "web")
        assert _ids(result.dependencies) == ["api", "db", "partner"]

    def test_depth_is_the_number_of_relationships(self) -> None:
        result = analyse(parse_dsl(CHAIN), "db")
        depths = {hop.id: hop.depth for hop in result.dependents}
        assert depths == {"api": 1, "web": 2, "u": 3}

    def test_depth_can_be_limited(self) -> None:
        result = analyse(parse_dsl(CHAIN), "db", depth=1)
        assert _ids(result.dependents) == ["api"]

    def test_the_two_directions_do_not_bleed(self) -> None:
        """`db` depends on nothing; plenty depends on it."""
        result = analyse(parse_dsl(CHAIN), "db")
        assert result.dependencies == []
        assert result.dependents


class TestContainment:
    def test_a_relationship_on_a_child_involves_the_parent(self) -> None:
        """`u -> web`, so a change to the shop can reach the user."""
        result = analyse(parse_dsl(CHAIN), "shop")
        assert "u" in _ids(result.dependents)
        assert "partner" in _ids(result.dependencies)

    def test_the_element_s_own_family_is_not_an_impact_on_itself(self) -> None:
        """A container is not 'affected by' the system that holds it."""
        result = analyse(parse_dsl(CHAIN), "api")
        assert "shop" not in _ids(result.dependents) + _ids(result.dependencies)
        assert "api" not in _ids(result.dependents)

    def test_reaching_a_child_reaches_its_parent_too(self) -> None:
        """What a diagram shows: an edge into `web` lands on the Shop."""
        result = analyse(parse_dsl(CHAIN), "u")
        assert "shop" in _ids(result.dependencies)

    def test_an_implied_relationship_is_not_counted_twice(self) -> None:
        source = CHAIN.replace(
            "    model {", "    model {\n        !impliedRelationships true"
        )
        result = analyse(parse_dsl(source), "db")
        assert len(_ids(result.dependents)) == len(set(_ids(result.dependents)))


class TestViews:
    def test_it_names_the_views_that_draw_the_element(self) -> None:
        workspace = parse_dsl(CHAIN)
        assert views_containing(workspace, "api") == ["Containers"]
        # The system appears on both; the container only on its own view.
        assert views_containing(workspace, "shop") == ["Landscape", "Containers"]

    def test_an_element_no_view_draws_reports_none(self) -> None:
        """Worth knowing: the model says it exists, no diagram shows it."""
        workspace = parse_dsl(
            """
            workspace "W" {
                model {
                    shop = softwareSystem "Shop" "Sells" {
                        web = container "Web" "UI" "React"
                    }
                    hidden = softwareSystem "Hidden" "In no view"
                }
                views {
                    container shop "Containers" {
                        include *
                    }
                }
            }
            """
        )
        assert views_containing(workspace, "hidden") == []
        assert views_containing(workspace, "web") == ["Containers"]


class TestCli:
    def test_the_text_output_answers_the_question(self) -> None:
        result = CliRunner().invoke(
            cli, ["impact", str(SAMPLES / "logistics_network.dsl"), "bookingApi"]
        )
        assert result.exit_code == 0
        assert "Depends on it" in result.output
        assert "It depends on" in result.output
        assert "Drawn in" in result.output

    def test_json_carries_hops_and_views(self) -> None:
        result = CliRunner().invoke(
            cli,
            ["impact", str(SAMPLES / "logistics_network.dsl"), "bookingApi", "--json"],
        )
        payload = json.loads(result.output)
        assert payload["element"]["name"] == "Booking API"
        assert payload["views"]
        assert all("depth" in hop for hop in payload["dependents"])

    def test_an_unknown_identifier_says_where_to_find_them(self) -> None:
        result = CliRunner().invoke(
            cli, ["impact", str(SAMPLES / "logistics_network.dsl"), "nope"]
        )
        assert result.exit_code != 0
        assert "No element with identifier 'nope'" in result.output

    @pytest.mark.parametrize(
        "name", ["hedge_fund/workspace.dsl", "logistics_network.dsl"]
    )
    def test_every_element_of_a_sample_can_be_asked_about(self, name: str) -> None:
        """The walk must terminate and stay sane on a real model."""
        workspace = parse_dsl_file(SAMPLES / name)
        for system in workspace.model.software_systems:
            result = analyse(workspace, system.id)
            # Within a direction, once each. *Across* directions an element
            # may appear twice and should: a two-way relationship makes it
            # both something you affect and something that affects you.
            for hops in (result.dependents, result.dependencies):
                ids = _ids(hops)
                assert len(ids) == len(set(ids)), f"{system.id} reported twice"
                assert system.id not in ids
