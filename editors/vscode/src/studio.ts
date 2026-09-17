import { spawn, type ChildProcess } from "node:child_process";
import * as http from "node:http";
import * as net from "node:net";
import * as path from "node:path";
import * as vscode from "vscode";

import { resolveC4Command } from "./resolve";

/**
 * Studio: the full authoring app, in a browser.
 *
 * The other half of the split introduced when the preview stopped
 * embedding the SPA. The preview is a picture of one view and needs no
 * server; Studio is the tool — file tree, editor, drill-down, arranging —
 * and needs the whole thing. Keeping them apart is what lets the preview
 * be small, and it puts Studio at a width it was designed for instead of
 * in a 400px panel.
 *
 * Everything here — port allocation, the readiness poll, the capability
 * probe, the `--viewer` fallback — used to run on every preview. It now
 * runs only when someone asks for Studio.
 */

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

/** Webview shell: a full-bleed iframe onto the local c4studio server. */

/** Spawns `c4 webapp` and opens it in the browser. */
export class StudioManager implements vscode.Disposable {
  private server: ChildProcess | undefined;
  private currentFile: string | undefined;
  private url: string | undefined;
  /** Set when the executable itself could not be run (ENOENT and friends),
      as opposed to a server that started and then refused an option. The
      two need different advice. */
  private execFailed = false;
  private readonly output: vscode.OutputChannel;
  private readonly storageDir: string;

  constructor(storageDir: string, output: vscode.OutputChannel) {
    this.storageDir = storageDir;
    this.output = output;
  }

  async open(document: vscode.TextDocument): Promise<void> {
    const file = document.uri.fsPath;
    if (this.server && this.currentFile === file && this.url) {
      // Already serving this file — just show it again rather than
      // restarting and losing whatever the user had arranged.
      await vscode.env.openExternal(vscode.Uri.parse(this.url));
      return;
    }

    this.stop();
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

    // Viewer mode, because VS Code has this file open in its own editor: a
    // second editor writing to the same path behind its back is the one
    // thing this must not do.
    //
    // It cannot simply be passed. `resolveC4Command` finds whatever
    // c4studio is on the user's machine, which may predate the flag — and
    // an unknown click option exits non-zero, which would surface as "the
    // server did not become ready". So: try it, and fall back if the
    // process dies immediately.
    let child = await this.spawn(command[0], [...baseArgs, "--viewer"], cwd, port);
    if (!child) {
      this.output.appendLine(
        "[studio] --viewer did not start; this c4studio may predate " +
          "Viewer mode. Retrying without it.",
      );
      child = await this.spawn(command[0], baseArgs, cwd, port);
    }
    if (!child) {
      this.stop();
      // Two different failures, two different pieces of advice: a missing
      // executable is something to install, a server that started and did
      // not answer is something to read the log about.
      const message = this.execFailed
        ? `c4studio: could not start "${command.join(" ")}". ` +
          "Install c4studio (e.g. via uv) or set c4studio.serverCommand."
        : "c4studio: the Studio server did not become ready.";
      void vscode.window.showErrorMessage(message, "Open Logs").then((choice) => {
        if (choice) this.output.show();
      });
      return;
    }

    const allowed = await capabilities(port);
    if (allowed === null) {
      this.output.appendLine(
        "[studio] no /api/capabilities: an older c4studio, which has no " +
          "in-browser editor. Read-only by construction.",
      );
    } else {
      this.output.appendLine(
        `[studio] mode=${allowed.mode} readOnly=${allowed.readOnly} ` +
          `version=${allowed.version}`,
      );
      if (!allowed.readOnly) {
        void vscode.window.showWarningMessage(
          "c4studio: Studio opened writable. Edits made there write to the " +
            "same file VS Code has open.",
        );
      }
    }

    this.url = `http://127.0.0.1:${port}/`;
    await vscode.env.openExternal(vscode.Uri.parse(this.url));
    this.output.appendLine(`[studio] serving ${file} at ${this.url}`);
  }

  /**
   * Spawn the backend and wait for it to answer.
   *
   * Returns undefined if it died or never became ready — which is what
   * makes the `--viewer` attempt safe to make blindly, since
   * `waitForServer` notices an exit rather than waiting out the timeout.
   */
  private async spawn(
    executable: string,
    args: string[],
    cwd: string,
    port: number,
  ): Promise<ChildProcess | undefined> {
    this.output.appendLine(`[studio] ${executable} ${args.join(" ")} (cwd: ${cwd})`);
    this.execFailed = false;
    const child = spawn(executable, args, { cwd });
    this.server = child;
    child.stdout?.on("data", (chunk: Buffer) => this.output.append(chunk.toString()));
    child.stderr?.on("data", (chunk: Buffer) => this.output.append(chunk.toString()));
    child.on("error", (error) => {
      this.execFailed = true;
      this.output.appendLine(`[studio] spawn failed: ${error.message}`);
    });
    child.on("exit", (code) => {
      this.output.appendLine(`[studio] server exited with code ${code ?? 0}`);
      if (this.server === child) this.server = undefined;
    });

    if (await waitForServer(port, child)) return child;
    if (child.exitCode === null) child.kill();
    if (this.server === child) this.server = undefined;
    return undefined;
  }

  private stop(): void {
    if (this.server) {
      this.server.kill();
      this.server = undefined;
    }
    this.currentFile = undefined;
    this.url = undefined;
  }

  dispose(): void {
    this.stop();
  }
}
