import { execFile } from "node:child_process";
import * as vscode from "vscode";

const LIST_TIMEOUT_MS = 30_000;
const MAX_JSON_BYTES = 4 * 1024 * 1024;

/** One entry of `c4 list-views --json`, which is `GET /api/views`'s shape. */
export interface ViewEntry {
  key: string;
  type: string;
  title: string;
  element_id: string;
  supported: boolean;
  default: boolean;
}

/**
 * List the views in `file`, default first.
 *
 * Reads `c4 list-views --json` rather than parsing the table, and the CLI
 * shares its implementation with the web app's `/api/views`
 * (`webapp/graph.py: views_index`) so the picker cannot disagree with
 * Studio about which view is the default.
 *
 * Returns an empty list on any failure. The caller has a better error to
 * show than this one — a broken file fails at render with the parse error
 * on stderr, which is the message worth reading.
 */
export function listViews(
  command: string[],
  file: string,
  cwd: string,
  output: vscode.OutputChannel,
): Promise<ViewEntry[]> {
  return new Promise((resolve) => {
    const args = [...command.slice(1), "list-views", file, "--json"];
    execFile(
      command[0],
      args,
      { cwd, timeout: LIST_TIMEOUT_MS, maxBuffer: MAX_JSON_BYTES },
      (error, stdout, stderr) => {
        if (error) {
          output.appendLine(`[views] ${stderr.trim() || error.message}`);
          resolve([]);
          return;
        }
        try {
          const parsed: unknown = JSON.parse(stdout);
          if (!Array.isArray(parsed)) {
            resolve([]);
            return;
          }
          resolve(parsed as ViewEntry[]);
        } catch (parseError) {
          // An older c4studio has no --json and prints the table, which is
          // not JSON. Same outcome as any other failure: no picker.
          output.appendLine(`[views] unparseable: ${String(parseError)}`);
          resolve([]);
        }
      },
    );
  });
}

/**
 * The view to open when the user has not chosen one.
 *
 * `views_index` already sorts the DSL's `default` view first, so this is
 * mostly "the first renderable one" — but it skips `image` and `custom`
 * views, which are listed with `supported: false` precisely so a caller
 * does not open a panel that can only be empty.
 */
export function defaultView(views: ViewEntry[]): ViewEntry | undefined {
  return views.find((view) => view.supported);
}
