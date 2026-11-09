"""Build the c4studio project site for GitHub Pages (PP-217).

The site is assembled from sources that already have to be true, so it
cannot drift from the product the way a hand-kept copy would:

- the DSL reference, keyword coverage and migration guide are the files
  in ``docs/``, whose examples the test suite parses;
- the guide pages in ``website/content/`` have their DSL examples parsed
  by the same test;
- the command-line reference is generated from the click commands;
- the keyboard shortcuts are read from ``frontend/src/shortcuts.ts``,
  the list the Studio's own help overlay shows;
- code is highlighted with the vocabulary in ``frontend/src/highlight.ts``,
  the SPA's one copy of it, rather than a second list;
- the live example is ``c4 publish`` of the model of this codebase.

Markdown goes through :mod:`c4studio.markdown`, the renderer the
published site already uses, so the site needs no dependency the package
does not have. Run it with::

    uv run python website/build.py -o website/_site
"""

from __future__ import annotations

import argparse
import html
import json
import keyword
import re
import shutil
import string
import warnings
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path

import click

from c4studio import markdown
from c4studio.cli.main import cli

ROOT = Path(__file__).resolve().parent.parent
WEBSITE = ROOT / "website"
CONTENT = WEBSITE / "content"
TEMPLATES = WEBSITE / "templates"
ASSETS = WEBSITE / "assets"

REPO_URL = "https://github.com/geoffkoh/c4studio"
BLOB_URL = f"{REPO_URL}/blob/main/"
TREE_URL = f"{REPO_URL}/tree/main/"
PYPI_URL = "https://pypi.org/project/c4studio/"

#: Where the site is served. Canonical links and the sitemap need it
#: absolute; everything else on the site is relative, so a local build
#: opens from ``file://``.
SITE_URL = "https://geoffkoh.github.io/c4studio/"

#: The workspace the live example publishes: the model of this codebase.
EXAMPLE_WORKSPACE = ROOT / "samples" / "c4studio" / "workspace.dsl"

#: Marker lines in a content page, replaced before it is rendered.
CLI_MARKER = "{{cli-reference}}"
SHORTCUTS_MARKER = "{{shortcuts}}"


@dataclass(frozen=True)
class Page:
    """One documentation page.

    Attributes:
        slug: Output file name without ``.html``.
        title: Sidebar and ``<title>`` text.
        source: The Markdown it is rendered from.
        section: Sidebar group.
        description: Meta description, for search results.
    """

    slug: str
    title: str
    source: Path
    section: str
    description: str


PAGES: tuple[Page, ...] = (
    Page(
        "getting-started",
        "Getting started",
        CONTENT / "getting-started.md",
        "Guide",
        "Install c4studio, write a first Structurizr DSL workspace and see it "
        "as C4 diagrams in minutes.",
    ),
    Page(
        "studio",
        "The Studio",
        CONTENT / "studio.md",
        "Guide",
        "The local web Studio: edit Structurizr DSL beside a live, interactive "
        "C4 diagram.",
    ),
    Page(
        "cli",
        "Command line",
        CONTENT / "cli.md",
        "Guide",
        "Every c4 command: check, lint, diff, impact, render, publish, export "
        "and more.",
    ),
    Page(
        "ci",
        "CI and automation",
        CONTENT / "ci.md",
        "Guide",
        "Lint, diff, render and publish C4 architecture models in GitHub Actions.",
    ),
    Page(
        "vscode",
        "VS Code",
        CONTENT / "vscode.md",
        "Guide",
        "The c4studio VS Code extension: highlighting, diagnostics and a C4 "
        "diagram preview.",
    ),
    Page(
        "python-api",
        "Python API",
        CONTENT / "python-api.md",
        "Guide",
        "Parse Structurizr DSL and JSON in Python and generate Mermaid C4 diagrams.",
    ),
    Page(
        "extensions",
        "Beyond Structurizr",
        CONTENT / "extensions.md",
        "Language",
        "What c4studio adds to the Structurizr DSL: c4studio.* properties, "
        "theme files, lint configuration and layout.",
    ),
    Page(
        "dsl-reference",
        "DSL reference",
        ROOT / "docs" / "dsl-reference.md",
        "Language",
        "How to write Structurizr DSL for c4studio: every construct, with "
        "examples the test suite parses.",
    ),
    Page(
        "dsl-support",
        "Keyword coverage",
        ROOT / "docs" / "dsl-support.md",
        "Language",
        "Every keyword in the Structurizr DSL and what c4studio does with it.",
    ),
    Page(
        "migration",
        "Migration guide",
        ROOT / "docs" / "MIGRATION.md",
        "Reference",
        "Changes between c4studio releases, and what to do about them.",
    ),
)

