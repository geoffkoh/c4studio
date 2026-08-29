import { execFile } from "node:child_process";
import * as crypto from "node:crypto";
import * as fs from "node:fs";
import * as path from "node:path";
import * as vscode from "vscode";

/** Backend installed by the uv rungs; overridable via c4studio.backendSpec. */
export const DEFAULT_BACKEND_SPEC = "c4studio==0.2.0";

const PROBE_TIMEOUT_MS = 5_000;
/** First `uv tool run` downloads CPython + the wheel; allow minutes, not seconds. */
const WARMUP_TIMEOUT_MS = 300_000;

/** process.platform/arch → uv release target triple. */
function uvTriple(): string | null {
  const key = `${process.platform}-${process.arch}`;
  const triples: Record<string, string> = {
    "darwin-arm64": "aarch64-apple-darwin",
    "darwin-x64": "x86_64-apple-darwin",
    "linux-x64": "x86_64-unknown-linux-gnu",
    "linux-arm64": "aarch64-unknown-linux-gnu",
    "win32-x64": "x86_64-pc-windows-msvc",
    "win32-arm64": "aarch64-pc-windows-msvc",
  };
  return triples[key] ?? null;
}

/** Run a command, resolving true when it exits 0 within the timeout. */
function runs(command: string[], timeoutMs: number, cwd?: string): Promise<boolean> {
  return new Promise((resolve) => {
    execFile(
      command[0],
      command.slice(1),
      { timeout: timeoutMs, cwd },
      (error) => resolve(error === null),
    );
  });
}

function workspaceLooksLikeUvProject(folder: string | undefined): boolean {
  if (!folder) return false;
  return (
    fs.existsSync(path.join(folder, "uv.lock")) ||
    fs.existsSync(path.join(folder, "pyproject.toml"))
  );
}

async function download(url: string, dest: string): Promise<void> {
  const response = await fetch(url); // follows GitHub's release redirects
  if (!response.ok) {
    throw new Error(`GET ${url} -> ${response.status}`);
  }
  const data = Buffer.from(await response.arrayBuffer());
  await fs.promises.writeFile(dest, data);
}

async function sha256File(file: string): Promise<string> {
  const data = await fs.promises.readFile(file);
  return crypto.createHash("sha256").update(data).digest("hex");
}

/**
 * Download the uv binary for this platform into `storageDir/uv/`,
 * verifying the archive against its published .sha256, and return the
 * binary's path. No-op when already bootstrapped.
 */
export async function bootstrapUv(
  storageDir: string,
  output: vscode.OutputChannel,
): Promise<string> {
  const triple = uvTriple();
  if (!triple) {
    throw new Error(`unsupported platform: ${process.platform}/${process.arch}`);
  }
  const isWindows = process.platform === "win32";
  const dir = path.join(storageDir, "uv");
  const binary = path.join(dir, isWindows ? "uv.exe" : "uv");
  if (fs.existsSync(binary)) return binary;

  await fs.promises.mkdir(dir, { recursive: true });
  const archiveName = `uv-${triple}.${isWindows ? "zip" : "tar.gz"}`;
  const base = "https://github.com/astral-sh/uv/releases/latest/download";
  const archivePath = path.join(dir, archiveName);

  output.appendLine(`[bootstrap] downloading ${base}/${archiveName}`);
  await download(`${base}/${archiveName}`, archivePath);

  const checksumText = await (await fetch(`${base}/${archiveName}.sha256`)).text();
  const expected = checksumText.trim().split(/\s+/)[0].toLowerCase();
  const actual = await sha256File(archivePath);
  if (actual !== expected) {
    await fs.promises.rm(archivePath, { force: true });
    throw new Error(`uv archive checksum mismatch (${actual} != ${expected})`);
  }
  output.appendLine(`[bootstrap] checksum ok (${expected.slice(0, 12)}…)`);

  const extracted = isWindows
    ? await runs(
        [
          "powershell.exe",
          "-NoProfile",
          "-Command",
          `Expand-Archive -Force -Path '${archivePath}' -DestinationPath '${dir}'`,
        ],
        60_000,
      )
    : await runs(
        ["tar", "-xzf", archivePath, "-C", dir, "--strip-components=1"],
        60_000,
      );
  await fs.promises.rm(archivePath, { force: true });
  if (!extracted || !fs.existsSync(binary)) {
    throw new Error("could not extract the uv archive");
  }
  if (!isWindows) await fs.promises.chmod(binary, 0o755);
  output.appendLine(`[bootstrap] uv ready at ${binary}`);
  return binary;
}

