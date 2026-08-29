"""View-level graph semantics: the shared contract between renderers.

:mod:`c4studio.graph.view_graph` turns a workspace + view into
``{nodes, edges}`` with C4 visibility rules already applied — abstraction
level per view type, boundary nesting, and relationship endpoints lifted to
their nearest visible ancestor.

Every renderer consumes this instead of re-deriving the semantics: the
web app's React Flow bridge, the Mermaid generator, and (in due course)
the headless SVG renderer. It depends only on
:mod:`c4studio.models` and :mod:`c4studio.themes`, so it stays
importable from the CLI without pulling in the web stack.
"""

from __future__ import annotations

from c4studio.graph.view_graph import (
    KIND_COLOURS,
    GraphData,
    GraphEdge,
    GraphNode,
    apply_positions,
    apply_sizes,
    base_view,
    build_view_graph,
)

__all__ = [
    "KIND_COLOURS",
    "GraphData",
    "GraphEdge",
    "GraphNode",
    "apply_positions",
    "apply_sizes",
    "base_view",
    "build_view_graph",
]