#: Sidebar groups, in order.
SECTIONS: tuple[str, ...] = ("Guide", "Language", "Reference")


class SiteBuildError(Exception):
    """A source the site is built from is missing or malformed."""


# --------------------------------------------------------------------------
# Sources read from the frontend
# --------------------------------------------------------------------------


def _ts_string_set(source: str, name: str) -> frozenset[str]:
    """The strings in ``export const <name> ... = new Set([...])``."""
    match = re.search(
        rf"export const {name}\b[^=]*=\s*new Set\(\[(.*?)\]\)", source, re.DOTALL
    )
    if match is None:
        raise SiteBuildError(f"{name} not found in frontend/src/highlight.ts")
    body = re.sub(r"//[^\n]*", "", match.group(1))
    return frozenset(re.findall(r'"([^"]+)"', body))


def dsl_vocabulary() -> tuple[frozenset[str], frozenset[str]]:
    """The DSL keywords and properties, from the SPA's one copy of them.

    Returns:
        ``(keywords, properties)``, lower-cased as ``highlight.ts`` keeps
        them; the DSL is case-insensitive.
    """
    source = (ROOT / "frontend" / "src" / "highlight.ts").read_text(encoding="utf-8")
    return _ts_string_set(source, "DSL_KEYWORDS"), _ts_string_set(
        source, "DSL_PROPERTIES"
    )


def studio_shortcuts() -> dict[str, list[tuple[str, str]]]:
    """The Studio's gestures and keyboard shortcuts, as its help shows them.

    Returns:
        ``{"GESTURES": [(keys, action), ...], "SHORTCUTS": [...]}``.
    """
    source = (ROOT / "frontend" / "src" / "shortcuts.ts").read_text(encoding="utf-8")
    found: dict[str, list[tuple[str, str]]] = {}
    for name in ("GESTURES", "SHORTCUTS"):
        match = re.search(
            rf"export const {name}\b.*?=\s*\[(.*?)\n\];", source, re.DOTALL
        )
        if match is None:
            raise SiteBuildError(f"{name} not found in frontend/src/shortcuts.ts")
        pairs = re.findall(
            r'keys:\s*"([^"]+)",\s*action:\s*"([^"]+)"', match.group(1), re.DOTALL
        )
        if not pairs:
            raise SiteBuildError(f"{name} in frontend/src/shortcuts.ts has no entries")
        found[name] = pairs
    return found


def shortcuts_markdown() -> str:
    """The shortcut tables for the Studio page."""
    lists = studio_shortcuts()
    out = ["| Key | Action |", "| --- | --- |"]
    out.extend(f"| `{keys}` | {action} |" for keys, action in lists["SHORTCUTS"])
    out.extend(["", "| Gesture | Action |", "| --- | --- |"])
    out.extend(f"| {keys} | {action} |" for keys, action in lists["GESTURES"])
    return "\n".join(out)


# --------------------------------------------------------------------------
# The command-line reference, generated from click
# --------------------------------------------------------------------------


def _cell(text: str) -> str:
    """Text safe inside a Markdown table cell."""
    return " ".join(text.split()).replace("|", "\\|")


