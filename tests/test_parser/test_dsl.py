from pathlib import Path
import pytest
from c4studio.parser.dsl import ParseError, parse_dsl, parse_dsl_file

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_parse_minimal() -> None:
    dsl = """
    workspace "Test" "desc" {
        model {
            u = person "User"
            s = softwareSystem "System"
            u -> s "Uses"
        }
        views {
            systemContext s "ctx" {
                include *
            }
        }
    }
    """
    ws = parse_dsl(dsl)
    assert ws.name == "Test"
    assert len(ws.people) == 1
    assert ws.people[0].name == "User"
    assert len(ws.software_systems) == 1
    assert ws.software_systems[0].name == "System"
    assert len(ws.relationships) == 1
    assert ws.relationships[0].description == "Uses"


def test_parse_containers() -> None:
    dsl = """
    workspace "W" {
        model {
            s = softwareSystem "MySystem" {
                c1 = container "Web App" "UI" "React"
                c2 = container "API" "Backend" "Python"
                c1 -> c2 "Calls"
            }
        }
        views {
            container s "ContView" {
                include *
            }
        }
    }
    """
    ws = parse_dsl(dsl)
    system = ws.software_systems[0]
    assert len(system.containers) == 2
    assert system.containers[0].technology == "React"
    assert len(ws.relationships) == 1


def test_parse_example_fixture() -> None:
    ws = parse_dsl_file(FIXTURES / "example.dsl")
    assert ws.name == "Internet Banking"
    assert len(ws.people) == 1
    assert len(ws.software_systems) == 3
    bank = next(s for s in ws.software_systems if "Banking System" in s.name)
    assert len(bank.containers) == 4
    assert len(ws.views) == 2


def test_include_multiple_identifiers_on_one_line() -> None:
    dsl = """
    workspace {
        model {
            a = person "A"
            b = person "B"
            s = softwareSystem "S"
            a -> s "Uses"
        }
        views {
            systemContext s "v" {
                include a b s
                exclude b
                autoLayout
            }
        }
    }
    """
    ws = parse_dsl(dsl)
    view = ws.views[0]
    a, b, s = ws.people[0].id, ws.people[1].id, ws.software_systems[0].id
    assert view.included_ids == [a, b, s]
    assert view.excluded_ids == [b]
    # autoLayout on the next line must not be swallowed as an included id.
    assert view.auto_layout is not None


def test_include_splits_workspace_across_files() -> None:
    ws = parse_dsl_file(FIXTURES / "split_workspace" / "workspace.dsl")
    assert ws.name == "Split Workspace"
    assert len(ws.people) == 1
    assert len(ws.software_systems) == 1
    assert ws.software_systems[0].containers[0].name == "API"
    # Relationship declared in a nested include, across fragment files.
    assert len(ws.relationships) == 1
    assert ws.relationships[0].description == "Calls"
    assert len(ws.views) == 1


def test_include_missing_file_raises(tmp_path: Path) -> None:
    main = tmp_path / "workspace.dsl"
    main.write_text(
        'workspace "W" { model {\n!include missing.dsl\n} }', encoding="utf-8"
    )
    with pytest.raises(ParseError, match="not found"):
        parse_dsl_file(main)


def test_include_cycle_raises(tmp_path: Path) -> None:
    a = tmp_path / "a.dsl"
    b = tmp_path / "b.dsl"
    a.write_text('workspace "W" { model {\n!include b.dsl\n} }', encoding="utf-8")
    b.write_text("!include a.dsl\n", encoding="utf-8")
    with pytest.raises(ParseError, match="Circular"):
        parse_dsl_file(a)


def test_include_without_file_context_raises() -> None:
    with pytest.raises(ParseError, match="file context"):
        parse_dsl('workspace "W" { model {\n!include other.dsl\n} }')


