import json
from pathlib import Path
from c4studio.models import Location
from c4studio.parser.json_parser import parse_json, parse_json_file

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_parse_json_fixture() -> None:
    ws = parse_json_file(FIXTURES / "example.json")
    assert ws.name == "Internet Banking"
    assert len(ws.people) == 1
    assert ws.people[0].name == "Personal Banking Customer"
    assert len(ws.software_systems) == 2


def test_parse_json_relationships() -> None:
    ws = parse_json_file(FIXTURES / "example.json")
    assert len(ws.relationships) > 0
    rels_from_customer = [r for r in ws.relationships if r.source_id == "1"]
    assert len(rels_from_customer) == 2


def test_parse_json_containers() -> None:
    ws = parse_json_file(FIXTURES / "example.json")
    banking = next(
        s for s in ws.software_systems if s.name == "Internet Banking System"
    )
    assert len(banking.containers) == 3


def test_parse_json_views() -> None:
    ws = parse_json_file(FIXTURES / "example.json")
    assert len(ws.views) == 2
    keys = {v.key for v in ws.views}
    assert "SystemContext" in keys
    assert "Containers" in keys


def test_external_system_flag() -> None:
    ws = parse_json_file(FIXTURES / "example.json")
    email = next(s for s in ws.software_systems if s.name == "E-mail System")
    assert email.location == Location.EXTERNAL


def test_container_parent_id_set_from_json() -> None:
    ws = parse_json_file(FIXTURES / "example.json")
    banking = next(
        s for s in ws.software_systems if s.name == "Internet Banking System"
    )
    assert banking.containers, "fixture should have containers"
    for c in banking.containers:
        assert c.parent_id == banking.id


def test_deployment_hierarchy_parent_id_from_json() -> None:
    raw = json.dumps(
        {
            "workspace": {
                "name": "W",
                "model": {
                    "deploymentNodes": [
                        {
                            "id": "1",
                            "name": "AWS",
                            "instances": 2,
                            "children": [{"id": "2", "name": "EC2"}],
                            "infrastructureNodes": [{"id": "3", "name": "LB"}],
                        }
                    ],
                },
            }
        }
    )
    ws = parse_json(raw)
    aws = ws.deployment_nodes[0]
    assert aws.parent_id == ""
    assert aws.instances == "2"
    assert aws.children[0].parent_id == "1"
    assert aws.infrastructure_nodes[0].parent_id == "1"


def test_perspective_title_from_json() -> None:
    raw = json.dumps(
        {
            "workspace": {
                "name": "W",
                "model": {
                    "people": [
                        {
                            "id": "1",
                            "name": "User",
                            "perspectives": [
                                {
                                    "name": "Security",
                                    "title": "Sec view",
                                    "value": "high",
                                }
                            ],
                        }
                    ],
                },
            }
        }
    )
    ws = parse_json(raw)
    assert ws.people[0].perspectives[0].title == "Sec view"


# ---------------------------------------------------------------------------
# Phase 4
# ---------------------------------------------------------------------------


def test_parse_branding_and_exporters_from_json() -> None:
    raw = json.dumps(
        {
            "workspace": {
                "name": "W",
                "model": {},
                "views": {
                    "configuration": {
                        "branding": {
                            "color": "#0a0",
                            "font": "Inter",
                            "logo": "https://x/logo.png",
                        },
                        "generatorsAndExporters": {"plantuml": "PlantUMLExporter"},
                    }
                },
            }
        }
    )
    ws = parse_json(raw)
    assert ws.configuration.branding is not None
    assert ws.configuration.branding.logo == "https://x/logo.png"
    assert ws.configuration.branding.font.name == "Inter"
    assert ws.configuration.generators_and_exporters["plantuml"] == "PlantUMLExporter"


def test_parse_workspace_documentation_and_decisions_from_json() -> None:
    raw = json.dumps(
        {
            "workspace": {
                "name": "W",
                "model": {},
                "documentation": {
                    "sections": [
                        {"content": "# Overview", "format": "Markdown"},
                        {"content": "Sec details", "format": "AsciiDoc"},
                    ],
                    "decisions": [
                        {"id": "1", "title": "Use Python", "status": "Accepted"},
                        {"id": "2", "title": "Use uv", "status": "Proposed"},
                    ],
                },
            }
        }
    )
    ws = parse_json(raw)
    assert len(ws.documentation.sections) == 2
    assert ws.documentation.sections[0].content == "# Overview"
    assert ws.documentation.sections[1].format == "AsciiDoc"
    assert [d.id for d in ws.documentation.decisions] == ["1", "2"]
    assert ws.documentation.decisions[0].status == "Accepted"


def test_terminology_defaults_preserved_when_json_omits_them() -> None:
    raw = json.dumps(
        {
            "workspace": {
                "name": "W",
                "model": {},
                "views": {"configuration": {"terminology": {}}},
            }
        }
    )
    ws = parse_json(raw)
    assert ws.configuration.terminology.person == "Person"
    assert ws.configuration.terminology.software_system == "Software System"