def _option_row(param: click.Parameter) -> str:
    names = ", ".join(f"`{name}`" for name in [*param.opts, *param.secondary_opts])
    help_text = _cell((getattr(param, "help", None) or "").replace("``", "`"))
    default = param.default
    if (
        isinstance(param, click.Option)
        and param.show_default
        and default not in (None, False, (), "")
        and not callable(default)
    ):
        help_text = f"{help_text} Default: `{default}`.".strip()
    return f"| {names} | {help_text} |"


def cli_markdown() -> str:
    """A reference section for every ``c4`` command.

    Returns:
        Markdown: one ``###`` section per command, with its usage, its
        help text and a table of its options.
    """
    context = click.Context(cli, info_name="c4")
    out: list[str] = []
    for name in sorted(cli.list_commands(context)):
        command = cli.get_command(context, name)
        if command is None or command.hidden:
            continue
        sub = click.Context(command, info_name=name, parent=context)
        usage = " ".join(command.collect_usage_pieces(sub))
        out.extend(
            [f"### c4 {name}", "", "```bash", f"c4 {name} {usage}".rstrip(), "```", ""]
        )
        # Docstrings use reST's ``code``; Markdown wants one backtick.
        help_text = (command.help or "").split("\f")[0].replace("``", "`")
        paragraphs = [" ".join(p.split()) for p in help_text.strip().split("\n\n")]
        out.extend(f"{p}\n" for p in paragraphs if p)
        options = [
            p for p in command.params if isinstance(p, click.Option) and not p.hidden
        ]
        if options:
            out.extend(["| Option | What it does |", "| --- | --- |"])
            out.extend(_option_row(p) for p in options)
            out.append("")
    return "\n".join(out)


# --------------------------------------------------------------------------
# HTML post-processing
# --------------------------------------------------------------------------


def slugify(text: str) -> str:
    """A heading's anchor, the way GitHub makes it.

    Matching GitHub keeps the anchors in ``docs/`` links working on the
    site: ``## 10. c4studio's own extensions`` is
    ``#10-c4studios-own-extensions`` in both places.
    """
    plain = html.unescape(re.sub(r"<[^>]+>", "", text)).strip().lower()
    plain = re.sub(r"[^\w\- ]", "", plain)
    return plain.replace(" ", "-")


@dataclass
class Heading:
    """A heading found on a page, for its table of contents and search."""

    level: int
    text: str
    anchor: str
    snippet: str = ""


def add_heading_ids(fragment: str) -> tuple[str, list[Heading]]:
    """Give every ``h1``–``h4`` an id and a self-link.

    Returns:
        The fragment, and the headings in document order.
    """
    seen: dict[str, int] = {}
    headings: list[Heading] = []

    def replace(match: re.Match[str]) -> str:
        level, inner = int(match.group(1)), match.group(2)
        anchor = slugify(inner) or "section"
        count = seen.get(anchor, 0)
        seen[anchor] = count + 1
        if count:
            anchor = f"{anchor}-{count}"
        headings.append(Heading(level, re.sub(r"<[^>]+>", "", inner), anchor))
        return (
            f'<h{level} id="{anchor}">{inner}'
            f'<a class="anchor" href="#{anchor}" aria-label="Link to this section">#</a>'
            f"</h{level}>"
        )

    out = re.sub(r"<h([1-4])>(.*?)</h\1>", replace, fragment)
    # A snippet for search: the text after each heading, up to the next.
    parts = re.split(r'<h[1-4] id="[^"]+">.*?</h[1-4]>', out)
    for heading, body in zip(headings, parts[1:], strict=True):
        text = html.unescape(re.sub(r"<[^>]+>", " ", body))
        heading.snippet = " ".join(text.split())[:240]
    return out, headings


def table_of_contents(headings: Iterable[Heading]) -> str:
    """The "On this page" list: ``h2`` and ``h3`` only."""
    items = [
        f'<li class="toc-l{h.level}"><a href="#{h.anchor}">{h.text}</a></li>'
        for h in headings
        if h.level in (2, 3)
    ]
    if not items:
        return ""
    return '<p class="toc-title">On this page</p><ul>' + "".join(items) + "</ul>"


