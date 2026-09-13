# c4studio, described in its own DSL

This workspace models the tool that renders it. It is dogfooding, but it is
also the clearest way to state the two decisions the codebase is organised
around.

## One parse, one view graph

`graph/view_graph.py` turns a workspace and a view into nodes and edges,
with C4 visibility, boundary nesting and endpoint lifting already applied.
Everything that draws — the web app, both Mermaid generators, the headless
SVG renderer — consumes that one output.

The consequence is worth stating plainly: a diagram exported in CI does not
merely resemble the one on screen, it is the same graph drawn twice. When
the two ever disagree, the bug is in a renderer, never in the semantics.

## Text-first, never model-first

c4studio edits DSL *text*. It never generates DSL from the model, and the
reason is structural rather than preferential: the parser rewrites the
source before tokenising — `!include` flattened into one string, `!script`
stripped, `${constants}` substituted — and then discards comments and
whitespace. No concrete syntax tree survives. A model-to-DSL writer would
have to reconstruct includes and constants from information that no longer
exists, and would destroy the author's comments and formatting on every
save.

So the diagram is a preview of the text, and saving is the render trigger.
The `SaveLoop` dynamic view traces exactly that.

## Local-first

There is no server, no account and no locking. Sharing happens through git
and through generated artifacts. The `Offline` filtered view shows what is
left when every component that can reach the network is removed, which is
nearly all of it — the assistant and the theme icon fetcher are the only
two, and the first is off unless asked for.
