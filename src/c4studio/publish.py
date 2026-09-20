"""A static site for the model (PP-188).

c4studio has a complete authoring loop — write, see, arrange, render,
commit — and no consumption loop: reading the model has meant installing
c4studio and opening a file. This is the other half. Every view as a
page, the `!docs` prose and the ADRs beside them, navigation between, and
nothing to install for whoever reads it.

**One page per view, not one page with a switcher.** The test is whether
a link survives being pasted into a ticket or a wiki: a page per view can
be linked to, bookmarked and diffed; a switcher makes every diagram the
same URL.

**Self-contained by construction.** Diagrams are inlined SVG, and the
renderer already embeds theme icons as `data:` URIs, so a published
folder has no external references at all — no CDN, no fonts, no network.
Open it from a file:// path on a locked-down laptop and it is the same
site.
"""

from __future__ import annotations

import html
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from c4studio.markdown import render as render_markdown
from c4studio.models import View, Workspace
from c4studio.render import render_view
from c4studio.webapp.graph import is_supported

#: One stylesheet for the site, written once and linked by every page.
STYLESHEET = """\
:root {
  --bg: #ffffff;
  --text: #1c2530;
  --muted: #6b7684;
  --border: #e2e5ea;
  --accent: #1976d2;
  --sidebar: 260px;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  font: 15px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
        Helvetica, Arial, sans-serif;
  color: var(--text);
  background: var(--bg);
}
.layout { display: flex; min-height: 100vh; align-items: stretch; }
nav {
  width: var(--sidebar);
  flex: 0 0 var(--sidebar);
  border-right: 1px solid var(--border);
  padding: 24px 20px;
  overflow-y: auto;
}
nav h1 { font-size: 16px; margin: 0 0 4px; }
nav .subtitle { color: var(--muted); font-size: 13px; margin-bottom: 20px; }
nav h2 {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--muted);
  margin: 20px 0 8px;
}
nav ul { list-style: none; margin: 0; padding: 0; }
nav li { margin: 2px 0; }
nav a { color: var(--text); text-decoration: none; display: block; padding: 3px 0; }
nav a:hover { color: var(--accent); }
nav a.current { color: var(--accent); font-weight: 600; }
nav .kind { color: var(--muted); font-size: 12px; }
main { flex: 1; padding: 32px 40px; min-width: 0; max-width: 1100px; }
main h1 { font-size: 24px; margin: 0 0 4px; }
main .subtitle { color: var(--muted); margin: 0 0 24px; }
.diagram { border: 1px solid var(--border); border-radius: 8px; padding: 16px; }
.diagram svg { width: 100%; height: auto; display: block; }
table { border-collapse: collapse; margin: 16px 0; }
th, td { border: 1px solid var(--border); padding: 6px 10px; text-align: left; }
th { background: #f5f6f8; }
pre {
  background: #f5f6f8;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 12px;
  overflow-x: auto;
}
code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 13px; }
pre code { font-size: 12.5px; }
blockquote {
  margin: 16px 0;
  padding: 4px 16px;
  border-left: 3px solid var(--border);
  color: var(--muted);
}
.status {
  display: inline-block;
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 10px;
  background: #e8f1fb;
  color: var(--accent);
}
footer { color: var(--muted); font-size: 12px; margin-top: 40px; }
@media (max-width: 800px) {
  .layout { display: block; }
  nav { width: auto; border-right: none; border-bottom: 1px solid var(--border); }
  main { padding: 24px 20px; }
}
"""


@dataclass(frozen=True)
class Page:
    """One page of the site.

    Attributes:
        path: Where it is written, relative to the output directory.
        title: Its heading and nav label.
        group: Which nav section it belongs to.
        subtitle: Small print under the nav label, such as a view type.
    """

    path: str
    title: str
    group: str
    subtitle: str = ""


def _slug(text: str) -> str:
    """A filename-safe form of ``text``."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", text.strip()).strip("-")
    return cleaned.lower() or "untitled"


def _nav(pages: list[Page], current: str, workspace: Workspace) -> str:
    """The navigation column, identical on every page."""
    groups: dict[str, list[Page]] = {}
    for page in pages:
        groups.setdefault(page.group, []).append(page)

    parts = [
        "<nav>",
        f"<h1>{html.escape(workspace.name or 'Workspace')}</h1>",
    ]
    if workspace.description:
        parts.append(
            f'<div class="subtitle">{html.escape(workspace.description)}</div>'
        )
    for group, items in groups.items():
        parts.append(f"<h2>{html.escape(group)}</h2><ul>")
        for page in items:
            depth = current.count("/")
            href = ("../" * depth) + page.path
            css = ' class="current"' if page.path == current else ""
            label = html.escape(page.title)
            subtitle = (
                f'<div class="kind">{html.escape(page.subtitle)}</div>'
                if page.subtitle
                else ""
            )
            parts.append(f'<li><a href="{href}"{css}>{label}{subtitle}</a></li>')
        parts.append("</ul>")
    parts.append("</nav>")
    return "".join(parts)


def _page(
    *,
    title: str,
    body: str,
    pages: list[Page],
    current: str,
    workspace: Workspace,
) -> str:
    """Wrap ``body`` in the site's chrome."""
    depth = current.count("/")
    stylesheet = ("../" * depth) + "site.css"
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{html.escape(title)}</title>\n"
        f'<link rel="stylesheet" href="{stylesheet}">\n'
        "</head>\n<body>\n"
        '<div class="layout">'
        + _nav(pages, current, workspace)
        + f"<main>{body}</main>"
        + "</div>\n</body>\n</html>\n"
    )


