import * as vscode from "vscode";

import { DiagnosticsManager } from "./diagnostics";
import { PreviewManager } from "./preview";
import { StudioManager } from "./studio";

export function activate(context: vscode.ExtensionContext): void {
  const output = vscode.window.createOutputChannel("c4studio");
  context.subscriptions.push(output);

  const previews = new PreviewManager(context.globalStorageUri.fsPath, output);
  context.subscriptions.push(previews);

  const studio = new StudioManager(context.globalStorageUri.fsPath, output);
  context.subscriptions.push(studio);

  const diagnostics = new DiagnosticsManager(
    context.globalStorageUri.fsPath,
    output,
  );
  context.subscriptions.push(diagnostics);

  const enabled = (): boolean =>
    vscode.workspace
      .getConfiguration("c4studio")
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
      // The preview is a static picture, so unlike the old embedded SPA it
      // has nothing polling a server on its behalf.
      void previews.refresh(document);
    }),
    vscode.workspace.onDidChangeTextDocument((event) => {
      if (enabled()) diagnostics.scheduleCheck(event.document);
    }),
    vscode.workspace.onDidCloseTextDocument((document) => {
      diagnostics.clear(document);
    }),
    vscode.workspace.onDidChangeConfiguration((event) => {
      if (!event.affectsConfiguration("c4studio")) return;
      if (enabled()) checkAll();
    }),
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("c4studio.openPreview", async () => {
      const document = vscode.window.activeTextEditor?.document;
      if (!document || document.languageId !== "structurizr-dsl") {
        void vscode.window.showInformationMessage(
          "c4studio: open a Structurizr DSL file (.dsl) first.",
        );
        return;
      }
      if (document.isDirty) await document.save();
      await previews.open(document);
    }),
    vscode.commands.registerCommand("c4studio.showView", async () => {
      const document = vscode.window.activeTextEditor?.document;
      if (!document || document.languageId !== "structurizr-dsl") {
        void vscode.window.showInformationMessage(
          "c4studio: open a Structurizr DSL file (.dsl) first.",
        );
        return;
      }
      if (document.isDirty) await document.save();
      await previews.pickView(document);
    }),
    vscode.commands.registerCommand("c4studio.showPerspective", async () => {
      const document = vscode.window.activeTextEditor?.document;
      if (!document || document.languageId !== "structurizr-dsl") {
        void vscode.window.showInformationMessage(
          "c4studio: open a Structurizr DSL file (.dsl) first.",
        );
        return;
      }
      if (document.isDirty) await document.save();
      await previews.pickPerspective(document);
    }),
    vscode.commands.registerCommand("c4studio.openInStudio", async () => {
      const document = vscode.window.activeTextEditor?.document;
      if (!document || document.languageId !== "structurizr-dsl") {
        void vscode.window.showInformationMessage(
          "c4studio: open a Structurizr DSL file (.dsl) first.",
        );
        return;
      }
      if (document.isDirty) await document.save();
      await studio.open(document);
    }),
    vscode.commands.registerCommand("c4studio.checkFile", async () => {
      const document = vscode.window.activeTextEditor?.document;
      if (!document || document.languageId !== "structurizr-dsl") {
        void vscode.window.showInformationMessage(
          "c4studio: open a Structurizr DSL file (.dsl) first.",
        );
        return;
      }
      if (document.isDirty) await document.save();
      await diagnostics.check(document);
    }),
  );
}

export function deactivate(): void {
  // Disposal (the Studio server, the panel) happens via context.subscriptions.
}
