"""Tests for the element definition location scanner."""

from __future__ import annotations

from pathlib import Path

from c4studio.parser.locations import element_locations

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_locates_elements_across_include_fragments() -> None:
    root = FIXTURES / "split_workspace" / "workspace.dsl"
    locations = element_locations(root)

    user_path, user_line = locations["user"]
    assert user_path.name == "people.dsl"
    assert user_line == 1

    core_path, _ = locations["core"]
    assert core_path.name == "systems.dsl"
    api_path, api_line = locations["api"]
    assert api_path.name == "systems.dsl"
    assert api_line == 2


def test_unaliased_elements_use_slugified_names(tmp_path: Path) -> None:
    source = tmp_path / "w.dsl"
    source.write_text(
        """
        workspace "W" {
            model {
                person "Data Analyst"
                s = softwareSystem "Core" {
                    container "Web App" "" "React"
                }
            }
        }
        """,
        encoding="utf-8",
    )
    locations = element_locations(source)
    assert "data_analyst" in locations
    assert locations["data_analyst"][1] == 4
    assert "web_app" in locations


def test_view_headers_and_relationships_do_not_match(tmp_path: Path) -> None:
    source = tmp_path / "w.dsl"
    source.write_text(
        """
        workspace "W" {
            model {
                a = person "A"
                s = softwareSystem "S" {
                    web = container "Web"
                }
                a -> web "Uses"
            }
            views {
                container s ContainersView "Title" {
                    include *
                }
                component web CompView
            }
        }
        """,
        encoding="utf-8",
    )
    locations = element_locations(source)
    # Only the four real definitions; view headers add nothing.
    assert set(locations) == {"a", "s", "web"}
    assert locations["web"][1] == 6


def test_instances_get_aliases_or_generated_ids(tmp_path: Path) -> None:
    source = tmp_path / "w.dsl"
    source.write_text(
        """
        workspace "W" {
            model {
                s = softwareSystem "S" {
                    web = container "Web"
                }
                deploymentEnvironment "Prod" {
                    deploymentNode "Cloud" {
                        webInst = containerInstance web
                        containerInstance web
                        containerInstance web
                    }
                }
            }
        }
        """,
        encoding="utf-8",
    )
    locations = element_locations(source)
    assert locations["webInst"][1] == 9
    assert locations["web_instance"][1] == 10
    assert locations["web_instance_2"][1] == 11
    assert "cloud" in locations  # deployment node by slug


def test_docs_markdown_is_not_scanned(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "a.md").write_text('person "Fake"', encoding="utf-8")
    source = tmp_path / "w.dsl"
    source.write_text(
        'workspace "W" {\n!docs docs\nmodel { u = person "U" } }',
        encoding="utf-8",
    )
    locations = element_locations(source)
    assert set(locations) == {"u"}


def test_locates_custom_elements(tmp_path: Path) -> None:
    source = tmp_path / "w.dsl"
    source.write_text(
        """
workspace "W" {
    model {
        box = element "Box"
        element "Plain Thing"
    }
}
""",
        encoding="utf-8",
    )
    locations = element_locations(source)
    assert locations["box"][1] == 4
    assert locations["plain_thing"][1] == 5


def test_style_rules_are_not_indexed_as_elements(tmp_path: Path) -> None:
    source = tmp_path / "w.dsl"
    source.write_text(
        """
workspace "W" {
    model {
        s = softwareSystem "Sys"
    }
    views {
        styles {
            element "Styled Tag" {
                background #ff0000
            }
        }
    }
}
""",
        encoding="utf-8",
    )
    locations = element_locations(source)
    assert "s" in locations
    assert "styled_tag" not in locations