function backendSpec(): string {
  const configured = vscode.workspace
    .getConfiguration("c4studio")
    .get<string>("backendSpec");
  return configured && configured.trim() !== "" ? configured : DEFAULT_BACKEND_SPEC;
}

function toolRunCommand(uvPath: string): string[] {
  return [uvPath, "tool", "run", "--from", backendSpec(), "c4"];
}

/**
 * Find a command that runs the c4 CLI, first match wins:
 *
 * 1. the `c4studio.serverCommand` setting, verbatim, when non-empty;
 * 2. `c4` already on PATH;
 * 3. `uv run c4` when the workspace looks like a uv/python
 *    project (the development-repo case);
 * 4. `uv tool run --from <spec> c4` when uv is on PATH;
 * 5. as (4) after downloading a private, checksum-verified uv binary
 *    into the extension's global storage.
 *
 * Rungs 4–5 pre-warm the tool environment (`… --version`) under a
 * progress notification: the first run downloads a managed CPython plus
 * the wheel from PyPI and must not eat the preview's health budget.
 * Returns null when nothing could be resolved.
 */
export async function resolveServerCommand(
  workspaceFolder: string | undefined,
  storageDir: string,
  output: vscode.OutputChannel,
): Promise<string[] | null> {
  const configured = vscode.workspace
    .getConfiguration("c4studio")
    .get<string[]>("serverCommand");
  if (configured && configured.length > 0) {
    output.appendLine(`[resolve] using serverCommand setting: ${configured.join(" ")}`);
    return configured;
  }

  if (await runs(["c4", "--version"], PROBE_TIMEOUT_MS)) {
    output.appendLine("[resolve] found c4 on PATH");
    return ["c4"];
  }

  const uvOnPath = await runs(["uv", "--version"], PROBE_TIMEOUT_MS);
  if (uvOnPath && workspaceLooksLikeUvProject(workspaceFolder)) {
    if (
      await runs(
        ["uv", "run", "c4", "--version"],
        WARMUP_TIMEOUT_MS,
        workspaceFolder,
      )
    ) {
      output.appendLine("[resolve] using the workspace project via uv run");
      return ["uv", "run", "c4"];
    }
  }

  const warm = (command: string[]): Thenable<boolean> =>
    vscode.window.withProgress(
      {
        location: vscode.ProgressLocation.Notification,
        title: "Setting up the c4studio backend (one-time download)…",
      },
      () => runs([...command, "--version"], WARMUP_TIMEOUT_MS),
    );

  if (uvOnPath) {
    const command = toolRunCommand("uv");
    output.appendLine(`[resolve] trying ${command.join(" ")}`);
    if (await warm(command)) return command;
    output.appendLine("[resolve] uv tool run failed (see above)");
    return null;
  }

  output.appendLine("[resolve] no uv on PATH; bootstrapping a private copy");
  try {
    const uvPath = await vscode.window.withProgress(
      {
        location: vscode.ProgressLocation.Notification,
        title: "Downloading the uv runtime for c4studio (one-time)…",
      },
      () => bootstrapUv(storageDir, output),
    );
    const command = toolRunCommand(uvPath);
    if (await warm(command)) return command;
    return null;
  } catch (error) {
    output.appendLine(`[resolve] bootstrap failed: ${String(error)}`);
    return null;
  }
}
