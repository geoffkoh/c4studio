# VS Code

The c4studio extension brings Structurizr DSL into VS Code: highlighting, problems as you type, and a diagram preview beside your editor. It uses the same parser and renderer as the CLI, so the preview draws exactly what `c4 render` draws.

## Install

The extension is not on the Marketplace yet. Build the `.vsix` from the repository and install it:

```bash
git clone https://github.com/geoffkoh/c4studio
cd c4studio/editors/vscode
npm install
npm run package                          # writes c4studio-vscode-<version>.vsix
code --install-extension c4studio-vscode-*.vsix
```

Then reload VS Code. Building needs Node 18 or newer. Using the extension does not need Node, as explained below.

## Features

- **Syntax highlighting** for `.dsl` and `.structurizr` files: keywords, style properties, directives and their paths, strings, comments, hex colours, `->` relationships and `alias =` definitions.
- **Problems as you type.** Parse errors and skipped constructs show as squiggles and in the Problems panel, from `c4 check`. The unsaved buffer is checked as written. A problem inside an `!include` fragment is reported against the fragment.
- **Diagram preview.** *C4Studio: Open Diagram Preview*, or the button in the editor title bar, draws one view beside your editor as an SVG. Saving the file, or any fragment it includes, redraws it. The preview follows the layout you arranged in the Studio.
- **Switch view or perspective.** *Show View…* picks the view, with the workspace default marked. *Show Perspective…* shows one perspective over it. Both choices are remembered per file.
- **The full Studio when you want it.** *Open in Studio (browser)* starts `c4 webapp` on a free local port and opens it in your browser, for dragging layouts, expanding elements and the rest.

## Commands

| Command | What it does |
| --- | --- |
| C4Studio: Open Diagram Preview | Draws the current file's default view beside the editor. |
| C4Studio: Show View… | Chooses which view the preview draws. |
| C4Studio: Show Perspective… | Shows one perspective in the preview, or none. |
| C4Studio: Open in Studio (browser) | Starts the Studio for this file and opens it in a browser. The only command that starts a server, which stops when VS Code closes. |
| C4Studio: Check for Problems | Runs the checker on the current file now. |

## Settings

| Setting | Default | What it does |
| --- | --- | --- |
| `c4studio.diagnostics.enabled` | `true` | Report parse problems as editor diagnostics. |
| `c4studio.serverCommand` | `[]` | The command that runs c4studio, such as `["c4"]` or a path into a virtual environment. Empty means automatic. |
| `c4studio.backendSpec` | the matching release | The package the automatic `uv tool run` step installs. Set it to a pre-release or a local wheel to test one. |

## How it finds c4studio

No setup is required. The extension tries these in order, and logs each attempt to the *c4studio* output channel:

1. the `c4studio.serverCommand` setting, when set;
2. `c4` on your `PATH`, for example from `pipx install c4studio`;
3. your workspace's own environment via `uv run`, when the folder has a `pyproject.toml` and uv is installed;
4. `uv tool run`, installing `c4studio` from PyPI;
5. as a last resort, a one-time, checksum-verified download of uv into the extension's private storage, which then provisions Python and the package.

Steps 4 and 5 download tens of megabytes the first time, and are cached after that. On a proxied or air-gapped machine, install c4studio yourself and use step 1 or 2.

Rendering needs Node. If neither `C4STUDIO_NODE` nor `node` on `PATH` is found, the extension runs the renderer with VS Code's own runtime, so the preview works on a machine with no Node installed.

## Privacy and security

The preview is an SVG in a webview whose content security policy is `default-src 'none'` with `img-src data:`. Theme icons are embedded in the SVG, so a diagram makes no network requests. Nothing listens on a port unless you choose *Open in Studio*.
