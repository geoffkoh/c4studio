# c4studio for VS Code

Structurizr DSL support in VS Code, powered by
[c4studio](https://github.com/geoffkoh/c4studio).

## Features

- **Syntax highlighting** for `.dsl` / `.structurizr` files: element and
  view keywords, style properties, `!include`/`!docs`/`!adrs` directives
  with their paths, strings, comments, `#hex` colours, `->`
  relationships, `alias =` definitions. The grammar mirrors the token
  spec used by the web app's source viewer
  (`frontend/src/highlight.ts`).
- **Language basics**: comment toggling, brace/quote auto-close,
  indentation on `{`.
- **Problem reporting**: parse errors and skipped constructs appear as
  squiggles and in the Problems panel. A syntax grammar cannot validate
  anything, so these come from the parser itself via
  `c4 check --json` — the same backend the preview uses, so
  there is one implementation of the language's rules. Problems inside an
  `!include`-ed fragment are reported against the fragment, not the file
  that included it. Checking happens as you type (debounced) as well as on
  open and save: the buffer is piped to the checker, so unsaved edits are
  checked as written. `!include`-ed fragments are still read from disk, so
  a problem introduced in an unsaved fragment appears once it is saved.
  Disable with `c4studio.diagnostics.enabled`.
- **Interactive C4 diagram preview**: the "Pystructurizr: Open Diagram
  Preview" command (also a button in the editor title bar of DSL files)
  opens the full c4studio React Flow app beside your editor — view
  sidebar, drag layouts, in-place expansion, themes and cloud-provider
  icons, filtered views, dynamic-view animation, keyboard shortcuts.
  Saving the DSL file (or any `!include` fragment) refreshes the preview
  automatically within ~2 seconds.

## How the preview works

The extension spawns a local `c4studio webapp` server for the file
(bound to `127.0.0.1` on a free port) and embeds it in a webview. The
server is killed when the preview panel closes. Its logs go to the
"c4studio" output channel.

**No setup is required.** The backend is resolved automatically, first
match wins (each attempt is logged to the output channel):

1. the `c4studio.serverCommand` setting, when set — always wins;
2. `c4studio` already on your PATH (`pipx install
   c4studio-studio`);
3. your workspace's own environment via `uv run` (when the folder has a
   `pyproject.toml`/`uv.lock` and uv is installed);
4. `uv tool run` installing
   [`c4studio`](https://pypi.org/project/c4studio-studio/)
   from PyPI;
5. as a last resort, a one-time, checksum-verified download of the
   [uv](https://github.com/astral-sh/uv) binary into the extension's
   private storage, which then provisions Python and the package itself.

The first run of rungs 4–5 downloads uv, a managed CPython and the
wheel (tens of MB, network required) behind a progress notification;
afterwards everything is cached and startup is fast. On proxied or
air-gapped machines, install the backend yourself and use rung 1
(`c4studio.serverCommand`) or 2. The
`c4studio.backendSpec` setting overrides which package version the
uv rungs install.

## Install

Build and install the extension locally (Node 18+):

```bash
cd editors/vscode
npm install
npm run package                     # -> c4studio-vscode-<version>.vsix
code --install-extension c4studio-vscode-*.vsix
```

Then reload VS Code. (The extension is not on the Marketplace; local
`.vsix` is the supported distribution for now.)

## Development

1. `npm install && npm run compile` in `editors/vscode/`.
2. Open `editors/vscode/` in VS Code and press `F5` (Run Extension).
3. In the Extension Development Host, open
   `samples/hedge_fund/workspace.dsl` and click the preview icon in the
   editor title bar.
