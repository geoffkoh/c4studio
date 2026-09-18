import * as path from "node:path";
import * as vscode from "vscode";

import { renderView } from "./render";
import { resolveC4Command } from "./resolve";
import {
  defaultView,
  listPerspectives,
  listViews,
  type ViewEntry,
} from "./views";

/**
 * The diagram preview: one view, as an SVG, in a webview.
 *
 * It used to embed the whole Studio in an iframe, which put a topbar, a
 * sidebar rail, page tabs and a 725px diagram toolbar into a panel often
 * only 400px wide. This renders a picture instead.
 *
 * That change removes the constraint the old design worked around: the
 * iframe was cross-origin, so the extension could not touch anything
 * inside it. Owning the DOM is what makes the view picker, the error
 * display and re-render-on-save ordinary extension code rather than
 * impossible ones.
 *
 * The SVG comes from `c4 render`, which runs the same layout the SPA does,
 * so the picture matches what Studio would draw. What it cannot do is pan,
 * zoom, drill down or arrange — that is what `c4studio.openInStudio` is
 * for.
 */
export class PreviewManager implements vscode.Disposable {
  private panel: vscode.WebviewPanel | undefined;
  private currentFile: string | undefined;
  private currentView: string | undefined;
  private views: ViewEntry[] = [];
  private readonly output: vscode.OutputChannel;
  private readonly storageDir: string;
  private readonly chosen: Map<string, string> = new Map();
  /** The perspective shown per file, when one was chosen (PP-183). */
  private readonly perspective: Map<string, string> = new Map();

  constructor(storageDir: string, output: vscode.OutputChannel) {
    this.storageDir = storageDir;
    this.output = output;
  }

  /** Open (or re-render) the preview for `document`. */
  async open(document: vscode.TextDocument, viewKey?: string): Promise<void> {
    const file = document.uri.fsPath;
    const cwd =
      vscode.workspace.getWorkspaceFolder(document.uri)?.uri.fsPath ??
      path.dirname(file);

    const command = await resolveC4Command(cwd, this.storageDir, this.output);
    if (!command) {
      void vscode.window
        .showErrorMessage(
          "c4studio: no way to run the backend was found. " +
            "Install it (pipx install c4studio) or set " +
            "c4studio.serverCommand.",
          "Open Logs",
        )
        .then((choice) => {
          if (choice) this.output.show();
        });
      return;
    }

    // The view list is per file and only needs re-reading when the file
    // changes — a save can add or remove views, so refresh it then too.
    if (this.currentFile !== file || this.views.length === 0) {
      this.views = await listViews(command, file, cwd, this.output);
    }

    const key =
      viewKey ??
      this.chosen.get(file) ??
      defaultView(this.views)?.key ??
      this.views[0]?.key;
    if (!key) {
      this.show(file, undefined, errorHtml("This workspace defines no views."));
      return;
    }
    this.chosen.set(file, key);
    this.currentFile = file;
    this.currentView = key;

    const outcome = await renderView(
      command,
      file,
      key,
      cwd,
      this.output,
      this.perspective.get(file),
    );
    const label = this.views.find((view) => view.key === key)?.title || key;
    this.show(
      file,
      key,
      outcome.ok ? svgHtml(outcome.svg, label) : errorHtml(outcome.message),
    );
  }

  /** Re-render the current file, if the saved document is that file. */
  async refresh(document: vscode.TextDocument): Promise<void> {
    if (!this.panel || document.uri.fsPath !== this.currentFile) return;
    // Views may have been added or removed by the edit.
    this.views = [];
    await this.open(document, this.currentView);
  }

  /** Ask which view to show, then show it. */
  async pickView(document: vscode.TextDocument): Promise<void> {
    const file = document.uri.fsPath;
    const cwd =
      vscode.workspace.getWorkspaceFolder(document.uri)?.uri.fsPath ??
      path.dirname(file);
    const command = await resolveC4Command(cwd, this.storageDir, this.output);
    if (!command) return;

    const views = await listViews(command, file, cwd, this.output);
    const renderable = views.filter((view) => view.supported);
    if (renderable.length === 0) {
      void vscode.window.showInformationMessage(
        "c4studio: this workspace has no renderable views.",
      );
      return;
    }

    const picked = await vscode.window.showQuickPick(
      renderable.map((view) => ({
        label: view.key,
        // The title is what a person recognises; the key is what they
        // typed. Show both rather than making them match one to the other.
        description: view.title,
        detail: view.default ? `${view.type} · the workspace default` : view.type,
        key: view.key,
      })),
      { title: "c4studio: show view", placeHolder: "Which view?" },
    );
    if (!picked) return;
    await this.open(document, picked.key);
  }

