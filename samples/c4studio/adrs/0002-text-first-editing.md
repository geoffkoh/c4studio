# 2. The editor edits text, never the model

Date: 2026-02-03

## Status

Accepted

## Context

Adding an in-browser editor raised the obvious question of whether it
should edit the DSL or edit the model and regenerate the DSL from it. The
second is what most modelling tools do.

It is not available to us. `parse_dsl` rewrites the source before
tokenising: `_expand_includes` flattens every `!include` into one string,
`_strip_scripts` deletes `!script` blocks, `_apply_constants` substitutes
`${NAME}` away. The tokeniser then discards comments and all whitespace. No
CST is retained and no serialiser exists.

## Decision

The editor edits DSL text. The diagram is a preview of the text. Saving
bumps the file's mtime, which is what the live-reload watcher already
notices — so save *is* the render trigger, and no second pipeline exists.

## Consequences

The author's comments, formatting and `!include` structure survive every
edit, because nothing ever rewrites them.

It also made the assistant almost free to add: it returns DSL text, which
is diffed against the buffer and applied by setting the buffer. Nothing
AI-specific touches the editor, the save path or the reload — the assistant
is one more producer of text.

The cost is that structural edits are the user's to type. We think that is
the right trade for a tool whose output is a file in a git repository.