def rewrite_links(fragment: str, source: Path, page_for: dict[Path, str]) -> str:
    """Point a page's relative links at the site, or at GitHub.

    A link to another documented Markdown file becomes that page; any
    other path in the repository becomes its GitHub URL, since the site
    does not carry the source. Absolute URLs and same-page anchors are
    left alone.
    """

    def replace(match: re.Match[str]) -> str:
        attribute, target = match.group(1), html.unescape(match.group(2))
        if re.match(r"^[a-z][a-z0-9+.-]*:", target, re.IGNORECASE) or target.startswith(
            "#"
        ):
            return match.group(0)
        path_part, _, anchor = target.partition("#")
        resolved = (source.parent / path_part).resolve()
        suffix = f"#{anchor}" if anchor else ""
        if resolved in page_for:
            new = f"{page_for[resolved]}.html{suffix}"
        elif attribute == "src" and resolved.is_relative_to(ROOT / "docs" / "images"):
            new = f"assets/images/{resolved.name}"
        elif resolved.is_relative_to(ROOT) and resolved.exists():
            relative = resolved.relative_to(ROOT).as_posix()
            base = TREE_URL if resolved.is_dir() else BLOB_URL
            new = f"{base}{relative}{suffix}"
        else:
            return match.group(0)
        return f'{attribute}="{html.escape(new)}"'

    return re.sub(r'\b(href|src)="([^"]*)"', replace, fragment)


def wrap_tables(fragment: str) -> str:
    """Let a wide table scroll inside its own box on a narrow screen."""
    return re.sub(
        r"<table>(.*?)</table>",
        r'<div class="table-wrap"><table>\1</table></div>',
        fragment,
        flags=re.DOTALL,
    )


# --------------------------------------------------------------------------
# Syntax highlighting
# --------------------------------------------------------------------------

Token = tuple[str, str]  # (css class or "", text)


def _span(css: str, text: str) -> str:
    escaped = html.escape(text, quote=False)
    return f'<span class="tok-{css}">{escaped}</span>' if css else escaped


