from pathlib import Path
from pystructurizr.parser.dsl import parse_dsl_file
from pystructurizr.parser.json_parser import parse_json_file
from pystructurizr.generators.mermaid import MermaidGenerator

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_generate_system_context_from_dsl() -> None:
    ws = parse_dsl_file(FIXTURES / "example.dsl")
    gen = MermaidGenerator(ws)
    diagrams = gen.generate_all()
    assert "SystemContext" in diagrams
    mmd = diagrams["SystemContext"]
    assert mmd.startswith("C4Context")
    assert "Person(" in mmd or "Person_Ext(" in mmd


def test_generate_container_from_dsl() -> None:
    ws = parse_dsl_file(FIXTURES / "example.dsl")
    gen = MermaidGenerator(ws)
    diagrams = gen.generate_all()
    assert "Containers" in diagrams
    mmd = diagrams["Containers"]
    assert mmd.startswith("C4Container")
    assert "Container(" in mmd
    assert "System_Boundary(" in mmd


def test_relationships_in_output() -> None:
    ws = parse_dsl_file(FIXTURES / "example.dsl")
    gen = MermaidGenerator(ws)
    mmd = gen.generate_all()["SystemContext"]
    assert "Rel(" in mmd


def test_generate_from_json() -> None:
    ws = parse_json_file(FIXTURES / "example.json")
    gen = MermaidGenerator(ws)
    diagrams = gen.generate_all()
    assert len(diagrams) == 2
    assert diagrams["SystemContext"].startswith("C4Context")
    assert diagrams["Containers"].startswith("C4Container")


def test_generate_single_view() -> None:
    ws = parse_dsl_file(FIXTURES / "example.dsl")
    gen = MermaidGenerator(ws)
    view = next(v for v in ws.views if v.key == "SystemContext")
    mmd = gen.generate_view(view)
    assert "C4Context" in mmd


def test_external_system_rendered() -> None:
    ws = parse_json_file(FIXTURES / "example.json")
    gen = MermaidGenerator(ws)
    mmd = gen.generate_all()["SystemContext"]
    assert "System_Ext(" in mmd
