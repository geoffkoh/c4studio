import { execFile } from "node:child_process";
import * as vscode from "vscode";

import { runs } from "./resolve";

/** `c4 render` shells out to Node and can pull icons over the network. */
const RENDER_TIMEOUT_MS = 60_000;
const NODE_PROBE_TIMEOUT_MS = 5_000;
/** Enough for the largest sample (ProductionDeployment, ~45 KB) many times over. */
const MAX_SVG_BYTES = 8 * 1024 * 1024;

export interface RenderedView {
  ok: true;
  svg: string;
}

export interface RenderFailed {
  ok: false;
  /** Shown in the panel. `c4 render` writes parse errors to stderr. */
  message: string;
}

export type RenderOutcome = RenderedView | RenderFailed;

let cachedNodeEnv: NodeJS.ProcessEnv | undefined;

/**
 * Environment for the render subprocess, so it can find a Node.
 *
 * `render.py` looks for `C4STUDIO_NODE` and then `node` on PATH, and this
 * is the only part of c4studio that needs Node at runtime. When the user
 * has none, the extension host itself is one: VS Code ships an Electron
 * binary that behaves as Node under `ELECTRON_RUN_AS_NODE`. Measured on
 * VS Code 1.135 — `process.execPath` with that variable reports Node
 * 24.18.1, comfortably above the Node 18 floor the README promises.
 *
 * Probed once and remembered: `node --version` costs a process spawn, and
 * this runs on every save.
 */
async function nodeEnv(output: vscode.OutputChannel): Promise<NodeJS.ProcessEnv> {
  if (cachedNodeEnv) return cachedNodeEnv;
  if (await runs(["node", "--version"], NODE_PROBE_TIMEOUT_MS)) {
    output.appendLine("[render] node found on PATH");
    cachedNodeEnv = {};
  } else {
    output.appendLine(
      `[render] no node on PATH; using the extension host (${process.execPath})`,
    );
    cachedNodeEnv = {
      C4STUDIO_NODE: process.execPath,
      ELECTRON_RUN_AS_NODE: "1",
    };
  }
  return cachedNodeEnv;
}

/**
 * Render one view of `file` to a standalone SVG string.
 *
 * This is the whole preview: no server, no port, no iframe. `c4 render`
 * runs the same `layoutGraph` the SPA does (`packages/diagram-core/src/
 * svg.ts`), so node positions match what Studio would show rather than
 * merely resembling it.
 *
 * A parse error is an outcome, not an exception — the caller paints it in
 * the panel. Leaving the previous diagram up while the source is broken is
 * the failure mode this replaces: the old preview did exactly that,
 * because the server keeps serving the last good workspace and every error
 * rendered inside a sidebar the panel is too narrow to show.
 */
export function renderView(
  command: string[],
  file: string,
  viewKey: string,
  cwd: string,
  output: vscode.OutputChannel,
  perspective?: string,
): Promise<RenderOutcome> {
  return nodeEnv(output).then(
    (env) =>
      new Promise<RenderOutcome>((resolve) => {
        const args = [...command.slice(1), "render", file, "--view", viewKey];
        // Shows the perspective the way the Studio's picker does: what
        // lacks it fades, what carries it is badged with its value.
        if (perspective) args.push("--perspective", perspective);
        output.appendLine(`[render] ${command[0]} ${args.join(" ")}`);
        execFile(
          command[0],
          args,
          {
            cwd,
            timeout: RENDER_TIMEOUT_MS,
            maxBuffer: MAX_SVG_BYTES,
            env: { ...process.env, ...env },
          },
          (error, stdout, stderr) => {
            if (error) {
              const detail = stderr.trim() || error.message;
              output.appendLine(`[render] failed: ${detail}`);
              resolve({ ok: false, message: detail });
              return;
            }
            if (!stdout.includes("<svg")) {
              // Exit 0 with no SVG means the view key matched nothing, or
              // matched a type no renderer draws (`image`, `custom`).
              resolve({
                ok: false,
                message:
                  `"${viewKey}" produced no diagram. It may be a view type ` +
                  `that cannot be rendered.`,
              });
              return;
            }
            resolve({ ok: true, svg: stdout });
          },
        );
      }),
  );
}