  /** Ask which perspective to show, then show it. */
  async pickPerspective(document: vscode.TextDocument): Promise<void> {
    const file = document.uri.fsPath;
    const cwd =
      vscode.workspace.getWorkspaceFolder(document.uri)?.uri.fsPath ??
      path.dirname(file);
    const command = await resolveC4Command(cwd, this.storageDir, this.output);
    if (!command) return;

    const names = await listPerspectives(command, file, cwd, this.output);
    if (names.length === 0) {
      void vscode.window.showInformationMessage(
        "c4studio: this workspace defines no perspectives.",
      );
      return;
    }

    const current = this.perspective.get(file);
    const picked = await vscode.window.showQuickPick(
      [
        // Clearing it has to be as reachable as setting it, which is why
        // the Studio's picker carries the same entry.
        {
          label: "(none)",
          description: "Show the diagram unfiltered",
          name: "",
        },
        ...names.map((name) => ({
          label: name,
          description: name === current ? "shown" : undefined,
          name,
        })),
      ],
      { title: "c4studio: show perspective", placeHolder: "Which perspective?" },
    );
    if (!picked) return;
    if (picked.name) {
      this.perspective.set(file, picked.name);
    } else {
      this.perspective.delete(file);
    }
    await this.open(document, this.chosen.get(file));
  }

  /** Put `body` in the panel, creating it if this is the first time. */
  private show(file: string, viewKey: string | undefined, body: string): void {
    if (!this.panel) {
      this.panel = vscode.window.createWebviewPanel(
        "c4studioPreview",
        "c4studio",
        { viewColumn: vscode.ViewColumn.Beside, preserveFocus: true },
        // No scripts: this is a static picture, and the CSP below says so.
        // retainContextWhenHidden costs nothing to drop now that the panel
        // holds markup rather than a live app.
        { enableScripts: false },
      );
      this.panel.onDidDispose(() => {
        this.panel = undefined;
        this.currentFile = undefined;
        this.currentView = undefined;
      });
    }
    this.panel.title = viewKey
      ? `${viewKey} — ${path.basename(file)}`
      : `C4: ${path.basename(file)}`;
    this.panel.webview.html = body;
    this.panel.reveal(undefined, true);
  }

  dispose(): void {
    this.panel?.dispose();
  }
}

/**
 * The shared head of every preview document.
 *
 * `img-src data:` is load-bearing and easy to miss. `default-src 'none'`
 * covers `img-src`, and the cloud-provider icons in deployment views are
 * inlined by `render.py` as `data:` URIs — so without this they vanish
 * silently, with nothing in the UI to say why. Two of the thirteen
 * hedge_fund views contain them; the other eleven look perfect.
 *
 * No `script-src`: the page has no script, and keeping it that way is why
 * `enableScripts` is false.
 */
function head(title: string): string {
  return `<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8" />
  <meta http-equiv="Content-Security-Policy"
        content="default-src 'none'; img-src data:; style-src 'unsafe-inline';" />
  <title>${escapeHtml(title)}</title>
  <style>
    html, body { margin: 0; padding: 0; height: 100%; }
    body {
      display: flex;
      background: var(--vscode-editor-background);
      color: var(--vscode-editor-foreground);
      font-family: var(--vscode-font-family);
      font-size: var(--vscode-font-size);
    }
  </style>
</head>`;
}

/**
 * The diagram, scaled to fit the panel.
 *
 * `c4 render` emits an SVG with its own width/height. Overriding them in
 * CSS and leaning on the viewBox lets the picture fit whatever width the
 * panel happens to be — which is the entire reason this surface exists.
 */
function svgHtml(svg: string, label: string): string {
  return `${head(label)}
<body>
  <main>${svg}</main>
  <style>
    main { margin: auto; padding: 12px; width: 100%; box-sizing: border-box; }
    svg { width: 100%; height: auto; max-height: calc(100vh - 24px); display: block; }
  </style>
</body>
</html>`;
}

/**
 * A parse error, in place of the diagram.
 *
 * Showing this rather than the last good picture is the point. The old
 * preview did the opposite: the server keeps serving the previous
 * workspace on a failed reload, and the SPA renders every error inside a
 * sidebar that auto-collapses below 900px — so a broken DSL looked exactly
 * like a working one.
 */
function errorHtml(message: string): string {
  return `${head("c4studio")}
<body>
  <main>
    <h2>This view could not be rendered</h2>
    <pre>${escapeHtml(message)}</pre>
  </main>
  <style>
    main { margin: auto; padding: 24px; max-width: 60em; }
    h2 { font-size: 1.1em; font-weight: 600; margin: 0 0 12px; }
    pre {
      white-space: pre-wrap;
      word-break: break-word;
      font-family: var(--vscode-editor-font-family);
      background: var(--vscode-textCodeBlock-background);
      padding: 12px;
      border-radius: 4px;
      margin: 0;
    }
  </style>
</body>
</html>`;
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