def test_styles_block_parses_element_and_relationship_rules() -> None:
    dsl = """
    workspace {
        model {
            u = person "User"
            s = softwareSystem "System" "" "Database"
            u -> s "Uses"
        }
        views {
            systemContext s "ctx" {
                include *
            }
            styles {
                element "Person" {
                    background #08427b
                    color "#ffffff"
                    shape Person
                    fontSize 22
                }
                element "Database" {
                    shape Cylinder
                }
                relationship "Relationship" {
                    color #707070
                    dashed false
                    thickness 2
                }
            }
        }
    }
    """
    ws = parse_dsl(dsl)
    styles = ws.views.configuration.styles
    assert len(styles.element_styles) == 2
    person = styles.element_styles[0]
    assert person.tag == "Person"
    assert person.background == "#08427b"
    assert person.color == "#ffffff"
    assert person.shape is not None and person.shape.value == "Person"
    assert person.font_size == 22
    database = styles.element_styles[1]
    assert database.shape is not None and database.shape.value == "Cylinder"
    rel = styles.relationship_styles[0]
    assert rel.color == "#707070"
    assert rel.dashed is False
    assert rel.thickness == 2
    # The rest of the views block still parsed correctly.
    assert len(ws.views) == 1


def test_styles_block_skips_unknown_properties() -> None:
    dsl = """
    workspace {
        model {
            u = person "User"
            s = softwareSystem "System"
            u -> s "Uses"
        }
        views {
            systemContext s "ctx" {
                include *
            }
            styles {
                element "Person" {
                    unknownThing whatever
                    background #123456
                }
            }
        }
    }
    """
    ws = parse_dsl(dsl)
    assert ws.views.configuration.styles.element_styles[0].background == "#123456"


def test_docs_and_adrs_directives_attach_documentation(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    adrs = tmp_path / "adrs"
    docs.mkdir()
    adrs.mkdir()
    (docs / "02-details.md").write_text("# Details\n\nBody.", encoding="utf-8")
    (docs / "01-intro.md").write_text("# Introduction\n\nHello.", encoding="utf-8")
    (adrs / "0001-use-adrs.md").write_text(
        "# 1. Use ADRs\n\nDate: 2026-05-04\n\n## Status\n\nAccepted\n\n"
        "## Context\n\nBecause.",
        encoding="utf-8",
    )
    main = tmp_path / "workspace.dsl"
    main.write_text(
        """
        workspace "Docs" {
            !docs docs
            !adrs adrs
            model {
                s = softwareSystem "S"
            }
            views {
                systemContext s ctx { include * }
            }
        }
        """,
        encoding="utf-8",
    )

    ws = parse_dsl_file(main)
    sections = ws.documentation.sections
    assert [sec.title for sec in sections] == ["Introduction", "Details"]
    assert sections[0].order == 1
    assert sections[0].filename == "01-intro.md"
    decision = ws.documentation.decisions[0]
    assert decision.id == "1"
    assert decision.title == "Use ADRs"
    assert decision.date == "2026-05-04"
    assert decision.status == "Accepted"
    # The rest of the DSL still parsed normally.
    assert ws.software_systems[0].name == "S"
    assert len(ws.views) == 1


def test_docs_directive_without_file_context_raises() -> None:
    with pytest.raises(ParseError, match="file context"):
        parse_dsl('workspace "W" {\n!docs docs\n}')


def test_docs_files_are_watched_for_live_reload(tmp_path: Path) -> None:
    from c4studio.parser.dsl import collect_source_files

    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "a.md").write_text("# A", encoding="utf-8")
    main = tmp_path / "workspace.dsl"
    main.write_text(
        'workspace "W" {\n!docs docs\nmodel { s = softwareSystem "S" } }',
        encoding="utf-8",
    )
    files = collect_source_files(main)
    assert main.resolve() in files
    assert (docs / "a.md").resolve() in files


def test_relationship_technology() -> None:
    dsl = """
    workspace {
        model {
            a = person "A"
            b = softwareSystem "B"
            a -> b "Uses" "HTTPS"
        }
        views { systemContext b "v" { include * } }
    }
    """
    ws = parse_dsl(dsl)
    assert ws.relationships[0].technology == "HTTPS"
