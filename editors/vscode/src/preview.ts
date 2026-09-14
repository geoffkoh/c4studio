import { spawn, type ChildProcess } from "node:child_process";
import * as http from "node:http";
import * as net from "node:net";
import * as path from "node:path";
import * as vscode from "vscode";

import { resolveServerCommand } from "./resolve";

const HEALTH_TIMEOUT_MS = 15_000;
const HEALTH_INTERVAL_MS = 300;

/** Ask the OS for a free localhost port. */
function freePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      if (address && typeof address === "object") {
        const port = address.port;
        server.close(() => resolve(port));
      } else {
        server.close(() => reject(new Error("Could not allocate a port")));
      }
    });
  });
}

/** What the server says it allows, or null when it is too old to say.

    A backend without this endpoint predates Studio/Viewer modes — and
    therefore predates the in-browser editor too, so "old" and "read-only"
    are the same thing for our purposes. */
interface Capabilities {
  readOnly: boolean;
  mode: string;
  version: string;
}

function capabilities(port: number): Promise<Capabilities | null> {
  return new Promise((resolve) => {
    const request = http.get(
      { host: "127.0.0.1", port, path: "/api/capabilities", timeout: 1000 },
      (response) => {
        if (response.statusCode !== 200) {
          response.resume();
          resolve(null);
          return;
        }
        let body = "";
        response.setEncoding("utf8");
        response.on("data", (chunk: string) => (body += chunk));
        response.on("end", () => {
          try {
            resolve(JSON.parse(body) as Capabilities);
          } catch {
            resolve(null);
          }
        });
      },
    );
    request.on("error", () => resolve(null));
    request.on("timeout", () => {
      request.destroy();
      resolve(null);
    });
  });
}

/** One GET /api/status probe; resolves true on any HTTP response. */
function probe(port: number): Promise<boolean> {
  return new Promise((resolve) => {
    const request = http.get(
      { host: "127.0.0.1", port, path: "/api/status", timeout: 1000 },
      (response) => {
        response.resume();
        resolve(response.statusCode !== undefined);
      },
    );
    request.on("error", () => resolve(false));
    request.on("timeout", () => {
      request.destroy();
      resolve(false);
    });
  });
}

/** Poll until the spawned server answers, the timeout passes, or it dies. */
async function waitForServer(
  port: number,
  child: ChildProcess,
): Promise<boolean> {
  const deadline = Date.now() + HEALTH_TIMEOUT_MS;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) return false;
    if (await probe(port)) return true;
    await new Promise((resolve) => setTimeout(resolve, HEALTH_INTERVAL_MS));
  }
  return false;
}

/** Webview shell: a full-bleed iframe onto the local c4studio server.

    `?embed=1` asks the SPA for the diagram and a view picker and nothing
    else — no topbar, no sidebar, no diagram toolbar, no minimap. It is a
    query param rather than a server flag because this iframe is
    cross-origin: the extension cannot reach inside it, so the URL is the
    only channel it has. An older SPA ignores the parameter and renders as
    it always did, which is why no version dance is needed here the way it
    is for `--viewer`. */
function iframeHtml(port: number): string {
  const origin = `http://127.0.0.1:${port}`;
  return `<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8" />
  <meta http-equiv="Content-Security-Policy"
        content="default-src 'none'; frame-src ${origin}; style-src 'unsafe-inline';" />
  <style>
    html, body { margin: 0; padding: 0; width: 100%; height: 100%; overflow: hidden; }
    iframe { border: none; width: 100%; height: 100%; }
  </style>
</head>
<body>
  <iframe src="${origin}/?embed=1" allow="clipboard-read; clipboard-write"></iframe>
</body>
</html>`;
}

/**
 * Owns the preview webview and the c4studio server behind it.
 *
 * One server + one panel at a time: previewing the same file reveals the
 * existing panel; previewing a different file restarts the server against
 * it. The server is spawned from the workspace folder (so `uv run` finds
 * the project) and killed when the panel closes or the extension
 * deactivates. Live reload needs no extra wiring — the SPA polls the
 * server, which watches the source file's mtime.
 */
export class PreviewManager implements vscode.Disposable {
  private panel: vscode.WebviewPanel | undefined;
  private server: ChildProcess | undefined;
  private currentFile: string | undefined;
  /** Set when the executable itself could not be run (ENOENT and friends),
      as opposed to a server that started and then refused an option. The
      two need different advice. */
  private execFailed = false;
  private readonly output: vscode.OutputChannel;
  private readonly storageDir: string;

  constructor(storageDir: string) {
    this.output = vscode.window.createOutputChannel("c4studio");
    this.storageDir = storageDir;
  }

