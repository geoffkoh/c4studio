"""Tests for the Structurizr workspace JSON exporter."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pystructurizr.generators.json_export import export_json, workspace_to_json
from pystructurizr.models import Location, Shape, ViewType, Workspace
from pystructurizr.parser.dsl import parse_dsl_file
from pystructurizr.parser.json_parser import parse_json, parse_json_file
from collections.abc import Iterator
from pystructurizr.models import DeploymentNode
from pystructurizr.models import SoftwareSystem

FIXTURES = Path(__file__).parent.parent / "fixtures"
SAMPLES = Path(__file__).parent.parent.parent / "samples"


def _relationship_triples(workspace: Workspace) -> set[tuple[str, str, str]]:
    return {
        (r.source_id, r.destination_id, r.description) for r in workspace.relationships
    }


def _element_ids(workspace: Workspace) -> set[str]:
    ids = {p.id for p in workspace.people}
    for system in workspace.software_systems:
        ids.add(system.id)
        for container in system.containers:
            ids.add(container.id)
            ids.update(c.id for c in container.components)
    return ids


@pytest.fixture(scope="module")
def hedge_fund() -> Workspace:
    return parse_dsl_file(SAMPLES / "hedge_fund" / "workspace.dsl")


class TestRoundTrip:
    def test_dsl_workspace_survives_json_round_trip(
        self, hedge_fund: Workspace
    ) -> None:
        reparsed = parse_json(export_json(hedge_fund))

        assert reparsed.name == hedge_fund.name
        assert _element_ids(reparsed) == _element_ids(hedge_fund)
        assert _relationship_triples(reparsed) == _relationship_triples(hedge_fund)
        assert {v.key for v in reparsed.views} == {v.key for v in hedge_fund.views}
        assert {(v.key, v.type) for v in reparsed.views} == {
            (v.key, v.type) for v in hedge_fund.views
        }

    def test_export_is_idempotent_through_reparse(self, hedge_fund: Workspace) -> None:
        # export -> parse -> export must be a fixpoint: anything the second
        # pass would drop or reshape means the first export was lossy.
        once = export_json(hedge_fund)
        assert export_json(parse_json(once)) == once

    def test_json_fixture_round_trips(self) -> None:
        original = parse_json_file(FIXTURES / "example.json")
        reparsed = parse_json(export_json(original))
        assert _element_ids(reparsed) == _element_ids(original)
        assert _relationship_triples(reparsed) == _relationship_triples(original)
        assert export_json(reparsed) == export_json(original)


class TestModelShape:
    def test_relationships_nest_under_their_source_element(
        self, hedge_fund: Workspace
    ) -> None:
        data = workspace_to_json(hedge_fund)["workspace"]
        systems = {s["name"]: s for s in data["model"]["softwareSystems"]}
        oms = systems["Order Management System"]
        containers = {c["name"]: c for c in oms.get("containers", [])}
        blotter = containers["Order Blotter"]
        destinations = {r["destinationId"] for r in blotter.get("relationships", [])}
        assert destinations  # the blotter calls into the order service
        # Nested relationships never repeat the source id.
        assert all("sourceId" not in r for r in blotter.get("relationships", []))

    def test_tags_are_comma_joined_strings(self, hedge_fund: Workspace) -> None:
        data = workspace_to_json(hedge_fund)["workspace"]
        for person in data["model"]["people"]:
            if "tags" in person:
                assert isinstance(person["tags"], str)

    def test_external_location_round_trips_via_tags(self) -> None:
        source = """
        workspace "W" {
            model {
                internal = softwareSystem "Core"
                vendor = softwareSystem "Vendor"
            }
        }
        """
        # The DSL marks externals via Location; JSON carries it as a tag.
        from pystructurizr.parser.dsl import parse_dsl

        workspace = parse_dsl(source)
        vendor = workspace.find_element("vendor")
        assert isinstance(vendor, SoftwareSystem)
        vendor.location = Location.EXTERNAL

        reparsed = parse_json(export_json(workspace))
        again = reparsed.find_element("vendor")
        assert isinstance(again, SoftwareSystem)
        assert again.location == Location.EXTERNAL

    def test_empty_fields_are_omitted(self) -> None:
        from pystructurizr.parser.dsl import parse_dsl

        workspace = parse_dsl('workspace "W" { model { u = person "U" } }')
        person = workspace_to_json(workspace)["workspace"]["model"]["people"][0]
        assert "description" not in person
        assert "url" not in person
        assert "relationships" not in person


class TestViews:
    def test_include_all_views_export_a_wildcard(self, hedge_fund: Workspace) -> None:
        data = workspace_to_json(hedge_fund)["workspace"]["views"]
        context_views = data["systemContextViews"]
        assert all(v.get("includes") == ["*"] for v in context_views)

    def test_view_scope_key_matches_view_type(self, hedge_fund: Workspace) -> None:
        data = workspace_to_json(hedge_fund)["workspace"]["views"]
        assert all("softwareSystemId" in v for v in data["systemContextViews"])
        assert all("softwareSystemId" in v for v in data["containerViews"])
        assert all("containerId" in v for v in data["componentViews"])

    def test_dynamic_view_steps_round_trip(self, hedge_fund: Workspace) -> None:
        reparsed = parse_json(export_json(hedge_fund))
        original = next(v for v in hedge_fund.views if v.type == ViewType.DYNAMIC)
        again = next(v for v in reparsed.views if v.type == ViewType.DYNAMIC)
        assert [(r.id, r.order, r.description) for r in again.relationship_views] == [
            (r.id, r.order, r.description) for r in original.relationship_views
        ]

    def test_deployment_view_environment_round_trips(
        self, hedge_fund: Workspace
    ) -> None:
        reparsed = parse_json(export_json(hedge_fund))
        environments = {
            v.key: v.environment
            for v in reparsed.views
            if v.type == ViewType.DEPLOYMENT
        }
        expected = {
            v.key: v.environment
            for v in hedge_fund.views
            if v.type == ViewType.DEPLOYMENT
        }
        assert environments == expected

    def test_auto_layout_direction_round_trips(self, hedge_fund: Workspace) -> None:
        reparsed = parse_json(export_json(hedge_fund))
        directions = {
            v.key: v.auto_layout.rank_direction
            for v in reparsed.views
            if v.auto_layout is not None
        }
        expected = {
            v.key: v.auto_layout.rank_direction
            for v in hedge_fund.views
            if v.auto_layout is not None
        }
        assert directions == expected


class TestStylesAndDeployment:
    def test_element_styles_round_trip_including_shape(
        self, hedge_fund: Workspace
    ) -> None:
        reparsed = parse_json(export_json(hedge_fund))
        original = {
            s.tag: (s.background, s.color, s.shape)
            for s in hedge_fund.configuration.styles.element_styles
        }
        again = {
            s.tag: (s.background, s.color, s.shape)
            for s in reparsed.configuration.styles.element_styles
        }
        assert again == original
        assert any(shape == Shape.CYLINDER for _, _, shape in again.values())

    def test_deployment_nodes_and_instances_round_trip(
        self, hedge_fund: Workspace
    ) -> None:
        reparsed = parse_json(export_json(hedge_fund))

        def flatten(nodes: list[DeploymentNode]) -> Iterator[DeploymentNode]:
            for node in nodes:
                yield node
                yield from flatten(node.children)

        def summary(workspace: Workspace) -> set[tuple[str, str, str]]:
            result = set()
            for node in flatten(workspace.deployment_nodes):
                result.add((node.id, node.name, node.environment))
                for ci in node.container_instances:
                    result.add((ci.id, ci.container_id, ci.environment))
            return result

        assert summary(reparsed) == summary(hedge_fund)

    def test_enterprise_round_trips(self, hedge_fund: Workspace) -> None:
        assert hedge_fund.enterprise is not None  # sample defines one
        reparsed = parse_json(export_json(hedge_fund))
        assert reparsed.enterprise is not None
        assert reparsed.enterprise.name == hedge_fund.enterprise.name


class TestDocumentation:
    def test_docs_and_adrs_round_trip(self, hedge_fund: Workspace) -> None:
        reparsed = parse_json(export_json(hedge_fund))
        assert len(reparsed.documentation.sections) == len(
            hedge_fund.documentation.sections
        )
        original_adrs = {
            (d.id, d.title, d.status) for d in hedge_fund.documentation.decisions
        }
        again_adrs = {
            (d.id, d.title, d.status) for d in reparsed.documentation.decisions
        }
        assert again_adrs == original_adrs


class TestSerialisation:
    def test_export_json_is_valid_json_with_trailing_newline(
        self, hedge_fund: Workspace
    ) -> None:
        text = export_json(hedge_fund)
        assert text.endswith("\n")
        assert json.loads(text)["workspace"]["name"] == hedge_fund.name


class TestCli:
    def test_export_command_writes_reparseable_json(self, tmp_path: Path) -> None:
        from click.testing import CliRunner

        from pystructurizr.cli.main import cli

        out_file = tmp_path / "out" / "workspace.json"
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "export",
                str(SAMPLES / "hedge_fund" / "workspace.dsl"),
                "--output",
                str(out_file),
            ],
        )
        assert result.exit_code == 0, result.output
        reparsed = parse_json_file(out_file)
        assert reparsed.name

    def test_export_command_prints_to_stdout(self) -> None:
        from click.testing import CliRunner

        from pystructurizr.cli.main import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["export", str(FIXTURES / "example.json")])
        assert result.exit_code == 0, result.output
        assert json.loads(result.output)["workspace"]["name"] == "Internet Banking"
