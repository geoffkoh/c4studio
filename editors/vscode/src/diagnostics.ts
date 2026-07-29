import { execFile } from "node:child_process";
import * as path from "node:path";
import * as vscode from "vscode";

import { resolveServerCommand } from "./resolve";

/** One record emitted by `pystructurizr check --json`. */
interface CheckRecord {
  path: string | null;
  line: number | null;
  column: number | null;
  endColumn: number | null;
  severity: "error" | "warning";
  code: string;
  message: string;
}

const CHECK_TIMEOUT_MS = 20_000;
/** Pause after a keystroke before re-checking, so squiggles do not flicker. */
const DEBOUNCE_MS = 400;

function severityOf(record: CheckRecord): vscode.DiagnosticSeverity {
  return record.severity === "error"
    ? vscode.DiagnosticSeverity.Error
    : vscode.DiagnosticSeverity.Warning;
}

/**
 * Range to underline. The parser reports lines but not yet columns, so a
 * record without a column marks the whole line — VS Code trims the trailing
 * whitespace itself. Once columns arrive the precise span is used.
 */
function rangeOf(record: CheckRecord): vscode.Range {
  const line = Math.max((record.line ?? 1) - 1, 0);
  if (record.column === null) {
    return new vscode.Range(line, 0, line, Number.MAX_SAFE_INTEGER);
  }
  const start = Math.max(record.column - 1, 0);
  const end = record.endColumn !== null ? record.endColumn - 1 : start + 1;
  return new vscode.Range(line, start, line, Math.max(end, start + 1));
}

/**
 * Publishes parse problems as editor squiggles.
 *
 * Diagnostics come from the parser itself rather than the TextMate grammar,
 * which is a stateless tokeniser and cannot tell whether a construct is
 * valid. The extension shells out to `pystructurizr check --json` through
 * the same backend the preview resolves, so there is one implementation of
 * the language's rules.
 *
 * Records are grouped by the path the parser reports, which is not always
 * the file being edited: a problem inside an `!include`-ed fragment belongs
 * to the fragment, and lands there.
 *
 * Checking happens as you type, debounced: the buffer is piped to
 * `check - --path <file>`, so an unsaved edit is checked as written rather
 * than as last saved, while diagnostics still name the real file and
 * relative `!include` targets still resolve.
 *
 * One limitation is inherent: only the active document's text is in hand,
 * so `!include`-ed fragments are read from disk. A problem introduced in an
 * unsaved fragment appears once that fragment is saved.
 */
export class DiagnosticsManager implements vscode.Disposable {
  private readonly collection =
    vscode.languages.createDiagnosticCollection("pystructurizr");
  private readonly timers = new Map<string, NodeJS.Timeout>();
  /** Files this document's last run put diagnostics on, so they can be cleared. */
  private readonly owned = new Map<string, string[]>();
  private command: string[] | null = null;

  constructor(
    private readonly storageDir: string,
    private readonly output: vscode.OutputChannel,
  ) {}

  dispose(): void {
    for (const timer of this.timers.values()) clearTimeout(timer);
    this.timers.clear();
    this.collection.dispose();
  }

  /** Re-check after a pause, so typing does not spawn a process per keystroke. */
  scheduleCheck(document: vscode.TextDocument): void {
    if (document.languageId !== "structurizr-dsl") return;
    const key = document.uri.toString();
    const existing = this.timers.get(key);
    if (existing) clearTimeout(existing);
    this.timers.set(
      key,
      setTimeout(() => {
        this.timers.delete(key);
        void this.check(document);
      }, DEBOUNCE_MS),
    );
  }

  /** Drop everything this document owned — including fragment diagnostics. */
  clear(document: vscode.TextDocument): void {
    const key = document.uri.toString();
    const timer = this.timers.get(key);
    if (timer) {
      clearTimeout(timer);
      this.timers.delete(key);
    }
    for (const file of this.owned.get(key) ?? []) {
      this.collection.delete(vscode.Uri.file(file));
    }
    this.owned.delete(key);
  }

  async check(document: vscode.TextDocument): Promise<void> {
    if (document.languageId !== "structurizr-dsl") return;
    if (document.isUntitled) return;

    const file = document.uri.fsPath;
    const cwd =
      vscode.workspace.getWorkspaceFolder(document.uri)?.uri.fsPath ??
      path.dirname(file);

    if (this.command === null) {
      this.command = await resolveServerCommand(cwd, this.storageDir, this.output);
      if (this.command === null) {
        this.output.appendLine("[check] no backend available; diagnostics disabled");
        return;
      }
    }

    let records: CheckRecord[];
    try {
      records = await this.run(this.command, file, cwd, document.getText());
    } catch (error) {
      // A crashed checker must not leave stale squiggles behind, nor spam
      // the user: the reason goes to the output channel.
      this.output.appendLine(`[check] ${file}: ${String(error)}`);
      this.clear(document);
      return;
    }

    this.publish(document, file, records);
  }

  private run(
    command: string[],
    file: string,
    cwd: string,
    source: string,
  ): Promise<CheckRecord[]> {
    // "-" reads the buffer from stdin; --path keeps diagnostics pointed at
    // the real file and lets relative !include targets resolve.
    const args = [...command.slice(1), "check", "-", "--path", file, "--json"];
    return new Promise((resolve, reject) => {
      const child = execFile(
        command[0],
        args,
        { cwd, timeout: CHECK_TIMEOUT_MS, maxBuffer: 8 * 1024 * 1024 },
        (error, stdout, stderr) => {
          // `check` exits 1 when the file has errors, which is a successful
          // run with findings — not a failure to run.
          const output = stdout.trim();
          if (output.startsWith("[")) {
            try {
              resolve(JSON.parse(output) as CheckRecord[]);
              return;
            } catch (parseError) {
              reject(new Error(`unreadable check output: ${String(parseError)}`));
              return;
            }
          }
          reject(new Error(stderr.trim() || error?.message || "check produced no JSON"));
        },
      );
      child.stdin?.end(source);
    });
  }

  private publish(
    document: vscode.TextDocument,
    file: string,
    records: CheckRecord[],
  ): void {
    const byFile = new Map<string, vscode.Diagnostic[]>();
    for (const record of records) {
      // A record with no path came from a source with no file context;
      // attribute it to the document that was checked.
      const target = record.path ?? file;
      const diagnostic = new vscode.Diagnostic(
        rangeOf(record),
        record.message,
        severityOf(record),
      );
      diagnostic.source = "pystructurizr";
      if (record.code) diagnostic.code = record.code;
      const list = byFile.get(target) ?? [];
      list.push(diagnostic);
      byFile.set(target, list);
    }

    const key = document.uri.toString();
    // Clear what the previous run owned before setting the new set, or
    // problems in a fragment linger after they are fixed.
    for (const previous of this.owned.get(key) ?? []) {
      if (!byFile.has(previous)) this.collection.delete(vscode.Uri.file(previous));
    }
    for (const [target, diagnostics] of byFile) {
      this.collection.set(vscode.Uri.file(target), diagnostics);
    }
    this.collection.set(document.uri, byFile.get(file) ?? []);
    this.owned.set(key, [...byFile.keys(), file]);
  }
}