  async open(document: vscode.TextDocument): Promise<void> {
    const file = document.uri.fsPath;
    if (this.panel && this.server && this.currentFile === file) {
      this.panel.reveal(undefined, true);
      return;
    }

    this.stopServer();
    this.currentFile = file;

    let port: number;
    try {
      port = await freePort();
    } catch (error) {
      void vscode.window.showErrorMessage(
        `c4studio: could not allocate a port: ${String(error)}`,
      );
      return;
    }

    const cwd =
      vscode.workspace.getWorkspaceFolder(document.uri)?.uri.fsPath ??
      path.dirname(file);
    const command = await resolveServerCommand(cwd, this.storageDir, this.output);
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
    const baseArgs = [
      ...command.slice(1),
      "webapp",
      file,
      "--port",
      String(port),
      "--host",
      "127.0.0.1",
      "--no-browser",
    ];

    // Viewer mode, because VS Code already has this file open in its own
    // editor: a second editor in the webview writing to the same path
    // behind its back is the one thing this preview must not do.
    //
    // It cannot simply be passed, though. `resolveServerCommand` finds
    // whatever c4studio is on the user's machine, which may predate the
    // flag — and an unknown click option exits non-zero, which would
    // surface as "the preview server did not become ready". So: try it,
    // and fall back to a plain spawn if the process dies immediately.
    let child = await this.spawnServer(
      command[0],
      [...baseArgs, "--viewer"],
      cwd,
      port,
    );
    if (!child) {
      this.output.appendLine(
        "[preview] --viewer did not start; this c4studio may predate " +
          "Viewer mode. Retrying without it.",
      );
      child = await this.spawnServer(command[0], baseArgs, cwd, port);
    }
    if (!child) {
      this.stopServer();
      // Two different failures, two different pieces of advice: a missing
      // executable is something to install, a server that started and did
      // not answer is something to read the log about.
      const message = this.execFailed
        ? `c4studio: could not start "${command.join(" ")}". ` +
          "Install c4studio (e.g. via uv) or set c4studio.serverCommand."
        : "c4studio: the preview server did not become ready.";
      void vscode.window.showErrorMessage(message, "Open Logs").then((choice) => {
        if (choice) this.output.show();
      });
      return;
    }

    // What actually started. A server too old to answer predates Studio
    // and Viewer modes — and therefore predates the in-browser editor, so
    // there is nothing there to edit with and nothing to hide.
    const allowed = await capabilities(port);
    if (allowed === null) {
      this.output.appendLine(
        "[preview] no /api/capabilities: an older c4studio, which has no " +
          "in-browser editor. Read-only by construction.",
      );
    } else {
      this.output.appendLine(
        `[preview] mode=${allowed.mode} readOnly=${allowed.readOnly} ` +
          `version=${allowed.version}`,
      );
      if (!allowed.readOnly) {
        // Should not happen: a server new enough to report capabilities
        // accepted --viewer. Say so rather than leave two editors on one
        // file unremarked.
        void vscode.window.showWarningMessage(
          "c4studio: the preview is editable. Edits made in the preview " +
            "write to the same file VS Code has open.",
        );
      }
    }

    if (!this.panel) {
      this.panel = vscode.window.createWebviewPanel(
        "c4studioPreview",
        "c4studio",
        { viewColumn: vscode.ViewColumn.Beside, preserveFocus: true },
        { enableScripts: true, retainContextWhenHidden: true },
      );
      this.panel.onDidDispose(() => {
        this.panel = undefined;
        this.stopServer();
      });
    }
    this.panel.title = `C4: ${path.basename(file)}`;
    this.panel.webview.html = iframeHtml(port);
    this.panel.reveal(undefined, true);
  }

  /**
   * Spawn the backend and wait for it to answer.
   *
   * Returns the process, or `undefined` if it died or never became ready
   * — which is what makes the `--viewer` attempt safe to make blindly. An
   * older c4studio rejects the unknown option and exits non-zero, and
   * `waitForServer` notices the exit rather than waiting out the full
   * timeout.
   */
  private async spawnServer(
    executable: string,
    args: string[],
    cwd: string,
    port: number,
  ): Promise<ChildProcess | undefined> {
    this.output.appendLine(`[preview] ${executable} ${args.join(" ")} (cwd: ${cwd})`);
    this.execFailed = false;
    const child = spawn(executable, args, { cwd });
    this.server = child;
    child.stdout?.on("data", (chunk: Buffer) =>
      this.output.append(chunk.toString()),
    );
    child.stderr?.on("data", (chunk: Buffer) =>
      this.output.append(chunk.toString()),
    );
    child.on("error", (error) => {
      this.execFailed = true;
      this.output.appendLine(`[preview] spawn failed: ${error.message}`);
    });
    child.on("exit", (code) => {
      this.output.appendLine(`[preview] server exited with code ${code ?? 0}`);
      if (this.server === child) this.server = undefined;
    });

    if (await waitForServer(port, child)) return child;
    if (child.exitCode === null) child.kill();
    if (this.server === child) this.server = undefined;
    return undefined;
  }

  private stopServer(): void {
    if (this.server) {
      this.server.kill();
      this.server = undefined;
    }
    this.currentFile = undefined;
  }

  dispose(): void {
    this.stopServer();
    this.panel?.dispose();
    this.output.dispose();
  }
}
