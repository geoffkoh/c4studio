"""Editing style rules as text (PP-231).

Each edit is checked twice: as text, so formatting and comments are seen
to survive, and by parsing the result, so the edit is seen to mean what
the card said it would.
"""

from __future__ import annotations

import pytest

from c4studio.parser.dsl import parse_dsl
from c4studio.style_edit import (
    StyleEditError,
    add_element_tag,
    add_rule,
    element_tag_counts,
    is_own_tag,
    own_tag_name,
    relationship_tag_counts,
    set_rule_property,
)

DSL = """workspace "W" {
    model {
        u = person "User"
        s = softwareSystem "S" {
            db = container "DB" "" "" "Database"
            api = container "API" {
                technology "Java"
            }
        }
        u -> api "Uses" "" "Async"
    }
    views {
        styles {
            element "Database" {
                shape Cylinder
                # brand blue
                background #438dd5
            }
            element "One" { background #ffffff }
        }
    }
}
"""


def _style(text: str, tag: str) -> dict[str, object]:
    styles = parse_dsl(text).views.configuration.styles.element_styles
    rule = [s for s in styles if s.tag == tag][-1]
    return {"background": rule.background, "color": rule.color, "stroke": rule.stroke}


class TestRuleProperty:
    def test_replacing_a_colour_changes_only_the_value(self) -> None:
        text = set_rule_property(DSL, "element", "Database", "background", "#FF8800")
        assert (
            "                # brand blue\n                background #ff8800\n" in text
        )
        assert len(text) == len(DSL)
        assert _style(text, "Database")["background"] == "#ff8800"

    def test_a_new_property_is_the_rule_body_s_last_line(self) -> None:
        text = set_rule_property(DSL, "element", "Database", "color", "#000000")
        assert (
            "                background #438dd5\n"
            "                color #000000\n"
            "            }\n"
        ) in text
        assert _style(text, "Database")["color"] == "#000000"

    def test_a_one_line_rule_is_opened_out(self) -> None:
        # Statements need lines of their own, so `{ a b }` cannot simply grow.
        text = set_rule_property(DSL, "element", "One", "stroke", "#123456")
        assert (
            '            element "One" {\n'
            "                background #ffffff\n"
            "                stroke #123456\n"
            "            }\n"
        ) in text
        assert _style(text, "One") == {
            "background": "#ffffff",
            "color": "",
            "stroke": "#123456",
        }

    def test_resetting_removes_the_line_and_nothing_else(self) -> None:
        text = set_rule_property(DSL, "element", "Database", "background", None)
        assert "background #438dd5" not in text
        assert "shape Cylinder" in text
        assert "# brand blue" in text
        assert len(text.splitlines()) == len(DSL.splitlines()) - 1

    def test_resetting_what_no_rule_sets_changes_nothing(self) -> None:
        assert set_rule_property(DSL, "element", "Database", "stroke", None) == DSL
        assert set_rule_property(DSL, "element", "Nope", "stroke", None) == DSL

    def test_the_last_rule_for_a_tag_is_the_one_edited(self) -> None:
        # Where two rules overlap the later wins, so it is the one to edit.
        doubled = DSL.replace(
            'element "One"',
            'element "Database" {\n                color #111111\n            }\n'
            '            element "One"',
        )
        text = set_rule_property(doubled, "element", "Database", "color", "#222222")
        assert "color #222222" in text
        assert "background #438dd5" in text

    def test_a_dash_pattern_is_written_as_the_dsl_spells_it(self) -> None:
        text = set_rule_property(DSL, "relationship", "Async", "style", "dotted")
        assert (
            'relationship "Async" {\n                style Dotted\n            }'
            in text
        )
        rule = parse_dsl(text).views.configuration.styles.relationship_styles[-1]
        assert rule.style is not None and rule.style.value.lower() == "dotted"

    @pytest.mark.parametrize(
        ("kind", "prop", "value"),
        [
            ("element", "background", "red"),
            ("element", "background", "#fff"),
            ("element", "shape", "Box"),
            ("relationship", "style", "wavy"),
            ("relationship", "background", "#ffffff"),
        ],
    )
    def test_anything_the_card_would_not_write_is_refused(
        self, kind: str, prop: str, value: str
    ) -> None:
        with pytest.raises(StyleEditError):
            set_rule_property(DSL, kind, "Database", prop, value)


class TestNewRule:
    def test_it_goes_after_every_other_rule(self) -> None:
        text = add_rule(DSL, "element", "New", "background", "#00ff00")
        assert text.index('element "New"') > text.index('element "One"')
        assert _style(text, "New")["background"] == "#00ff00"

    def test_a_workspace_without_styles_gets_them(self) -> None:
        bare = 'workspace "X" {\n    model {\n        a = person "A"\n    }\n}\n'
        text = add_rule(bare, "element", "Person", "color", "#000000")
        assert text == (
            'workspace "X" {\n    model {\n        a = person "A"\n    }\n'
            "    views {\n        styles {\n"
            '            element "Person" {\n                color #000000\n            }\n'
            "        }\n    }\n}\n"
        )
        assert _style(text, "Person")["color"] == "#000000"

    def test_it_needs_a_value(self) -> None:
        with pytest.raises(StyleEditError):
            add_rule(DSL, "element", "New", "background", None)


class TestElementTag:
    def test_a_definition_without_a_body_gets_one(self) -> None:
        text = add_element_tag(DSL, 5, "DB")
        assert (
            '            db = container "DB" "" "" "Database" {\n'
            '                tags "DB"\n'
            "            }\n"
        ) in text
        db = parse_dsl(text).find_element("db")
        assert db is not None and db.tags == ["Database", "DB"]

    def test_a_body_gets_a_tags_statement_first(self) -> None:
        text = add_element_tag(DSL, 6, "API")
        assert 'api = container "API" {\n                tags "API"\n' in text
        api = parse_dsl(text).find_element("api")
        assert api is not None and "API" in api.tags
        assert getattr(api, "technology", "") == "Java"

    def test_a_definition_continued_across_lines_is_refused(self) -> None:
        continued = DSL.replace('"DB" "" "" "Database"', '"DB" \\\n "" "" "Database"')
        with pytest.raises(StyleEditError):
            add_element_tag(continued, 5, "DB")


class TestTags:
    def test_counts_include_the_implicit_tags(self) -> None:
        workspace = parse_dsl(DSL)
        counts = element_tag_counts(workspace)
        assert counts["Element"] == 4
        assert counts["Container"] == 2
        assert counts["Person"] == 1
        assert counts["Database"] == 1
        assert relationship_tag_counts(workspace) == {"Relationship": 1, "Async": 1}

    def test_an_own_tag_is_the_name_made_unique(self) -> None:
        assert own_tag_name("DB", {"API"}) == "DB"
        assert own_tag_name("DB", {"DB", "DB 2"}) == "DB 3"
        assert is_own_tag("DB 3", "DB")
        assert is_own_tag("DB", "DB")
        assert not is_own_tag("Database", "DB")
        assert not is_own_tag("DB copy", "DB")