def _view_pages(workspace: Workspace) -> list[tuple[View, Page]]:
    """A page for every view a renderer can draw."""
    found: list[tuple[View, Page]] = []
    for view in workspace.views:
        if not is_supported(view):
            continue
        page = Page(
            path=f"views/{_slug(view.key)}.html",
            title=view.title or view.key,
            group="Views",
            subtitle=view.type.value,
        )
        found.append((view, page))
    return found


def publish(
    workspace: Workspace,
    out_dir: Path,
    *,
    layout_source: Path | None = None,
    perspective: str | None = None,
    clean: bool = False,
) -> list[Path]:
    """Write a self-contained site for ``workspace``.

    Args:
        workspace: The parsed workspace.
        out_dir: Directory to write into; created if absent.
        layout_source: Root source file whose layout sidecar to honour,
            so published diagrams match what was arranged. ``None``
            renders a fresh auto-layout.
        perspective: Draw every diagram with this perspective shown.
        clean: Remove ``out_dir`` first. Off by default: publishing into
            a directory should not be a way to lose what is already in
            it.

    Returns:
        Every file written, in the order it was written.

    Raises:
        RenderError: If Node is unavailable or a view fails to render —
            a site with a missing diagram is worse than no site.
    """
    if clean and out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    views = _view_pages(workspace)
    sections = sorted(workspace.documentation.sections, key=lambda s: s.order)
    decisions = workspace.documentation.decisions

    pages: list[Page] = [Page(path="index.html", title="Overview", group="Start")]
    pages.extend(page for _, page in views)
    section_pages = [
        (
            section,
            Page(
                path=f"docs/{index + 1:02d}-{_slug(section.title)}.html",
                title=section.title or f"Section {index + 1}",
                group="Documentation",
            ),
        )
        for index, section in enumerate(sections)
    ]
    pages.extend(page for _, page in section_pages)
    decision_pages = [
        (
            decision,
            Page(
                path=f"decisions/{_slug(decision.id or str(index + 1))}.html",
                title=decision.title or f"Decision {decision.id}",
                group="Decisions",
                subtitle=decision.status,
            ),
        )
        for index, decision in enumerate(decisions)
    ]
    pages.extend(page for _, page in decision_pages)

    written: list[Path] = []

    def write(relative: str, text: str) -> None:
        target = out_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        written.append(target)

    write("site.css", STYLESHEET)

    # Views.
    for view, page in views:
        svg = render_view(
            workspace,
            view,
            layout_source=layout_source,
            perspective=perspective,
            # The page supplies the heading, so the diagram need not.
            show_title=False,
        )
        body = [f"<h1>{html.escape(page.title)}</h1>"]
        if view.description:
            body.append(f'<p class="subtitle">{html.escape(view.description)}</p>')
        body.append(f'<div class="diagram">{svg}</div>')
        write(
            page.path,
            _page(
                title=page.title,
                body="".join(body),
                pages=pages,
                current=page.path,
                workspace=workspace,
            ),
        )

    # Documentation.
    for section, page in section_pages:
        # A section that opens with its own `# Heading` supplies the
        # title; adding ours as well printed it twice.
        own_heading = section.content.lstrip().startswith("# ")
        heading = "" if own_heading else f"<h1>{html.escape(page.title)}</h1>"
        write(
            page.path,
            _page(
                title=page.title,
                body=heading + render_markdown(section.content),
                pages=pages,
                current=page.path,
                workspace=workspace,
            ),
        )

    # Decisions.
    for decision, page in decision_pages:
        intro: list[str] = [
            f"<h1>{html.escape(page.title)}</h1>",
            '<p class="subtitle">',
        ]
        if decision.status:
            intro.append(f'<span class="status">{html.escape(decision.status)}</span>')
        if decision.date:
            intro.append(f" {html.escape(decision.date)}")
        intro.append("</p>")
        write(
            page.path,
            _page(
                title=page.title,
                body="".join(intro) + render_markdown(decision.content),
                pages=pages,
                current=page.path,
                workspace=workspace,
            ),
        )

    # The overview goes last: it counts what the rest of the run produced.
    summary = [
        f"<h1>{html.escape(workspace.name or 'Workspace')}</h1>",
    ]
    if workspace.description:
        summary.append(f'<p class="subtitle">{html.escape(workspace.description)}</p>')
    summary.append(
        "<table><thead><tr><th>Views</th><th>Documentation</th>"
        "<th>Decisions</th></tr></thead><tbody><tr>"
        f"<td>{len(views)}</td><td>{len(section_pages)}</td>"
        f"<td>{len(decision_pages)}</td></tr></tbody></table>"
    )
    if views:
        summary.append("<h2>Views</h2><ul>")
        for _, page in views:
            summary.append(
                f'<li><a href="{page.path}">{html.escape(page.title)}</a> '
                f'<span class="kind">{html.escape(page.subtitle)}</span></li>'
            )
        summary.append("</ul>")
    summary.append(
        "<footer>Generated by c4studio. Every diagram is inlined SVG, so this "
        "folder needs no network and no server.</footer>"
    )
    write(
        "index.html",
        _page(
            title=workspace.name or "Workspace",
            body="".join(summary),
            pages=pages,
            current="index.html",
            workspace=workspace,
        ),
    )
    return written
