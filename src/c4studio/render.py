"""Headless SVG rendering of a view, via the bundled diagram renderer.

Layout and painting live in TypeScript (`packages/diagram-core`) because
that is where the web app's layout already lives; duplicating it in Python
would mean two implementations drifting apart, which is the mistake PP-88
existed to undo. The build bundles that code into a single dependency-free
ES module shipped inside this package, so rendering needs a ``node``
binary and nothing else — no npm install, no browser, no server.

``node`` is therefore required for :func:`render_view` **only**. Parsing,
Mermaid generation, JSON export and the web app are untouched by it, and a
missing binary is reported as an actionable error rather than a traceback.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from c4studio.icons import inline_icons
from c4studio.models import View, Workspace
from c4studio.webapp.graph import react_flow_graph

#: Environment variable pointing at a specific ``node`` binary, for
#: installations where it is not on ``PATH`` (nvm, conda, CI images).
NODE_ENV_VAR = "C4STUDIO_NODE"

#: The pre-rename spelling. Still honoured because this variable typically
#: lives in CI configuration that outlives a package rename.
LEGACY_NODE_ENV_VAR = "PYSTRUCTURIZR_NODE"

#: How long a single diagram may take before we give up on it.
RENDER_TIMEOUT_SECONDS = 60


class RenderError(Exception):
    """Raised when a diagram cannot be rendered."""


def renderer_script() -> Path:
    """Path to the bundled renderer shipped inside this package."""
    return Path(__file__).resolve().parent / "renderer" / "diagram-render.mjs"


def node_executable() -> str:
    """Locate ``node``, preferring an explicitly configured binary.

    Raises:
        RenderError: If no usable ``node`` can be found, with instructions.
    """
    configured = os.environ.get(NODE_ENV_VAR) or os.environ.get(LEGACY_NODE_ENV_VAR)
    if configured:
        if Path(configured).exists():
            return configured
        raise RenderError(
            f"{NODE_ENV_VAR} points at {configured}, which does not exist."
        )
    found = shutil.which("node")
    if found:
        return found
    raise RenderError(
        "rendering needs Node.js, which was not found on PATH. Install "
        "Node 18 or newer, or set "
        f"{NODE_ENV_VAR} to a node binary. Every other command "
        "(generate, export, check, webapp) works without it."
    )


def render_view(
    workspace: Workspace,
    view: View,
    *,
    padding: int = 24,
    title: str | None = None,
    show_title: bool = True,
    show_legend: bool = True,
) -> str:
    """Render ``view`` as a standalone SVG document.

    The graph payload is exactly what the web app's API serves, so the
    rendered positions come from the same layout code the browser runs —
    including any layout the user has saved for this view.

    Theme icons are fetched once each and embedded as ``data:`` URIs, so
    the result carries no external references; an icon that cannot be
    fetched is dropped and its element renders without one.

    Args:
        workspace: The workspace the view belongs to.
        view: The view to render.
        padding: Blank margin around the diagram bounds, in pixels.
        title: ``<title>`` for the document; defaults to the view's title.
        show_title: Draw the title as a heading above the diagram. The
            document ``<title>`` is written either way — it is metadata,
            not ink.
        show_legend: Draw the legend of styles used, when the view has any.

    Returns:
        A complete SVG document.

    Raises:
        RenderError: If Node is unavailable, the bundled renderer is
            missing, or the renderer fails.
    """
    script = renderer_script()
    if not script.exists():
        raise RenderError(
            f"the bundled renderer is missing ({script}). A source checkout "
            "needs `npm install && npm run build` at the repository root."
        )

    payload = react_flow_graph(workspace, view)
    # Theme icons are remote URLs; embedding them here keeps the rendered
    # file self-contained and keeps the Node side off the network.
    inline_icons(payload)
    command = [node_executable(), str(script), "--padding", str(padding)]
    caption = title if title is not None else (view.title or view.key)
    if caption:
        command += ["--title", caption]
    if not show_title:
        command.append("--no-title")
    if not show_legend:
        command.append("--no-legend")

    try:
        result = subprocess.run(
            command,
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=RENDER_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise RenderError(
            f"rendering {view.key} timed out after {RENDER_TIMEOUT_SECONDS}s"
        ) from exc
    except OSError as exc:
        raise RenderError(f"could not run the renderer: {exc}") from exc

    if result.returncode != 0:
        detail = result.stderr.strip() or f"exit code {result.returncode}"
        raise RenderError(f"rendering {view.key} failed: {detail}")
    return result.stdout