class Highlighter:
    """Small tokenizers for the languages the docs show.

    Deliberately shallow: comments, strings, keywords and a few shapes.
    The DSL tokenizer follows ``DSL_PATTERNS`` in ``highlight.ts`` and takes
    its words from that file, so the site paints DSL the way the editor does.
    """

    def __init__(self) -> None:
        self.keywords, self.properties = dsl_vocabulary()

    def dsl(self, code: str) -> list[Token]:
        pattern = re.compile(
            r"(?P<block>/\*.*?\*/)"
            r"|(?P<line>//[^\n]*)"
            r"|(?P<hash>(?:(?<=\n)|^)[ \t]*#[^\n]*)"
            r'|(?P<text>"""\s*\n.*?"""|"""\s*$)'
            r'|(?P<string>"(?:[^"\\\n]|\\.)*")'
            r"|(?P<color>#[0-9A-Fa-f]{3,8}\b)"
            r"|(?P<arrow>->)"
            r"|(?P<directive>![A-Za-z]+)"
            r"|(?P<word>[A-Za-z_][A-Za-z0-9_]*)"
            r"|(?P<number>\b[0-9]+\b)",
            re.DOTALL,
        )
        tokens: list[Token] = []
        position = 0
        for match in pattern.finditer(code):
            tokens.append(("", code[position : match.start()]))
            kind, text = match.lastgroup or "", match.group(0)
            if kind in ("block", "line", "hash"):
                tokens.append(("comment", text))
            elif kind in ("text", "string"):
                extension = text.startswith('"c4studio.')
                tokens.append(("ext" if extension else "string", text))
            elif kind == "word":
                lower = text.lower()
                after = code[match.end() : match.end() + 4]
                if re.match(r"[ \t]*=(?!=)", after):
                    tokens.append(("def", text))
                elif lower in self.keywords:
                    tokens.append(("keyword", text))
                elif lower in self.properties:
                    tokens.append(("property", text))
                else:
                    tokens.append(("", text))
            else:
                tokens.append((kind, text))
            position = match.end()
        tokens.append(("", code[position:]))
        return tokens

    @staticmethod
    def _generic(
        code: str, rules: list[tuple[str, str]], flags: int = 0
    ) -> list[Token]:
        pattern = re.compile("|".join(f"(?P<{name}>{rx})" for name, rx in rules), flags)
        tokens: list[Token] = []
        position = 0
        for match in pattern.finditer(code):
            tokens.append(("", code[position : match.start()]))
            tokens.append((match.lastgroup or "", match.group(0)))
            position = match.end()
        tokens.append(("", code[position:]))
        return tokens

    def bash(self, code: str) -> list[Token]:
        return self._generic(
            code,
            [
                ("comment", r"(?:(?<=\s)|^)#[^\n]*"),
                ("string", r'"(?:[^"\\]|\\.)*"|\'[^\']*\''),
                (
                    "command",
                    r"(?:(?<=\n)|^)[ \t]*(?:uv run |uvx (?:--from \S+ )?)?c4\b",
                ),
                (
                    "keyword",
                    r"(?:(?<=\n)|^)[ \t]*(?:pipx|pip|uv|uvx|npm|code|git|export|cd)\b",
                ),
                ("property", r"(?<=\s)--?[A-Za-z][\w-]*"),
            ],
            re.MULTILINE,
        )

    def yaml(self, code: str) -> list[Token]:
        return self._generic(
            code,
            [
                ("comment", r"(?:(?<=\s)|^)#[^\n]*"),
                ("string", r'"(?:[^"\\]|\\.)*"|\'[^\']*\''),
                ("property", r"(?:(?<=\n)|^)[ \t]*(?:- )?[\w.-]+(?=:)"),
                ("keyword", r"\$\{\{[^}]*\}\}"),
            ],
            re.MULTILINE,
        )

    def json(self, code: str) -> list[Token]:
        return self._generic(
            code,
            [
                ("property", r'"(?:[^"\\]|\\.)*"(?=\s*:)'),
                ("string", r'"(?:[^"\\]|\\.)*"'),
                ("number", r"\b-?\d+(?:\.\d+)?\b|\btrue\b|\bfalse\b|\bnull\b"),
            ],
        )

    def python(self, code: str) -> list[Token]:
        words = "|".join(sorted(keyword.kwlist, key=len, reverse=True))
        return self._generic(
            code,
            [
                ("comment", r"#[^\n]*"),
                (
                    "string",
                    r'"""[\s\S]*?"""|"(?:[^"\\\n]|\\.)*"|\'(?:[^\'\\\n]|\\.)*\'',
                ),
                ("keyword", rf"\b(?:{words})\b"),
                ("def", r"\b[A-Z][A-Za-z0-9]+(?=\()"),
            ],
        )

    def highlight(self, language: str, code: str) -> str | None:
        """``code`` as highlighted HTML, or ``None`` for an unknown language."""
        aliases = {
            "sh": "bash",
            "shell": "bash",
            "console": "bash",
            "yml": "yaml",
            "py": "python",
        }
        method: Callable[[str], list[Token]] | None = {
            "dsl": self.dsl,
            "structurizr": self.dsl,
            "bash": self.bash,
            "yaml": self.yaml,
            "json": self.json,
            "python": self.python,
        }.get(aliases.get(language, language))
        if method is None:
            return None
        return "".join(_span(css, text) for css, text in method(code) if text)


