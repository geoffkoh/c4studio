"""The Markdown subset the published site renders with (PP-188).

Hand-written because the project takes no new dependency without asking,
which makes the tests the specification: what it supports, what it does
not, and that nothing in a document can inject markup.
"""

from __future__ import annotations

from c4studio.markdown import render


class TestBlocks:
    def test_headings(self) -> None:
        assert render("# One\n\n### Three") == "<h1>One</h1>\n<h3>Three</h3>"

    def test_paragraphs_join_wrapped_lines(self) -> None:
        assert render("A sentence\nwrapped here.") == "<p>A sentence wrapped here.</p>"

    def test_a_blank_line_separates_paragraphs(self) -> None:
        assert render("One.\n\nTwo.") == "<p>One.</p>\n<p>Two.</p>"

    def test_unordered_and_ordered_lists(self) -> None:
        assert render("- a\n- b") == "<ul><li>a</li><li>b</li></ul>"
        assert render("1. a\n2. b") == "<ol><li>a</li><li>b</li></ol>"

    def test_a_wrapped_list_item_stays_one_item(self) -> None:
        """The bug the hedge_fund docs found: every wrapped item split its
        own list in half and left the remainder as a paragraph."""
        rendered = render("1. A long item\n   continued here.\n2. Second")
        assert rendered == (
            "<ol><li>A long item continued here.</li><li>Second</li></ol>"
        )

    def test_switching_list_type_starts_a_new_list(self) -> None:
        assert render("- a\n1. b") == "<ul><li>a</li></ul>\n<ol><li>b</li></ol>"

    def test_fenced_code_is_not_interpreted(self) -> None:
        rendered = render("```python\n# not a heading\n- not a list\n```")
        assert "<h1>" not in rendered and "<li>" not in rendered
        assert '<pre><code class="language-python">' in rendered

    def test_block_quote(self) -> None:
        assert render("> Careful.") == "<blockquote>Careful.</blockquote>"

    def test_horizontal_rule(self) -> None:
        assert render("---") == "<hr>"

    def test_table_with_a_header(self) -> None:
        rendered = render("| A | B |\n| --- | --- |\n| 1 | 2 |")
        assert "<th>A</th>" in rendered
        assert "<td>2</td>" in rendered

    def test_pipes_without_a_divider_are_just_text(self) -> None:
        assert render("a | b") == "<p>a | b</p>"


class TestInline:
    def test_bold_italic_and_code(self) -> None:
        assert render("**b** *i* `c`") == (
            "<p><strong>b</strong> <em>i</em> <code>c</code></p>"
        )

    def test_underscores_inside_a_word_are_left_alone(self) -> None:
        """`some_identifier_name` is a name, not emphasis."""
        assert render("some_identifier_name") == "<p>some_identifier_name</p>"

    def test_links_and_images(self) -> None:
        assert render("[text](http://x/y)") == '<p><a href="http://x/y">text</a></p>'
        assert render("![alt](y.png)") == '<p><img src="y.png" alt="alt"></p>'

    def test_code_content_is_not_further_interpreted(self) -> None:
        assert render("`**not bold**`") == "<p><code>**not bold**</code></p>"


class TestEscaping:
    def test_markup_in_the_source_cannot_reach_the_page(self) -> None:
        """The site is published; documentation is whatever is in the
        directory. Escaping is not optional."""
        rendered = render("<script>alert(1)</script>")
        assert "<script>" not in rendered
        assert "&lt;script&gt;" in rendered

    def test_markup_inside_a_heading_is_escaped(self) -> None:
        assert render("# <b>x</b>") == "<h1>&lt;b&gt;x&lt;/b&gt;</h1>"

    def test_markup_inside_code_is_escaped(self) -> None:
        assert "&lt;script&gt;" in render("```\n<script>\n```")

    def test_markup_inside_a_table_cell_is_escaped(self) -> None:
        rendered = render("| <i>a</i> |\n| --- |\n| b |")
        assert "<i>" not in rendered


class TestUnsupported:
    def test_an_unknown_construct_degrades_to_text(self) -> None:
        """Wrong in the safe direction: plain text, never someone else's
        markup."""
        rendered = render("Term\n: definition")
        assert "<dl>" not in rendered
        assert "definition" in rendered

    def test_empty_input(self) -> None:
        assert render("") == ""
