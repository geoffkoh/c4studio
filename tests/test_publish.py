"""The published site (PP-188).

Two properties matter more than the markup: the site is **self-contained**
— a folder that works from a file:// path with no network — and every
view is its **own page**, so a link to a diagram survives being pasted
into a ticket.

The rendering half needs Node, so it skips where `c4 render` would.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from click.testing import CliRunner

from c4studio.cli.main import cli
from c4studio.parser.dsl import parse_dsl
from c4studio.publish import publish
from c4studio.render import RenderError, node_executable

SAMPLES = Path(__file__).parent.parent / "samples"

WORKSPACE = """
workspace "Shop" "Sells things" {
    model {
        u = person "User" "Buys"
        s = softwareSystem "Shop" "Sells" {
            web = container "Web" "UI" "React"
            api = container "API" "Logic" "Python"
            web -> api "Calls"
        }
        u -> web "Uses"
    }
    views {
        systemLandscape "Landscape" "Everything" {
            include *
        }
        container s "Containers" {
            include *
        }
    }
}
"""


def _node_available() -> bool:
    try:
        node_executable()
    except RenderError:
        return False
    return True


needs_node = pytest.mark.skipif(not _node_available(), reason="no node")


@pytest.fixture()
def site(tmp_path: Path) -> Path:
    out = tmp_path / "site"
    publish(parse_dsl(WORKSPACE), out)
    return out


@needs_node
class TestStructure:
    def test_one_page_per_view(self, site: Path) -> None:
        """Not one page with a switcher: a link to a diagram has to be a
        link to *that* diagram."""
        pages = sorted(p.name for p in (site / "views").glob("*.html"))
        assert pages == ["containers.html", "landscape.html"]

    def test_the_index_links_every_view(self, site: Path) -> None:
        index = (site / "index.html").read_text(encoding="utf-8")
        assert 'href="views/landscape.html"' in index
        assert 'href="views/containers.html"' in index

    def test_each_view_page_carries_its_diagram_inline(self, site: Path) -> None:
        page = (site / "views" / "containers.html").read_text(encoding="utf-8")
        assert "<svg" in page
        assert "Web" in page and "API" in page

    def test_navigation_is_relative_and_works_from_a_subdirectory(
        self, site: Path
    ) -> None:
        page = (site / "views" / "containers.html").read_text(encoding="utf-8")
        assert 'href="../index.html"' in page
        assert 'href="../site.css"' in page

    def test_the_workspace_name_and_description_are_shown(self, site: Path) -> None:
        index = (site / "index.html").read_text(encoding="utf-8")
        assert "Shop" in index
        assert "Sells things" in index


@needs_node
class TestSelfContained:
    def test_nothing_is_fetched_from_the_network(self, site: Path) -> None:
        """The whole point: a folder that works offline, from file://."""
        for page in site.rglob("*.html"):
            text = page.read_text(encoding="utf-8")
            assert not re.search(r'(src|href)="https?://', text), page
            assert "@import" not in text

    def test_the_stylesheet_is_written_once_and_linked(self, site: Path) -> None:
        assert (site / "site.css").is_file()
        index = (site / "index.html").read_text(encoding="utf-8")
        assert 'href="site.css"' in index


@needs_node
class TestContent:
    def test_documentation_and_decisions_become_pages(self, tmp_path: Path) -> None:
        source_dir = tmp_path / "ws"
        (source_dir / "docs").mkdir(parents=True)
        (source_dir / "docs" / "01-intro.md").write_text(
            "# Introduction\n\nSome **prose**.\n", encoding="utf-8"
        )
        (source_dir / "adrs").mkdir()
        (source_dir / "adrs" / "0001-use-c4.md").write_text(
            "# 1. Use C4\n\nDate: 2026-01-01\n\n## Status\n\nAccepted\n",
            encoding="utf-8",
        )
        source = source_dir / "ws.dsl"
        source.write_text(
            WORKSPACE.replace(
                "    model {", "    !docs docs\n    !adrs adrs\n    model {"
            ),
            encoding="utf-8",
        )
        from c4studio.parser.dsl import parse_dsl_file

        out = tmp_path / "site"
        publish(parse_dsl_file(source), out)
        docs = list((out / "docs").glob("*.html"))
        decisions = list((out / "decisions").glob("*.html"))
        assert len(docs) == 1
        assert len(decisions) == 1
        assert "<strong>prose</strong>" in docs[0].read_text(encoding="utf-8")

    def test_a_section_with_its_own_heading_is_not_titled_twice(
        self, tmp_path: Path
    ) -> None:
        source_dir = tmp_path / "ws"
        (source_dir / "docs").mkdir(parents=True)
        (source_dir / "docs" / "01-intro.md").write_text(
            "# Introduction\n\nText.\n", encoding="utf-8"
        )
        source = source_dir / "ws.dsl"
        source.write_text(
            WORKSPACE.replace("    model {", "    !docs docs\n    model {"),
            encoding="utf-8",
        )
        from c4studio.parser.dsl import parse_dsl_file

        out = tmp_path / "site"
        publish(parse_dsl_file(source), out)
        page = next((out / "docs").glob("*.html")).read_text(encoding="utf-8")
        assert page.count("<h1>Introduction</h1>") == 1


@needs_node
class TestCli:
    def test_it_writes_a_site_and_says_where(self, tmp_path: Path) -> None:
        source = tmp_path / "ws.dsl"
        source.write_text(WORKSPACE, encoding="utf-8")
        out = tmp_path / "site"
        result = CliRunner().invoke(cli, ["publish", str(source), "-o", str(out)])
        assert result.exit_code == 0
        assert "index.html" in result.output
        assert (out / "index.html").is_file()

    def test_an_unknown_perspective_is_refused_before_any_rendering(
        self, tmp_path: Path
    ) -> None:
        source = tmp_path / "ws.dsl"
        source.write_text(WORKSPACE, encoding="utf-8")
        out = tmp_path / "site"
        result = CliRunner().invoke(
            cli, ["publish", str(source), "-o", str(out), "--perspective", "nope"]
        )
        assert result.exit_code != 0
        assert "No perspective named 'nope'" in result.output
        assert not out.exists()

    def test_publishing_twice_does_not_delete_what_is_there(
        self, tmp_path: Path
    ) -> None:
        """A publish into a directory must not be a way to lose things."""
        source = tmp_path / "ws.dsl"
        source.write_text(WORKSPACE, encoding="utf-8")
        out = tmp_path / "site"
        out.mkdir()
        (out / "CNAME").write_text("docs.example.com", encoding="utf-8")
        CliRunner().invoke(cli, ["publish", str(source), "-o", str(out)])
        assert (out / "CNAME").is_file()

    def test_clean_removes_the_directory_first(self, tmp_path: Path) -> None:
        source = tmp_path / "ws.dsl"
        source.write_text(WORKSPACE, encoding="utf-8")
        out = tmp_path / "site"
        out.mkdir()
        (out / "stale.html").write_text("old", encoding="utf-8")
        CliRunner().invoke(cli, ["publish", str(source), "-o", str(out), "--clean"])
        assert not (out / "stale.html").exists()
        assert (out / "index.html").is_file()


@needs_node
def test_the_richest_sample_publishes(tmp_path: Path) -> None:
    """hedge_fund has documentation, ADRs, deployment and every view type."""
    from c4studio.parser.dsl import parse_dsl_file

    out = tmp_path / "site"
    written = publish(parse_dsl_file(SAMPLES / "hedge_fund" / "workspace.dsl"), out)
    assert len(written) > 15
    index = (out / "index.html").read_text(encoding="utf-8")
    assert "Quantia" in index
