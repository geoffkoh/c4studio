"""`workspace extends <file>` (PP-210).

It used to be a parse error, failing the whole file. Upstream parses the
base workspace and carries on parsing the extending file into it: the
base's identifiers and constants are in scope, and declaring an element
the base already has, by name, means that element rather than a second
one. c4studio splices the two files into one source; these pin that the
splice behaves as upstream's two-stage parse does, and that errors and
relative paths still belong to the file they came from.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from c4studio.parser.dsl import (
    ParseError,
    collect_source_files,
    parse_dsl,
    parse_dsl_file,
)

BASE = """
!const OWNER "team-shop"

workspace "Shop" "The base model" {
    model {
        u = person "Customer"
        shop = softwareSystem "Shop" "Sells things" {
            web = container "Web" "Storefront" "React"
        }
        u -> web "Browses"
    }
    views {
        systemContext shop Context {
            include *
        }
    }
}
"""

EXTENSION = """
workspace extends base.dsl {
    model {
        shop = softwareSystem "Shop" {
            api = container "API" "Orders" "Python" {
                properties {
                    owner "${OWNER}"
                }
            }
        }
        web -> api "Calls"
    }
    views {
        container shop Containers {
            include *
        }
    }
}
"""


def _write(directory: Path, name: str, text: str) -> Path:
    path = directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture()
def extension(tmp_path: Path) -> Path:
    _write(tmp_path, "base.dsl", BASE)
    return _write(tmp_path, "workspace.dsl", EXTENSION)


class TestModel:
    def test_the_base_model_is_there(self, extension: Path) -> None:
        ws = parse_dsl_file(extension)
        assert [p.name for p in ws.people] == ["Customer"]
        assert ws.name == "Shop"

    def test_naming_an_existing_element_extends_it(self, extension: Path) -> None:
        ws = parse_dsl_file(extension)
        assert [s.name for s in ws.software_systems] == ["Shop"]
        shop = ws.software_systems[0]
        assert [c.name for c in shop.containers] == ["Web", "API"]
        # Left out, the description is the base's, not reset.
        assert shop.description == "Sells things"

    def test_base_identifiers_and_constants_are_in_scope(self, extension: Path) -> None:
        ws = parse_dsl_file(extension)
        rels = {
            (r.source_id, r.destination_id, r.description) for r in ws.relationships
        }
        assert ("web", "api", "Calls") in rels
        assert ("u", "web", "Browses") in rels
        api = ws.software_systems[0].containers[1]
        assert api.properties["owner"] == "team-shop"

    def test_views_from_both_files(self, extension: Path) -> None:
        ws = parse_dsl_file(extension)
        assert [v.key for v in ws.views] == ["Context", "Containers"]

    def test_a_new_name_is_a_new_element(self, tmp_path: Path) -> None:
        _write(tmp_path, "base.dsl", BASE)
        path = _write(
            tmp_path,
            "w.dsl",
            'workspace extends base.dsl {\n model {\n  pay = softwareSystem "Payments"\n }\n}\n',
        )
        ws = parse_dsl_file(path)
        assert [s.name for s in ws.software_systems] == ["Shop", "Payments"]

    def test_a_chain_of_bases(self, tmp_path: Path) -> None:
        _write(tmp_path, "base.dsl", BASE)
        _write(
            tmp_path,
            "middle.dsl",
            'workspace extends base.dsl {\n model {\n  ops = person "Operator"\n }\n}\n',
        )
        path = _write(
            tmp_path,
            "top.dsl",
            'workspace extends middle.dsl {\n model {\n  ops -> web "Monitors"\n }\n}\n',
        )
        ws = parse_dsl_file(path)
        assert [p.name for p in ws.people] == ["Customer", "Operator"]
        assert any(r.description == "Monitors" for r in ws.relationships)

    def test_a_workspace_that_extends_nothing_is_unaffected(
        self, tmp_path: Path
    ) -> None:
        ws = parse_dsl_file(_write(tmp_path, "base.dsl", BASE))
        assert ws.description == "The base model"


class TestErrorsAndPaths:
    def test_an_error_in_the_extension_names_the_extension(
        self, tmp_path: Path
    ) -> None:
        _write(tmp_path, "base.dsl", BASE)
        path = _write(
            tmp_path,
            "w.dsl",
            "workspace extends base.dsl {\n model {\n  x = person\n }\n}\n",
        )
        with pytest.raises(ParseError) as raised:
            parse_dsl_file(path)
        assert raised.value.path == path
        assert raised.value.line == 3

    def test_an_error_in_the_base_names_the_base(self, tmp_path: Path) -> None:
        base = _write(
            tmp_path, "base.dsl", "workspace {\n model {\n  x = person\n }\n}\n"
        )
        path = _write(tmp_path, "w.dsl", "workspace extends base.dsl {\n}\n")
        with pytest.raises(ParseError) as raised:
            parse_dsl_file(path)
        assert raised.value.path == base
        assert raised.value.line == 3

    def test_a_missing_base_is_an_error_on_the_extends_line(
        self, tmp_path: Path
    ) -> None:
        path = _write(tmp_path, "w.dsl", "// header\nworkspace extends gone.dsl {\n}\n")
        with pytest.raises(ParseError, match="not found") as raised:
            parse_dsl_file(path)
        assert (raised.value.path, raised.value.line) == (path, 2)

    def test_a_cycle_is_an_error(self, tmp_path: Path) -> None:
        _write(tmp_path, "a.dsl", "workspace extends b.dsl {\n}\n")
        path = _write(tmp_path, "b.dsl", "workspace extends a.dsl {\n}\n")
        with pytest.raises(ParseError, match="Circular"):
            parse_dsl_file(path)

    def test_a_string_without_a_file_context_is_an_error(self) -> None:
        with pytest.raises(ParseError, match="file context"):
            parse_dsl("workspace extends base.dsl {\n}\n")

    @pytest.mark.parametrize("target", ["https://example.com/base.dsl", "base.json"])
    def test_a_url_or_json_base_is_reported_and_skipped(
        self, tmp_path: Path, target: str
    ) -> None:
        path = _write(
            tmp_path,
            "w.dsl",
            f'workspace extends {target} {{\n model {{\n  u = person "U"\n }}\n}}\n',
        )
        ws = parse_dsl_file(path)
        assert [p.name for p in ws.people] == ["U"]
        found = [d for d in ws.diagnostics if d.code == "unsupported-extends"]
        assert len(found) == 1
        assert (found[0].path, found[0].line) == (path, 1)

    def test_the_bases_docs_resolve_from_the_base(self, tmp_path: Path) -> None:
        _write(tmp_path, "shared/docs/01-intro.md", "# Intro\n\nHello.\n")
        _write(
            tmp_path,
            "shared/base.dsl",
            'workspace "B" {\n !docs docs\n model {\n }\n}\n',
        )
        path = _write(
            tmp_path, "team/w.dsl", "workspace extends ../shared/base.dsl {\n}\n"
        )
        ws = parse_dsl_file(path)
        assert [s.title for s in ws.documentation.sections] == ["Intro"]

    def test_live_reload_watches_the_base(self, tmp_path: Path) -> None:
        base = _write(tmp_path, "shared/base.dsl", "workspace {\n !docs docs\n}\n")
        doc = _write(tmp_path, "shared/docs/01-a.md", "# A\n")
        path = _write(
            tmp_path, "team/w.dsl", "workspace extends ../shared/base.dsl {\n}\n"
        )
        files = collect_source_files(path)
        assert base.resolve() in files
        assert doc.resolve() in files
