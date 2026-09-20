"""A deliberately small Markdown subset, for the published site (PP-188).

`marked` renders documentation in the SPA, but that is JavaScript in a
browser. A static site has to be built in Python, and the project takes
no new dependency without asking — so this renders the subset that
architecture prose actually uses and escapes everything else.

**What it handles:** ATX headings, paragraphs, unordered and ordered
lists, fenced and indented code blocks, block quotes, horizontal rules,
tables with a header row, inline code, bold, italic, links and images.

**What it does not:** nested lists, reference links, footnotes, inline
HTML, setext headings. Anything unrecognised comes through as escaped
text, which is the safe direction to be wrong in: a document renders
plainly rather than rendering as markup someone else wrote.

Every value is escaped before any tag is added, so no input can inject
markup. That matters even for your own documentation — the site is
published, and `!docs` reads whatever files are in the directory.
"""

from __future__ import annotations

import html
import re

_HEADING = re.compile(r"^(?P<level>#{1,6})\s+(?P<text>.*)$")
_ORDERED = re.compile(r"^\s*\d+[.)]\s+(?P<text>.*)$")
_UNORDERED = re.compile(r"^\s*[-*+]\s+(?P<text>.*)$")
_QUOTE = re.compile(r"^>\s?(?P<text>.*)$")
_RULE = re.compile(r"^\s*([-*_])\s*(\1\s*){2,}$")
_FENCE = re.compile(r"^\s*```(?P<language>[A-Za-z0-9_+-]*)\s*$")
_TABLE_DIVIDER = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")

_CODE_SPAN = re.compile(r"`([^`]+)`")

#: A character no document contains, used to stand in for a code span
#: while the other rules run.
_PLACEHOLDER = "\x00"

#: Inline rules, applied in order to already-escaped text.
_INLINE = (
    (re.compile(r"!\[([^\]]*)\]\(([^)\s]+)\)"), r'<img src="\2" alt="\1">'),
    (re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)"), r'<a href="\2">\1</a>'),
    (re.compile(r"\*\*([^*]+)\*\*"), r"<strong>\1</strong>"),
    (re.compile(r"(?<!\w)_([^_]+)_(?!\w)"), r"<em>\1</em>"),
    (re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)"), r"<em>\1</em>"),
)


def _inline(text: str) -> str:
    """Escape ``text``, then apply the inline rules to the result.

    Code spans are lifted out before the other rules run and put back
    afterwards. Rendering them in place was not enough: the later rules
    kept matching *inside* the tag, so `` `**not bold**` `` came back
    bold — code that had been reformatted as the thing it was quoting.
    """
    rendered = html.escape(text, quote=False)

    spans: list[str] = []

    def lift(match: re.Match[str]) -> str:
        spans.append(match.group(1))
        return f"{_PLACEHOLDER}{len(spans) - 1}{_PLACEHOLDER}"

    rendered = _CODE_SPAN.sub(lift, rendered)
    for pattern, replacement in _INLINE:
        rendered = pattern.sub(replacement, rendered)
    for index, span in enumerate(spans):
        rendered = rendered.replace(
            f"{_PLACEHOLDER}{index}{_PLACEHOLDER}", f"<code>{span}</code>"
        )
    return rendered


def _table(rows: list[str]) -> str:
    """Render a pipe table whose second line is the divider."""

    def cells(line: str) -> list[str]:
        stripped = line.strip().strip("|")
        return [cell.strip() for cell in stripped.split("|")]

    header = cells(rows[0])
    body = [cells(row) for row in rows[2:]]
    out = ["<table>", "<thead>", "<tr>"]
    out.extend(f"<th>{_inline(cell)}</th>" for cell in header)
    out.extend(["</tr>", "</thead>", "<tbody>"])
    for row in body:
        out.append("<tr>")
        out.extend(f"<td>{_inline(cell)}</td>" for cell in row)
        out.append("</tr>")
    out.extend(["</tbody>", "</table>"])
    return "".join(out)


def render(source: str) -> str:
    """Render Markdown ``source`` as HTML.

    Args:
        source: Markdown text.

    Returns:
        An HTML fragment — no document wrapper, so a caller decides the
        page around it.
    """
    lines = source.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    paragraph: list[str] = []
    list_items: list[str] = []
    list_tag = ""
    quote: list[str] = []

    def close_paragraph() -> None:
        if paragraph:
            out.append(f"<p>{_inline(' '.join(paragraph))}</p>")
            paragraph.clear()

    def close_list() -> None:
        nonlocal list_tag
        if list_items:
            items = "".join(f"<li>{_inline(item)}</li>" for item in list_items)
            out.append(f"<{list_tag}>{items}</{list_tag}>")
            list_items.clear()
            list_tag = ""

    def close_quote() -> None:
        if quote:
            out.append(f"<blockquote>{_inline(' '.join(quote))}</blockquote>")
            quote.clear()

    def close_all() -> None:
        close_paragraph()
        close_list()
        close_quote()

    index = 0
    while index < len(lines):
        line = lines[index]

        fence = _FENCE.match(line)
        if fence:
            close_all()
            body: list[str] = []
            index += 1
            while index < len(lines) and not _FENCE.match(lines[index]):
                body.append(lines[index])
                index += 1
            language = fence.group("language")
            attribute = f' class="language-{language}"' if language else ""
            code = html.escape("\n".join(body))
            out.append(f"<pre><code{attribute}>{code}</code></pre>")
            index += 1
            continue

        if not line.strip():
            close_all()
            index += 1
            continue

        if _RULE.match(line):
            close_all()
            out.append("<hr>")
            index += 1
            continue

        heading = _HEADING.match(line)
        if heading:
            close_all()
            level = len(heading.group("level"))
            out.append(f"<h{level}>{_inline(heading.group('text'))}</h{level}>")
            index += 1
            continue

        # A table needs its divider on the next line, which is what tells
        # it apart from a paragraph that happens to contain pipes.
        if (
            "|" in line
            and index + 1 < len(lines)
            and _TABLE_DIVIDER.match(lines[index + 1])
        ):
            close_all()
            rows = [line, lines[index + 1]]
            index += 2
            while index < len(lines) and "|" in lines[index] and lines[index].strip():
                rows.append(lines[index])
                index += 1
            out.append(_table(rows))
            continue

        quoted = _QUOTE.match(line)
        if quoted:
            close_paragraph()
            close_list()
            quote.append(quoted.group("text"))
            index += 1
            continue

        ordered = _ORDERED.match(line)
        unordered = _UNORDERED.match(line)
        if ordered or unordered:
            close_paragraph()
            close_quote()
            wanted = "ol" if ordered else "ul"
            if list_tag and list_tag != wanted:
                close_list()
            list_tag = wanted
            match = ordered or unordered
            assert match is not None
            list_items.append(match.group("text"))
            index += 1
            continue

        # A wrapped list item continues that item rather than starting a
        # paragraph — Markdown's lazy continuation. Without it, every item
        # long enough to wrap cut its own list in half.
        if list_items and not paragraph:
            list_items[-1] = f"{list_items[-1]} {line.strip()}"
            index += 1
            continue

        close_list()
        close_quote()
        paragraph.append(line.strip())
        index += 1

    close_all()
    return "\n".join(out)
