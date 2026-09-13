# Why Node appears exactly once

c4studio is a Python tool, and one container in this model runs JavaScript
at run time: the **Headless Renderer**.

The alternative was to reimplement layout in Python. That was rejected: the
layout is compound dagre, it already exists in `diagram-core`, and a second
implementation would drift from the first in ways nobody would notice until
an exported diagram looked subtly wrong.

Instead `diagram-core` is bundled for Node and committed into the wheel, so
`c4 render` works without an `npm install`. Node is needed by that one
command and nothing else — parsing, Mermaid generation, JSON export and the
entire web app work without it.

This is also why `packages/diagram-core` must never depend on the DOM or on
application state. It is consumed twice: once in a browser, once in a Node
process with neither. The `DiagramCoreComponents` view shows the pieces that
constraint protects.
