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

/** Webview shell: a full-bleed iframe onto the local c4studio server. */
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
  <iframe src="${origin}/" allow="clipboard-read; clipboard-write"></iframe>
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
    const args = [
      ...command.slice(1),
      "webapp",
      file,
      "--port",
      String(port),
      "--host",
      "127.0.0.1",
      "--no-browser",
    ];
    this.output.appendLine(`[preview] ${command[0]} ${args.join(" ")} (cwd: ${cwd})`);

    const child = spawn(command[0], args, { cwd });
    this.server = child;
    child.stdout?.on("data", (chunk: Buffer) =>
      this.output.append(chunk.toString()),
    );
    child.stderr?.on("data", (chunk: Buffer) =>
      this.output.append(chunk.toString()),
    );
    child.on("error", (error) => {
      this.output.appendLine(`[preview] spawn failed: ${error.message}`);
      void vscode.window
        .showErrorMessage(
          `c4studio: could not start "${command.join(" ")}". ` +
            "Install c4studio (e.g. via uv) or set c4studio.serverCommand.",
          "Open Logs",
        )
        .then((choice) => {
          if (choice) this.output.show();
        });
    });
    child.on("exit", (code) => {
      this.output.appendLine(`[preview] server exited with code ${code ?? 0}`);
      if (this.server === child) this.server = undefined;
    });

    const healthy = await waitForServer(port, child);
    if (!healthy) {
      this.stopServer();
      void vscode.window
        .showErrorMessage(
          "c4studio: the preview server did not become ready.",
          "Open Logs",
        )
        .then((choice) => {
          if (choice) this.output.show();
        });
      return;
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
