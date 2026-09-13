# 3. Every renderer consumes one view graph

Date: 2025-11-20

## Status

Accepted

## Context

C4 view semantics are subtle: which elements are visible at a given
abstraction level, how boundaries nest, and how a relationship declared
between two components is lifted to the containers or systems that are
actually on the diagram. Getting that wrong is not a rendering bug, it is a
wrong diagram.

We have four things that draw: the web app, the Mermaid C4 generator, the
Mermaid flowchart generator, and the headless SVG renderer.

## Decision

`graph/view_graph.py` owns those semantics and emits `{nodes, edges}` with
visibility, nesting and lifting already applied. It depends only on
`models/` and `themes.py`. Every renderer consumes its output and decides
nothing for itself beyond paint.

## Consequences

A view semantics change lands in one place and is picked up by all four.
When two renderers disagree, the bug is in a renderer — the semantics are
not in question, which makes the disagreement cheap to diagnose.

The cost is a payload that carries more than any single renderer needs.
That has been worth it every time.