def highlight_code(fragment: str, highlighter: Highlighter) -> str:
    """Highlight every fenced block that names a language we know."""

    def replace(match: re.Match[str]) -> str:
        language, code = match.group(1), html.unescape(match.group(2))
        painted = highlighter.highlight(language, code)
        body = painted if painted is not None else match.group(2)
        return (
            f'<div class="code" data-lang="{html.escape(language)}">'
            f'<pre><code class="language-{html.escape(language)}">{body}</code></pre></div>'
        )

    fragment = re.sub(
        r'<pre><code class="language-([\w+-]+)">(.*?)</code></pre>',
        replace,
        fragment,
        flags=re.DOTALL,
    )
    # Unlabelled blocks still get the frame and the copy button.
    return re.sub(
        r"(?<!>)<pre><code>(.*?)</code></pre>",
        r'<div class="code"><pre><code>\1</code></pre></div>',
        fragment,
        flags=re.DOTALL,
    )


# --------------------------------------------------------------------------
# Pages
# --------------------------------------------------------------------------


def _template(name: str) -> string.Template:
    return string.Template((TEMPLATES / name).read_text(encoding="utf-8"))


def sidebar(current: str) -> str:
    """The documentation navigation, with ``current`` marked."""
    out: list[str] = []
    for section in SECTIONS:
        out.append(f'<p class="nav-section">{section}</p><ul>')
        for page in PAGES:
            if page.section != section:
                continue
            attrs = (
                ' class="active" aria-current="page"' if page.slug == current else ""
            )
            out.append(
                f'<li><a href="{page.slug}.html"{attrs}>{html.escape(page.title)}</a></li>'
            )
        out.append("</ul>")
    out.append('<p class="nav-section">See it</p><ul>')
    out.append('<li><a href="example/index.html">Live example ↗</a></li></ul>')
    return "".join(out)


def page_source(page: Page) -> str:
    """A page's Markdown, with its generated sections filled in."""
    text = page.source.read_text(encoding="utf-8")
    text = text.replace(CLI_MARKER, cli_markdown())
    return text.replace(SHORTCUTS_MARKER, shortcuts_markdown())


def render_page(
    page: Page, highlighter: Highlighter, page_for: dict[Path, str], release: str
) -> tuple[str, list[Heading]]:
    """One documentation page as a complete HTML document."""
    fragment = markdown.render(page_source(page))
    fragment, headings = add_heading_ids(fragment)
    fragment = rewrite_links(fragment, page.source, page_for)
    fragment = wrap_tables(highlight_code(fragment, highlighter))

    index = PAGES.index(page)
    previous = PAGES[index - 1] if index else None
    following = PAGES[index + 1] if index + 1 < len(PAGES) else None
    pager = '<nav class="pager" aria-label="Previous and next page">'
    if previous:
        pager += f'<a class="prev" href="{previous.slug}.html"><span>Previous</span>{html.escape(previous.title)}</a>'
    if following:
        pager += f'<a class="next" href="{following.slug}.html"><span>Next</span>{html.escape(following.title)}</a>'
    pager += "</nav>"

    edit = f"{BLOB_URL}{page.source.relative_to(ROOT).as_posix()}"
    document = _template("page.html").substitute(
        title=html.escape(page.title),
        description=html.escape(page.description),
        canonical=f"{SITE_URL}{page.slug}.html",
        sidebar=sidebar(page.slug),
        content=fragment,
        toc=table_of_contents(headings),
        pager=pager,
        edit=edit,
        version=release,
        repo=REPO_URL,
        pypi=PYPI_URL,
    )
    return document, headings


def render_home(release: str) -> str:
    """The landing page."""
    return _template("home.html").substitute(
        version=release,
        canonical=SITE_URL,
        repo=REPO_URL,
        pypi=PYPI_URL,
        site=SITE_URL,
    )


