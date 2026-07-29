import * as vscode from "vscode";

import { DiagnosticsManager } from "./diagnostics";
import { PreviewManager } from "./preview";

export function activate(context: vscode.ExtensionContext): void {
  const previews = new PreviewManager(context.globalStorageUri.fsPath);
  context.subscriptions.push(previews);

  const output = vscode.window.createOutputChannel("pystructurizr");
  context.subscriptions.push(output);

  const diagnostics = new DiagnosticsManager(
    context.globalStorageUri.fsPath,
    output,
  );
  context.subscriptions.push(diagnostics);

  const enabled = (): boolean =>
    vscode.workspace
      .getConfiguration("pystructurizr")
      .get<boolean>("diagnostics.enabled", true);

  // Check what is already open, then on open, save and edit. Editing is
  // debounced inside the manager, which pipes the buffer to the checker so
  // an unsaved edit is checked as written.
  const checkAll = (): void => {
    if (!enabled()) return;
    for (const document of vscode.workspace.textDocuments) {
      void diagnostics.check(document);
    }
  };
  checkAll();

  context.subscriptions.push(
    vscode.workspace.onDidOpenTextDocument((document) => {
      if (enabled()) void diagnostics.check(document);
    }),
    vscode.workspace.onDidSaveTextDocument((document) => {
      if (enabled()) void diagnostics.check(document);
    }),
    vscode.workspace.onDidChangeTextDocument((event) => {
      if (enabled()) diagnostics.scheduleCheck(event.document);
    }),
    vscode.workspace.onDidCloseTextDocument((document) => {
      diagnostics.clear(document);
    }),
    vscode.workspace.onDidChangeConfiguration((event) => {
      if (!event.affectsConfiguration("pystructurizr")) return;
      if (enabled()) checkAll();
    }),
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("pystructurizr.openPreview", async () => {
      const document = vscode.window.activeTextEditor?.document;
      if (!document || document.languageId !== "structurizr-dsl") {
        void vscode.window.showInformationMessage(
          "pystructurizr: open a Structurizr DSL file (.dsl) first.",
        );
        return;
      }
      if (document.isDirty) await document.save();
      await previews.open(document);
    }),
    vscode.commands.registerCommand("pystructurizr.checkFile", async () => {
      const document = vscode.window.activeTextEditor?.document;
      if (!document || document.languageId !== "structurizr-dsl") {
        void vscode.window.showInformationMessage(
          "pystructurizr: open a Structurizr DSL file (.dsl) first.",
        );
        return;
      }
      if (document.isDirty) await document.save();
      await diagnostics.check(document);
    }),
  );
}

export function deactivate(): void {
  // Disposal (server shutdown) happens via context.subscriptions.
}