def build_example(out_dir: Path) -> None:
    """Publish the model of this codebase as the live example.

    Uses ``c4 publish`` itself, with a fresh auto-layout: layout sidecars
    are per-user state and never committed, so CI has none, and a local
    build should produce what CI does.
    """
    from c4studio.parser.dsl import parse_dsl_file
    from c4studio.publish import publish

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        workspace = parse_dsl_file(EXAMPLE_WORKSPACE)
    publish(workspace, out_dir, layout_source=None, clean=True)
    banner = (
        '<div style="font:14px/1.4 system-ui,sans-serif;padding:8px 16px;'
        'background:#0f172a;color:#e2e8f0">'
        '<a href="../index.html" style="color:#93c5fd">← c4studio</a> · '
        "This site was generated by <code>c4 publish</code> from "
        f'<a style="color:#93c5fd" href="{BLOB_URL}samples/c4studio/workspace.dsl">'
        "the model of c4studio itself</a>.</div>"
    )
    for page in out_dir.rglob("*.html"):
        text = page.read_text(encoding="utf-8")
        depth = len(page.relative_to(out_dir).parts) - 1
        local = banner.replace("../index.html", "../" * (depth + 1) + "index.html")
        # The banner holds no backslashes, so it is safe as a replacement.
        text = re.sub(r"(<body[^>]*>)", r"\g<1>" + local, text, count=1)
        page.write_text(text, encoding="utf-8")


def sitemap(urls: Iterable[str]) -> str:
    """A sitemap of the site's pages, for search engines."""
    entries = "".join(f"<url><loc>{html.escape(url)}</loc></url>" for url in urls)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{entries}</urlset>\n'
    )


def build(out_dir: Path, *, example: bool = True) -> list[Path]:
    """Build the whole site into ``out_dir``, replacing what is there.

    Args:
        out_dir: Directory to write into.
        example: Publish the live example. It needs Node (``c4 publish``
            renders with it), so tests leave it out.

    Returns:
        The documentation and landing pages written, not the example's.
    """
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    release = version("c4studio")
    highlighter = Highlighter()
    page_for = {page.source.resolve(): page.slug for page in PAGES}

    written: list[Path] = []
    search: list[dict[str, str]] = []
    for page in PAGES:
        document, headings = render_page(page, highlighter, page_for, release)
        target = out_dir / f"{page.slug}.html"
        target.write_text(document, encoding="utf-8")
        written.append(target)
        search.extend(
            {
                "p": page.title,
                "h": html.unescape(heading.text),
                # The page's own title links to the page, not its top anchor.
                "u": f"{page.slug}.html"
                + (f"#{heading.anchor}" if heading.level > 1 else ""),
                "x": heading.snippet,
            }
            for heading in headings
        )

    home = out_dir / "index.html"
    home.write_text(render_home(release), encoding="utf-8")
    written.append(home)
    not_found = out_dir / "404.html"
    not_found.write_text(
        _template("404.html").substitute(version=release, site=SITE_URL, repo=REPO_URL),
        encoding="utf-8",
    )
    written.append(not_found)

    shutil.copytree(ASSETS, out_dir / "assets")
    shutil.copytree(ROOT / "docs" / "images", out_dir / "assets" / "images")
    (out_dir / "assets" / "search-index.js").write_text(
        "window.C4_SEARCH="
        + json.dumps(search, ensure_ascii=False, separators=(",", ":"))
        + ";\n",
        encoding="utf-8",
    )
    # Serve files as they are: no Jekyll pass over the output.
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")
    urls = [SITE_URL, *(f"{SITE_URL}{page.slug}.html" for page in PAGES)]
    if example:
        build_example(out_dir / "example")
        urls.append(f"{SITE_URL}example/index.html")
    (out_dir / "sitemap.xml").write_text(sitemap(urls), encoding="utf-8")
    (out_dir / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}sitemap.xml\n", encoding="utf-8"
    )
    return written


def main() -> None:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("-o", "--output", type=Path, default=WEBSITE / "_site")
    parser.add_argument(
        "--no-example",
        action="store_true",
        help="Skip the live example, which needs Node.",
    )
    args = parser.parse_args()
    pages = build(args.output, example=not args.no_example)
    print(f"Wrote {len(pages)} pages to {args.output}")


if __name__ == "__main__":
    main()
